from __future__ import annotations

import hashlib
from typing import Any

from django.db.models import F
from django.utils import timezone

from .models import MLTrainingSample
from matches.models import Action, ActionTag, LiveMatch
from teams.models import Team


SAMPLE_SCHEMA = {
    'privacy': 'No player names, emails, usernames, notes, or direct identifiers included.',
    'format': 'JSON',
    'encryption': 'Samples are stored encrypted when VOLLEYPILOT_STORAGE_ENCRYPTION_KEY is configured.',
    'features': {
        'team_hash': 'Stable hash for grouping samples without exposing team identity.',
        'opponent_hash': 'Stable hash of opponent name; raw opponent names are not exported.',
        'rotation_losses': 'Lost points by rotation 1-6.',
        'tag_counts': 'Aggregated volleyball action tags only.',
        'action_counts': 'Aggregated match action counts only.',
    },
}


def _hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.strip().lower().encode('utf-8')).hexdigest()[:length]


def _completed_team_lives(team: Team):
    return LiveMatch.objects.filter(
        match__team=team,
        match__status='completed',
    ).select_related('match', 'match__team').prefetch_related('set_scores')


def _win_loss_for_live(live: LiveMatch):
    our_sets = live.set_scores.filter(is_complete=True, our_score__gt=F('opponent_score')).count()
    their_sets = live.set_scores.filter(is_complete=True, opponent_score__gt=F('our_score')).count()
    return our_sets, their_sets, our_sets > their_sets


def _opponent_public_profile(opponent_name: str) -> dict[str, Any]:
    """Return non-identifying public team-level context for an opponent if present."""
    opponent_team = Team.objects.filter(name__iexact=(opponent_name or '').strip()).first()
    if not opponent_team:
        return {}

    active_players = opponent_team.players.filter(is_active=True)
    completed_matches = opponent_team.matches.filter(status='completed')
    opp_wins = 0
    opp_losses = 0
    for match in completed_matches:
        live = getattr(match, 'live', None)
        if not live:
            continue
        our_sets = live.set_scores.filter(is_complete=True, our_score__gt=F('opponent_score')).count()
        their_sets = live.set_scores.filter(is_complete=True, opponent_score__gt=F('our_score')).count()
        if our_sets > their_sets:
            opp_wins += 1
        else:
            opp_losses += 1

    # Only export aggregate roster properties, never names/emails/jerseys/notes.
    positions = list(active_players.values_list('position', flat=True).distinct())
    return {
        'player_count': active_players.count(),
        'overall_wins': opp_wins,
        'overall_losses': opp_losses,
        'positions': positions,
    }


def anonymized_sample_for_live(team: Team, live: LiveMatch) -> dict[str, Any]:
    match = live.match
    our_sets, their_sets, won = _win_loss_for_live(live)
    actions = Action.objects.filter(live_match=live, is_undone=False)
    tags = ActionTag.objects.filter(action__live_match=live, action__is_undone=False)

    action_counts: dict[str, int] = {}
    for action in actions.only('action_type'):
        action_counts[action.action_type] = action_counts.get(action.action_type, 0) + 1

    rotation_losses = {str(rotation): 0 for rotation in range(1, 7)}
    rotation_points = {str(rotation): 0 for rotation in range(1, 7)}
    for action in actions.filter(action_type__in=['point_won', 'sideout', 'point_lost'], rotation__in=[1, 2, 3, 4, 5, 6]).only('action_type', 'rotation'):
        rotation_points[str(action.rotation)] += 1
        if action.action_type == 'point_lost':
            rotation_losses[str(action.rotation)] += 1

    tag_counts: dict[str, int] = {}
    for tag in tags.only('tag_type'):
        tag_counts[tag.tag_type] = tag_counts.get(tag.tag_type, 0) + 1

    opponent_hash = _hash(match.opponent or '')
    team_hash = _hash(f'team-{team.id}')
    sample_id = _hash(f'{team.id}-{match.id}-{match.date.isoformat()}', length=16)

    return {
        'sample_id': sample_id,
        'team_hash': team_hash,
        'opponent_hash': opponent_hash,
        'opponent_public_profile': _opponent_public_profile(match.opponent),
        'is_home': bool(match.is_home),
        'ruleset': match.ruleset,
        'season_week': int(match.date.isocalendar().week),
        'our_sets': our_sets,
        'their_sets': their_sets,
        'won': bool(won),
        'action_counts': action_counts,
        'rotation_losses': rotation_losses,
        'rotation_points': rotation_points,
        'tag_counts': tag_counts,
    }


def upsert_training_sample(team: Team, live: LiveMatch) -> MLTrainingSample:
    payload = anonymized_sample_for_live(team, live)
    sample, _ = MLTrainingSample.objects.get_or_create(
        sample_id=payload['sample_id'],
        defaults={
            'team': team,
            'source_match': live.match,
            'team_hash': payload['team_hash'],
            'opponent_hash': payload['opponent_hash'],
        },
    )
    sample.team = team
    sample.source_match = live.match
    sample.team_hash = payload['team_hash']
    sample.opponent_hash = payload['opponent_hash']
    sample.set_payload(payload)
    sample.save()
    return sample


def collect_anonymized_samples_for_team(team: Team) -> list[MLTrainingSample]:
    return [upsert_training_sample(team, live) for live in _completed_team_lives(team)]


def anonymized_dataset_for_team(team: Team) -> dict[str, Any]:
    samples = collect_anonymized_samples_for_team(team)
    rows = [sample.get_payload() for sample in samples]
    return {
        'generated_at': timezone.now().isoformat(),
        'team_hash': _hash(f'team-{team.id}'),
        'samples': rows,
        'total_samples': len(rows),
        'schema': SAMPLE_SCHEMA,
    }
