import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from schedule.models import Match
from teams.models import Player
from teams.views import get_user_team
from .models import Action, ActionTag, LiveMatch, PlayerParticipation, SetScore

TECHNICAL_TIMEOUT_POINTS = (8, 16)


def _require_team_match(request, match_id):
    match = get_object_or_404(Match, pk=match_id)
    team = get_user_team(request.user)
    if not team or match.team != team:
        return None, None
    return team, match


def _get_live(match_id):
    match = get_object_or_404(Match.objects.select_related('team'), pk=match_id)
    live = get_object_or_404(
        LiveMatch.objects.select_related('match__team', 'libero_player'),
        match=match,
    )
    return match, live


def _team_players(live):
    return list(live.match.team.players.filter(is_active=True).order_by('jersey_number'))


def _current_set_score(live):
    obj, _ = SetScore.objects.get_or_create(live_match=live, set_number=live.current_set)
    return obj


def _sets_won(live):
    ours = live.set_scores.filter(is_complete=True, our_score__gt=models.F('opponent_score')).count()
    theirs = live.set_scores.filter(is_complete=True, opponent_score__gt=models.F('our_score')).count()
    return ours, theirs


def _target_score(live):
    if live.match.ruleset == 'best_of_3':
        return 15 if live.current_set == 3 else 25
    return 15 if live.current_set == 5 else 25


def _match_win_target(live):
    return 2 if live.match.ruleset == 'best_of_3' else 3


def _rotation_after_sideout(current):
    return (current % 6) + 1


def _get_timeouts(live):
    used = live.actions.filter(action_type='timeout', set_number=live.current_set, is_undone=False).count()
    return used, max(0, 2 - used)


def _get_technical_timeouts(live):
    return live.actions.filter(action_type='technical_timeout', set_number=live.current_set, is_undone=False).count()


def _regular_subs(live):
    return live.actions.filter(action_type='substitution', set_number=live.current_set, is_undone=False).count()


def _substitution_limit(live):
    return max(1, live.match.substitution_limit or live.match.team.default_substitution_limit or 6)


def _player_lookup(players):
    return {p.pk: p for p in players}


def _ensure_participation_records(live, players):
    for player in players:
        PlayerParticipation.objects.get_or_create(live_match=live, player=player)


def _sync_participation(live, players=None, timestamp=None):
    players = players or _team_players(live)
    _ensure_participation_records(live, players)
    timestamp = timestamp or timezone.now()
    active_ids = {int(pid) for pid in (live.lineup or {}).values()}
    for record in live.participation_records.select_related('player'):
        should_be_on_court = live.is_active and record.player_id in active_ids
        if should_be_on_court and not record.currently_on_court:
            record.currently_on_court = True
            record.stint_started_at = timestamp
            record.save(update_fields=['currently_on_court', 'stint_started_at'])
        elif not should_be_on_court and record.currently_on_court:
            if record.stint_started_at:
                delta = max(0, int((timestamp - record.stint_started_at).total_seconds()))
                record.seconds_played += delta
            record.currently_on_court = False
            record.stint_started_at = None
            record.save(update_fields=['seconds_played', 'currently_on_court', 'stint_started_at'])


def _participation_totals(live, players):
    _ensure_participation_records(live, players)
    now = timezone.now()
    rows = []
    lookup = _player_lookup(players)
    for record in live.participation_records.select_related('player'):
        seconds_played = record.seconds_played
        if record.currently_on_court and record.stint_started_at:
            seconds_played += max(0, int((now - record.stint_started_at).total_seconds()))
        rows.append({
            'player': lookup.get(record.player_id, record.player),
            'seconds_played': seconds_played,
            'minutes_played': round(seconds_played / 60, 1),
        })
    return sorted(rows, key=lambda item: item['seconds_played'], reverse=True)


def _participation_payload(rows):
    return [
        {
            'player': {
                'pk': row['player'].pk,
                'name': row['player'].name,
                'jersey_number': row['player'].jersey_number,
            },
            'minutes_played': row['minutes_played'],
            'seconds_played': row['seconds_played'],
        }
        for row in rows
    ]


def _lineup_players(live, players):
    lookup = _player_lookup(players)
    result = {}
    for pos, pid in (live.lineup or {}).items():
        pid = int(pid)
        if pid in lookup:
            result[int(pos)] = lookup[pid]
    return result


def _bench_players(live, players):
    lookup = _player_lookup(players)
    result = []
    for pid in (live.bench or []):
        pid = int(pid)
        if pid in lookup:
            result.append(lookup[pid])
    return result


def _live_rotation_stats(live):
    actions = list(
        live.actions.filter(
            is_undone=False,
            action_type__in=['point_won', 'point_lost', 'sideout'],
        ).order_by('timestamp')
    )
    overall_sideout_won = 0
    overall_sideout_chances = 0
    by_rotation = []
    for rotation in range(1, 7):
        rotation_actions = [action for action in actions if action.rotation == rotation]
        won = sum(1 for action in rotation_actions if action.action_type in ('point_won', 'sideout'))
        lost = sum(1 for action in rotation_actions if action.action_type == 'point_lost')
        sideout_won = sum(
            1 for action in rotation_actions if not action.data.get('our_serve', True) and action.action_type in ('point_won', 'sideout')
        )
        sideout_chances = sum(1 for action in rotation_actions if not action.data.get('our_serve', True))
        overall_sideout_won += sideout_won
        overall_sideout_chances += sideout_chances
        by_rotation.append({
            'rotation': rotation,
            'won': won,
            'lost': lost,
            'net': won - lost,
            'sideout_pct': round(sideout_won / sideout_chances * 100) if sideout_chances else 0,
        })
    return {
        'by_rotation': by_rotation,
        'overall_sideout_pct': round(overall_sideout_won / overall_sideout_chances * 100) if overall_sideout_chances else 0,
    }


def _run_stats(live):
    actions = list(
        live.actions.filter(
            is_undone=False,
            action_type__in=['point_won', 'point_lost', 'sideout'],
        ).order_by('timestamp')
    )
    current_run = 0
    longest_run = 0
    for action in actions:
        if action.action_type in ('point_won', 'sideout'):
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    return {'current_run': current_run, 'longest_run': longest_run}


def _latest_point_action(live):
    return live.actions.filter(
        is_undone=False,
        action_type__in=['point_won', 'point_lost', 'sideout'],
    ).order_by('-timestamp').first()


def _get_action_label(action, players):
    lookup = _player_lookup(players)
    data = action.data or {}
    if action.action_type == 'match_start':
        return f"Match started - server position {data.get('first_server', 1)}"
    if action.action_type == 'point_won':
        return f"Point VolleyPilot - {data.get('our_score', 0)}-{data.get('opponent_score', 0)}"
    if action.action_type == 'point_lost':
        return f"Point Opponent - {data.get('our_score', 0)}-{data.get('opponent_score', 0)}"
    if action.action_type == 'sideout':
        return f"Sideout won - {data.get('our_score', 0)}-{data.get('opponent_score', 0)}"
    if action.action_type == 'timeout':
        return 'Coach timeout called'
    if action.action_type == 'technical_timeout':
        return f"Technical timeout at {data.get('trigger_score')} points"
    if action.action_type == 'rotation':
        return f"Rotation changed to {action.rotation}"
    if action.action_type == 'lineup':
        return 'Lineup updated'
    if action.action_type == 'substitution':
        player_in = lookup.get(int(data.get('player_in_id', 0)))
        player_out = lookup.get(int(data.get('player_out_id', 0)))
        if data.get('is_libero_swap'):
            return f"Libero swap - {player_in or data.get('player_in_id')} for {player_out or data.get('player_out_id')}"
        return f"Substitution - {player_in or data.get('player_in_id')} in for {player_out or data.get('player_out_id')}"
    if action.action_type == 'undo':
        return f"Undo - {data.get('target_action_type', 'action')}"
    return action.get_action_type_display()


def _build_context(live, team, players):
    _sync_participation(live, players)
    set_score = _current_set_score(live)
    all_set_scores = live.set_scores.filter(is_complete=True)
    our_sets, their_sets = _sets_won(live)
    position_players = _lineup_players(live, players)
    bench_players = _bench_players(live, players)
    subs_remaining = max(0, _substitution_limit(live) - _regular_subs(live))
    _, timeouts_remaining = _get_timeouts(live)
    technical_timeouts = _get_technical_timeouts(live)
    actions = live.actions.filter(is_undone=False).order_by('-timestamp')[:25]
    action_log = [
        {'timestamp': action.timestamp, 'label': _get_action_label(action, players), 'set_number': action.set_number}
        for action in actions
    ]
    participation_totals = _participation_totals(live, players)
    return {
        'match': live.match,
        'live': live,
        'team': team,
        'players': players,
        'players_json': [
            {
                'pk': player.pk,
                'name': player.name,
                'jersey_number': player.jersey_number,
                'position': player.position,
            }
            for player in players
        ],
        'set_score': set_score,
        'our_sets': our_sets,
        'their_sets': their_sets,
        'all_set_scores': all_set_scores,
        'position_players': position_players,
        'bench_players': bench_players,
        'subs_remaining': subs_remaining,
        'substitution_limit': _substitution_limit(live),
        'timeouts_remaining': timeouts_remaining,
        'technical_timeouts': technical_timeouts,
        'action_log': action_log,
        'rotation_metrics': _live_rotation_stats(live),
        'run_stats': _run_stats(live),
        'participation_totals': participation_totals[:6],
        'libero_player': live.libero_player,
        'tag_choices': ActionTag.TAG_CHOICES,
        'lineup_json': json.dumps(live.lineup or {}),
        'bench_json': json.dumps(live.bench or []),
    }


@login_required
def start_match(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        messages.error(request, 'Only staff can start this match.')
        return redirect('schedule')

    players = list(team.players.filter(is_active=True).order_by('jersey_number'))
    if request.method == 'POST':
        lineup = {str(i): request.POST.get(f'position_{i}') for i in range(1, 7)}
        lineup = {key: int(value) for key, value in lineup.items() if value}
        first_server = int(request.POST.get('first_server', '1') or '1')
        libero_id = request.POST.get('libero_player') or ''
        if len(lineup) != 6 or len(set(lineup.values())) != 6:
            messages.error(request, 'Choose 6 unique starters for positions 1-6.')
            return render(request, 'matches/match_startup.html', {
                'match': match,
                'team': team,
                'players': players,
                'selected_lineup': lineup,
                'selected_bench': request.POST.getlist('bench'),
                'first_server': first_server,
                'selected_libero': libero_id,
            })
        bench = [int(pid) for pid in request.POST.getlist('bench') if pid and int(pid) not in lineup.values()]
        libero_player = None
        if libero_id:
            libero_player = next((player for player in players if player.pk == int(libero_id)), None)
            if not libero_player:
                messages.error(request, 'Choose a valid libero from your roster.')
                return redirect('start_match', match_id=match.id)
        live, _ = LiveMatch.objects.get_or_create(match=match)
        live.current_set = 1
        live.is_active = True
        live.our_serve = True
        live.current_rotation = first_server
        live.lineup = lineup
        live.bench = bench
        live.first_server = first_server
        live.libero_player = libero_player
        live.ended_at = None
        live.save()
        team.preferred_lineup = lineup
        team.preferred_first_server = first_server
        team.save(update_fields=['preferred_lineup', 'preferred_first_server'])
        _ensure_participation_records(live, players)
        _sync_participation(live, players, timestamp=live.started_at)
        SetScore.objects.get_or_create(live_match=live, set_number=1)
        Action.objects.create(
            live_match=live,
            action_type='match_start',
            set_number=1,
            rotation=first_server,
            data={
                'lineup': lineup,
                'bench': bench,
                'first_server': first_server,
                'libero_player_id': libero_player.pk if libero_player else None,
            },
        )
        Action.objects.create(
            live_match=live,
            action_type='lineup',
            set_number=1,
            rotation=first_server,
            data={
                'positions': lineup,
                'bench': bench,
                'first_server': first_server,
                'libero_player_id': libero_player.pk if libero_player else None,
            },
        )
        messages.success(request, 'Match started.')
        return redirect('live_match', match_id=match.id)

    existing = getattr(match, 'live', None)
    selected_lineup = getattr(existing, 'lineup', None) if existing else None
    if not selected_lineup:
        preferred = team.preferred_lineup or {}
        valid_ids = {player.pk for player in players}
        preferred = {
            str(position): int(player_id)
            for position, player_id in preferred.items()
            if int(player_id) in valid_ids
        }
        if len(preferred) == 6 and len(set(preferred.values())) == 6:
            selected_lineup = preferred
    selected_lineup = selected_lineup or {}
    selected_bench = getattr(existing, 'bench', None) if existing else None
    if selected_bench is None:
        selected_bench = [player.pk for player in players if player.pk not in selected_lineup.values()]
    return render(request, 'matches/match_startup.html', {
        'match': match,
        'team': team,
        'players': players,
        'selected_lineup': selected_lineup,
        'selected_bench': selected_bench,
        'first_server': getattr(existing, 'first_server', team.preferred_first_server) if existing else team.preferred_first_server,
        'selected_libero': getattr(existing, 'libero_player_id', None) if existing else None,
    })


@login_required
def live_match_view(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team:
        return redirect('dashboard')
    live = getattr(match, 'live', None)
    if not live:
        messages.info(request, 'Set the lineup and start the match first.')
        return redirect('start_match', match_id=match.id)
    players = list(team.players.filter(is_active=True).order_by('jersey_number'))
    ctx = _build_context(live, team, players)
    return render(request, 'matches/live_match.html', ctx)


@require_POST
@login_required
@transaction.atomic
def set_lineup(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    data = json.loads(request.body)
    positions = {str(key): int(value) for key, value in data.get('positions', {}).items() if value}
    if len(positions) != 6 or len(set(positions.values())) != 6:
        return JsonResponse({'ok': False, 'error': 'Choose 6 unique players.'}, status=400)
    bench = [int(pid) for pid in data.get('bench', []) if int(pid) not in positions.values()]
    libero_player = None
    libero_id = data.get('libero_player')
    if libero_id:
        libero_player = Player.objects.filter(pk=int(libero_id), team=team, is_active=True).first()
        if not libero_player:
            return JsonResponse({'ok': False, 'error': 'Choose a valid libero.'}, status=400)
    live.lineup = positions
    live.bench = bench
    if data.get('first_server'):
        live.first_server = int(data['first_server'])
        live.current_rotation = int(data['first_server'])
    live.libero_player = libero_player
    live.save()
    team.preferred_lineup = positions
    team.preferred_first_server = live.first_server
    team.save(update_fields=['preferred_lineup', 'preferred_first_server'])
    _sync_participation(live, timestamp=timezone.now())
    Action.objects.create(
        live_match=live,
        action_type='lineup',
        set_number=live.current_set,
        rotation=live.current_rotation,
        data={
            'positions': positions,
            'bench': bench,
            'first_server': live.first_server,
            'libero_player_id': libero_player.pk if libero_player else None,
        },
    )
    return JsonResponse(_state_payload(live, include_events=True))


@require_POST
@login_required
@transaction.atomic
def record_point(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    data = json.loads(request.body)
    us = bool(data.get('us', True))
    mode = data.get('mode', 'point')
    set_score = _current_set_score(live)

    before = {
        'our_score': set_score.our_score,
        'opponent_score': set_score.opponent_score,
        'our_serve': live.our_serve,
        'current_rotation': live.current_rotation,
        'current_set': live.current_set,
    }

    if us:
        set_score.our_score += 1
        action_type = 'sideout' if mode == 'sideout' and not live.our_serve else 'point_won'
        if not live.our_serve:
            live.current_rotation = _rotation_after_sideout(live.current_rotation)
            live.our_serve = True
    else:
        set_score.opponent_score += 1
        action_type = 'point_lost'
        if live.our_serve:
            live.our_serve = False

    set_score.save()
    live.save()
    Action.objects.create(
        live_match=live,
        action_type=action_type,
        set_number=live.current_set,
        rotation=live.current_rotation,
        data={**before, 'our_score': set_score.our_score, 'opponent_score': set_score.opponent_score},
    )

    trigger_score = max(set_score.our_score, set_score.opponent_score)
    if live.current_set != 5 and trigger_score in TECHNICAL_TIMEOUT_POINTS:
        existing = live.actions.filter(
            action_type='technical_timeout',
            set_number=live.current_set,
            data__trigger_score=trigger_score,
            is_undone=False,
        ).exists()
        if not existing:
            Action.objects.create(
                live_match=live,
                action_type='technical_timeout',
                set_number=live.current_set,
                rotation=live.current_rotation,
                data={'trigger_score': trigger_score},
            )

    set_over = _check_set_over(live, set_score)
    match_over = False
    if set_over:
        ours, theirs = _sets_won(live)
        if ours >= _match_win_target(live) or theirs >= _match_win_target(live):
            _end_match(live)
            match_over = True
        else:
            _start_new_set(live)

    return JsonResponse(_state_payload(live, include_events=True, set_over=set_over, match_over=match_over))


def _check_set_over(live, set_score):
    target = _target_score(live)
    if (set_score.our_score >= target and set_score.our_score - set_score.opponent_score >= 2) or (
        set_score.opponent_score >= target and set_score.opponent_score - set_score.our_score >= 2
    ):
        set_score.is_complete = True
        set_score.save(update_fields=['is_complete'])
        return True
    return False


def _start_new_set(live):
    live.current_set += 1
    live.current_rotation = live.first_server or 1
    live.our_serve = True
    live.save()
    SetScore.objects.get_or_create(live_match=live, set_number=live.current_set)


def _end_match(live):
    _sync_participation(live, timestamp=timezone.now())
    live.is_active = False
    live.ended_at = timezone.now()
    live.save()
    live.match.status = 'completed'
    live.match.save(update_fields=['status'])

    # VT-107: capture a de-identified training sample when a match finishes.
    # This is deliberately non-blocking so live scoring remains fast (VT-99).
    try:
        from dashboard.ml import upsert_training_sample

        upsert_training_sample(live.match.team, live)
    except Exception:
        # Analytics collection must never interrupt match operations.
        pass


@require_POST
@login_required
@transaction.atomic
def manual_rotate(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    data = json.loads(request.body)
    direction = data.get('direction', 'forward')
    previous = live.current_rotation
    if direction == 'forward':
        live.current_rotation = _rotation_after_sideout(live.current_rotation)
    else:
        live.current_rotation = ((live.current_rotation - 2) % 6) + 1
    live.save()
    Action.objects.create(
        live_match=live,
        action_type='rotation',
        set_number=live.current_set,
        rotation=live.current_rotation,
        data={'previous_rotation': previous, 'direction': direction},
    )
    return JsonResponse(_state_payload(live, include_events=True))


@require_POST
@login_required
@transaction.atomic
def make_substitution(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    data = json.loads(request.body)
    player_in_id = data.get('player_in')
    player_out_id = data.get('player_out')
    is_libero_swap = bool(data.get('is_libero_swap'))
    if not player_in_id or not player_out_id or str(player_in_id) == str(player_out_id):
        return JsonResponse({'ok': False, 'error': 'Choose two different players.'}, status=400)
    if not is_libero_swap and _regular_subs(live) >= 6:
        return JsonResponse({'ok': False, 'error': 'Substitution limit reached for this set.'}, status=400)
    if not is_libero_swap and _regular_subs(live) >= _substitution_limit(live):
        return JsonResponse({'ok': False, 'error': 'Substitution limit reached for this set.'}, status=400)

    lineup = live.lineup or {}
    bench = set(int(pid) for pid in live.bench or [])
    out_position = next((pos for pos, pid in lineup.items() if int(pid) == int(player_out_id)), None)
    if not out_position:
        return JsonResponse({'ok': False, 'error': 'Outgoing player must be on the court.'}, status=400)
    if int(player_in_id) not in bench:
        return JsonResponse({'ok': False, 'error': 'Incoming player must come from the bench.'}, status=400)
    if is_libero_swap:
        if not live.libero_player_id:
            return JsonResponse({'ok': False, 'error': 'Assign a libero before recording libero swaps.'}, status=400)
        if int(player_in_id) != live.libero_player_id and int(player_out_id) != live.libero_player_id:
            return JsonResponse({'ok': False, 'error': 'One side of a libero swap must be the assigned libero.'}, status=400)

    lineup[str(out_position)] = int(player_in_id)
    bench.discard(int(player_in_id))
    bench.add(int(player_out_id))
    live.lineup = lineup
    live.bench = sorted(bench)
    live.save()
    _sync_participation(live, timestamp=timezone.now())
    Action.objects.create(
        live_match=live,
        action_type='substitution',
        set_number=live.current_set,
        rotation=live.current_rotation,
        data={
            'player_in_id': player_in_id,
            'player_out_id': player_out_id,
            'position': out_position,
            'is_libero_swap': is_libero_swap,
        },
    )
    return JsonResponse(_state_payload(live, include_events=True))


@require_POST
@login_required
@transaction.atomic
def call_timeout(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    used, remaining = _get_timeouts(live)
    if remaining <= 0:
        return JsonResponse({'ok': False, 'error': 'No timeouts remaining.'}, status=400)
    Action.objects.create(
        live_match=live,
        action_type='timeout',
        set_number=live.current_set,
        rotation=live.current_rotation,
        data={},
    )
    return JsonResponse(_state_payload(live, include_events=True))


@require_POST
@login_required
@transaction.atomic
def undo_last_action(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    last = live.actions.filter(is_undone=False).exclude(action_type='undo').order_by('-timestamp').first()
    if not last:
        return JsonResponse({'ok': False, 'error': 'Nothing to undo.'}, status=400)

    if last.action_type in ('point_won', 'point_lost', 'sideout'):
        set_score = SetScore.objects.get(live_match=live, set_number=last.set_number)
        set_score.our_score = last.data.get('our_score', set_score.our_score) - (1 if last.action_type in ('point_won', 'sideout') else 0)
        set_score.opponent_score = last.data.get('opponent_score', set_score.opponent_score) - (1 if last.action_type == 'point_lost' else 0)
        set_score.our_score = max(0, set_score.our_score)
        set_score.opponent_score = max(0, set_score.opponent_score)
        set_score.is_complete = False
        set_score.save()
        live.our_serve = last.data.get('our_serve', live.our_serve)
        live.current_rotation = last.data.get('current_rotation', live.current_rotation)
        live.current_set = last.data.get('current_set', live.current_set)
        live.is_active = True
        live.ended_at = None
        live.save()
        if live.match.status == 'completed':
            live.match.status = 'scheduled'
            live.match.save(update_fields=['status'])
    elif last.action_type == 'rotation':
        live.current_rotation = last.data.get('previous_rotation', live.current_rotation)
        live.save()
    elif last.action_type == 'substitution':
        lineup = live.lineup or {}
        bench = set(int(pid) for pid in live.bench or [])
        position = str(last.data.get('position'))
        player_in = int(last.data.get('player_in_id'))
        player_out = int(last.data.get('player_out_id'))
        lineup[position] = player_out
        bench.discard(player_out)
        bench.add(player_in)
        live.lineup = lineup
        live.bench = sorted(bench)
        live.save()
        _sync_participation(live, timestamp=timezone.now())
    elif last.action_type == 'lineup':
        previous = live.actions.filter(action_type='lineup', is_undone=False, timestamp__lt=last.timestamp).order_by('-timestamp').first()
        if previous:
            live.lineup = previous.data.get('positions', live.lineup)
            live.bench = previous.data.get('bench', live.bench)
            live.first_server = previous.data.get('first_server', live.first_server)
            previous_libero = previous.data.get('libero_player_id')
            live.libero_player = Player.objects.filter(pk=previous_libero, team=live.match.team).first() if previous_libero else None
            live.current_rotation = live.first_server
            live.save()
            _sync_participation(live, timestamp=timezone.now())

    last.is_undone = True
    last.save(update_fields=['is_undone'])
    Action.objects.create(
        live_match=live,
        action_type='undo',
        set_number=live.current_set,
        rotation=live.current_rotation,
        data={'target_action_type': last.action_type},
    )
    return JsonResponse(_state_payload(live, include_events=True))


@login_required
def match_state(request, match_id):
    match, live = _get_live(match_id)
    return JsonResponse(_state_payload(live, include_events=True))


@require_POST
@login_required
@transaction.atomic
def tag_last_point(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    latest_action = _latest_point_action(live)
    if not latest_action:
        return JsonResponse({'ok': False, 'error': 'Record a rally before tagging it.'}, status=400)
    data = json.loads(request.body)
    tag_type = data.get('tag_type')
    player_id = data.get('player_id')
    if tag_type not in dict(ActionTag.TAG_CHOICES):
        return JsonResponse({'ok': False, 'error': 'Choose a valid tag.'}, status=400)
    player = Player.objects.filter(pk=player_id, team=team, is_active=True).first() if player_id else None
    ActionTag.objects.create(action=latest_action, tag_type=tag_type, player=player)
    return JsonResponse({**_state_payload(live, include_events=True), 'label': f"{tag_type.replace('_', ' ').title()} tagged"})


def _state_payload(live, include_events=False, set_over=False, match_over=False):
    # Prefetch all non-undone actions once to avoid redundant queries (VT-99)
    all_actions = list(live.actions.filter(is_undone=False).order_by('timestamp'))
    players = _team_players(live)
    _sync_participation(live, players)
    set_score = _current_set_score(live)
    our_sets, their_sets = _sets_won(live)
    participation_rows = _participation_totals(live, players)

    # Count timeouts/subs/technical TOs from prefetched list
    current_set = live.current_set
    timeouts_used = sum(
        1 for a in all_actions
        if a.action_type == 'timeout' and a.set_number == current_set
    )
    timeouts_remaining = max(0, 2 - timeouts_used)
    technical_timeouts = sum(
        1 for a in all_actions
        if a.action_type == 'technical_timeout' and a.set_number == current_set
    )
    subs_used = sum(
        1 for a in all_actions
        if a.action_type == 'substitution' and a.set_number == current_set
        and not (a.data or {}).get('is_libero_swap')
    )

    # Inline rotation stats (VT-99 — avoid separate DB round-trip)
    point_actions = [
        a for a in all_actions
        if a.action_type in ('point_won', 'point_lost', 'sideout')
    ]
    overall_so_won = overall_so_chances = 0
    by_rotation = []
    for rotation in range(1, 7):
        ra = [a for a in point_actions if a.rotation == rotation]
        won = sum(1 for a in ra if a.action_type in ('point_won', 'sideout'))
        lost = sum(1 for a in ra if a.action_type == 'point_lost')
        so_won = sum(
            1 for a in ra
            if not a.data.get('our_serve', True) and a.action_type in ('point_won', 'sideout')
        )
        so_chances = sum(1 for a in ra if not a.data.get('our_serve', True))
        overall_so_won += so_won
        overall_so_chances += so_chances
        by_rotation.append({
            'rotation': rotation, 'won': won, 'lost': lost,
            'net': won - lost,
            'sideout_pct': round(so_won / so_chances * 100) if so_chances else 0,
        })
    rotation_metrics = {
        'by_rotation': by_rotation,
        'overall_sideout_pct': round(overall_so_won / overall_so_chances * 100)
        if overall_so_chances else 0,
    }

    # Inline run stats
    current_run = longest_run = 0
    for a in point_actions:
        if a.action_type in ('point_won', 'sideout'):
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    run_stats = {'current_run': current_run, 'longest_run': longest_run}

    sub_limit = _substitution_limit(live)
    payload = {
        'ok': True,
        'our_score': set_score.our_score,
        'opponent_score': set_score.opponent_score,
        'our_serve': live.our_serve,
        'rotation': live.current_rotation,
        'current_set': live.current_set,
        'our_sets': our_sets,
        'their_sets': their_sets,
        'subs_remaining': max(0, sub_limit - subs_used),
        'substitution_limit': sub_limit,
        'timeouts_remaining': timeouts_remaining,
        'technical_timeouts': technical_timeouts,
        'is_active': live.is_active,
        'lineup': live.lineup,
        'bench': live.bench,
        'first_server': live.first_server,
        'libero_player_id': live.libero_player_id,
        'rotation_metrics': rotation_metrics,
        'run_stats': run_stats,
        'participation_totals': _participation_payload(participation_rows[:6]),
        'set_over': set_over,
        'match_over': match_over,
    }
    if include_events:
        recent = all_actions[-10:]
        payload['events'] = [
            {
                'label': _get_action_label(a, players),
                'timestamp': a.timestamp.strftime('%H:%M:%S'),
            }
            for a in reversed(recent)
        ]
    return payload
