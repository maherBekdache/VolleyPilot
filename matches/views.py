import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from schedule.models import Match
from teams.models import Player
from teams.views import get_user_team
from .models import Action, ActionTag, LiveMatch, SetScore

TECHNICAL_TIMEOUT_POINTS = (8, 16)


def _require_team_match(request, match_id):
    match = get_object_or_404(Match, pk=match_id)
    team = get_user_team(request.user)
    if not team or match.team != team:
        return None, None
    return team, match


def _get_live(match_id):
    match = get_object_or_404(Match, pk=match_id)
    live = get_object_or_404(LiveMatch, match=match)
    return match, live


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


def _player_lookup(players):
    return {p.pk: p for p in players}


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


def _get_action_label(action, players):
    lookup = _player_lookup(players)
    data = action.data or {}
    if action.action_type == 'match_start':
        return f"Match started · server position {data.get('first_server', 1)}"
    if action.action_type == 'point_won':
        return f"Point VolleyPilot · {data.get('our_score', 0)}-{data.get('opponent_score', 0)}"
    if action.action_type == 'point_lost':
        return f"Point Opponent · {data.get('our_score', 0)}-{data.get('opponent_score', 0)}"
    if action.action_type == 'timeout':
        return 'Coach timeout called'
    if action.action_type == 'technical_timeout':
        return f"Technical timeout at {data.get('trigger_score')} points"
    if action.action_type == 'rotation':
        return f"Rotation changed to {action.rotation}"
    if action.action_type == 'lineup':
        return 'Lineup updated'
    if action.action_type == 'substitution':
        p_in = lookup.get(int(data.get('player_in_id', 0)))
        p_out = lookup.get(int(data.get('player_out_id', 0)))
        if data.get('is_libero_swap'):
            return f"Libero swap · {p_in or data.get('player_in_id')} for {p_out or data.get('player_out_id')}"
        return f"Substitution · {p_in or data.get('player_in_id')} in for {p_out or data.get('player_out_id')}"
    if action.action_type == 'undo':
        return f"Undo · {data.get('target_action_type', 'action')}"
    return action.get_action_type_display()


def _build_context(live, team, players):
    set_score = _current_set_score(live)
    all_set_scores = live.set_scores.filter(is_complete=True)
    our_sets, their_sets = _sets_won(live)
    position_players = _lineup_players(live, players)
    bench_players = _bench_players(live, players)
    subs_remaining = max(0, 6 - _regular_subs(live))
    _, timeouts_remaining = _get_timeouts(live)
    technical_timeouts = _get_technical_timeouts(live)
    actions = live.actions.filter(is_undone=False).order_by('-timestamp')[:25]
    action_log = [
        {
            'timestamp': a.timestamp,
            'label': _get_action_label(a, players),
            'set_number': a.set_number,
        }
        for a in actions
    ]
    return {
        'match': live.match,
        'live': live,
        'team': team,
        'players': players,
        'set_score': set_score,
        'our_sets': our_sets,
        'their_sets': their_sets,
        'all_set_scores': all_set_scores,
        'position_players': position_players,
        'bench_players': bench_players,
        'subs_remaining': subs_remaining,
        'timeouts_remaining': timeouts_remaining,
        'technical_timeouts': technical_timeouts,
        'action_log': action_log,
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
        lineup = {k: int(v) for k, v in lineup.items() if v}
        first_server = int(request.POST.get('first_server', '1') or '1')
        if len(lineup) != 6 or len(set(lineup.values())) != 6:
            messages.error(request, 'Choose 6 unique starters for positions 1-6.')
            return render(request, 'matches/match_startup.html', {
                'match': match,
                'team': team,
                'players': players,
                'selected_lineup': lineup,
                'selected_bench': request.POST.getlist('bench'),
                'first_server': first_server,
            })
        bench = [int(pid) for pid in request.POST.getlist('bench') if pid and int(pid) not in lineup.values()]
        live, _ = LiveMatch.objects.get_or_create(match=match)
        live.current_set = 1
        live.is_active = True
        live.our_serve = True
        live.current_rotation = first_server
        live.lineup = lineup
        live.bench = bench
        live.first_server = first_server
        live.ended_at = None
        live.save()
        SetScore.objects.get_or_create(live_match=live, set_number=1)
        Action.objects.create(
            live_match=live,
            action_type='match_start',
            set_number=1,
            rotation=first_server,
            data={'lineup': lineup, 'bench': bench, 'first_server': first_server},
        )
        Action.objects.create(
            live_match=live,
            action_type='lineup',
            set_number=1,
            rotation=first_server,
            data={'positions': lineup},
        )
        messages.success(request, 'Match started.')
        return redirect('live_match', match_id=match.id)

    existing = getattr(match, 'live', None)
    return render(request, 'matches/match_startup.html', {
        'match': match,
        'team': team,
        'players': players,
        'selected_lineup': getattr(existing, 'lineup', {}) if existing else {},
        'selected_bench': getattr(existing, 'bench', []) if existing else [],
        'first_server': getattr(existing, 'first_server', 1) if existing else 1,
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
def set_lineup(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    data = json.loads(request.body)
    positions = {str(k): int(v) for k, v in data.get('positions', {}).items() if v}
    if len(positions) != 6 or len(set(positions.values())) != 6:
        return JsonResponse({'ok': False, 'error': 'Choose 6 unique players.'}, status=400)
    bench = [int(pid) for pid in data.get('bench', []) if int(pid) not in positions.values()]
    live.lineup = positions
    live.bench = bench
    if data.get('first_server'):
        live.first_server = int(data['first_server'])
        live.current_rotation = int(data['first_server'])
    live.save()
    Action.objects.create(
        live_match=live,
        action_type='lineup',
        set_number=live.current_set,
        rotation=live.current_rotation,
        data={'positions': positions, 'bench': bench, 'first_server': live.first_server},
    )
    return JsonResponse({'ok': True})


@require_POST
@login_required
def record_point(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    data = json.loads(request.body)
    us = bool(data.get('us', True))
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
        action_type = 'point_won'
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
    live.is_active = False
    live.ended_at = timezone.now()
    live.save()
    live.match.status = 'completed'
    live.match.save(update_fields=['status'])


@require_POST
@login_required
def manual_rotate(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    data = json.loads(request.body)
    direction = data.get('direction', 'forward')
    previous = live.current_rotation
    live.current_rotation = _rotation_after_sideout(live.current_rotation) if direction == 'forward' else ((live.current_rotation - 2) % 6) + 1
    live.save()
    Action.objects.create(
        live_match=live,
        action_type='rotation',
        set_number=live.current_set,
        rotation=live.current_rotation,
        data={'previous_rotation': previous, 'direction': direction},
    )
    return JsonResponse({'ok': True, 'rotation': live.current_rotation})


@require_POST
@login_required
def make_substitution(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    data = json.loads(request.body)
    player_in_id = data.get('player_in')
    player_out_id = data.get('player_out')
    if not player_in_id or not player_out_id or str(player_in_id) == str(player_out_id):
        return JsonResponse({'ok': False, 'error': 'Choose two different players.'}, status=400)
    if _regular_subs(live) >= 6:
        return JsonResponse({'ok': False, 'error': 'Substitution limit reached for this set.'}, status=400)

    lineup = live.lineup or {}
    bench = set(int(pid) for pid in live.bench or [])
    out_position = next((pos for pos, pid in lineup.items() if int(pid) == int(player_out_id)), None)
    if not out_position:
        return JsonResponse({'ok': False, 'error': 'Outgoing player must be on the court.'}, status=400)
    lineup[str(out_position)] = int(player_in_id)
    bench.discard(int(player_in_id))
    bench.add(int(player_out_id))
    live.lineup = lineup
    live.bench = sorted(bench)
    live.save()
    Action.objects.create(
        live_match=live,
        action_type='substitution',
        set_number=live.current_set,
        rotation=live.current_rotation,
        data={'player_in_id': player_in_id, 'player_out_id': player_out_id, 'position': out_position},
    )
    return JsonResponse({'ok': True, 'subs_remaining': max(0, 6 - _regular_subs(live))})


@require_POST
@login_required
def call_timeout(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    used, remaining = _get_timeouts(live)
    if remaining <= 0:
        return JsonResponse({'ok': False, 'error': 'No timeouts remaining.'}, status=400)
    Action.objects.create(live_match=live, action_type='timeout', set_number=live.current_set, rotation=live.current_rotation, data={})
    return JsonResponse({'ok': True, 'timeouts_remaining': remaining - 1})


@require_POST
@login_required
def undo_last_action(request, match_id):
    team, match = _require_team_match(request, match_id)
    if not team or not request.user.is_staff_role:
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    live = match.live
    last = live.actions.filter(is_undone=False).exclude(action_type='undo').order_by('-timestamp').first()
    if not last:
        return JsonResponse({'ok': False, 'error': 'Nothing to undo.'}, status=400)

    if last.action_type in ('point_won', 'point_lost'):
        set_score = SetScore.objects.get(live_match=live, set_number=last.set_number)
        set_score.our_score = last.data.get('our_score', set_score.our_score) - (1 if last.action_type == 'point_won' else 0)
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
    elif last.action_type == 'timeout':
        pass
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
    elif last.action_type == 'lineup':
        previous = live.actions.filter(action_type='lineup', is_undone=False, timestamp__lt=last.timestamp).order_by('-timestamp').first()
        if previous:
            live.lineup = previous.data.get('positions', live.lineup)
            live.bench = previous.data.get('bench', live.bench)
            live.first_server = previous.data.get('first_server', live.first_server)
            live.current_rotation = live.first_server
            live.save()
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


def _state_payload(live, include_events=False, set_over=False, match_over=False):
    set_score = _current_set_score(live)
    our_sets, their_sets = _sets_won(live)
    _, timeouts_remaining = _get_timeouts(live)
    payload = {
        'ok': True,
        'our_score': set_score.our_score,
        'opponent_score': set_score.opponent_score,
        'our_serve': live.our_serve,
        'rotation': live.current_rotation,
        'current_set': live.current_set,
        'our_sets': our_sets,
        'their_sets': their_sets,
        'subs_remaining': max(0, 6 - _regular_subs(live)),
        'timeouts_remaining': timeouts_remaining,
        'technical_timeouts': _get_technical_timeouts(live),
        'is_active': live.is_active,
        'lineup': live.lineup,
        'bench': live.bench,
        'first_server': live.first_server,
        'set_over': set_over,
        'match_over': match_over,
    }
    if include_events:
        payload['events'] = [
            {'label': a.get_action_type_display(), 'timestamp': a.timestamp.strftime('%H:%M:%S')}
            for a in live.actions.filter(is_undone=False).order_by('-timestamp')[:10]
        ]
    return payload
