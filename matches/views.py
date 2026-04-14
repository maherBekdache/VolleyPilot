import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages
from teams.views import get_user_team
from teams.models import Player
from schedule.models import Match
from .models import LiveMatch, SetScore, Action, ActionTag


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_live(match_id):
    match = get_object_or_404(Match, pk=match_id)
    live = get_object_or_404(LiveMatch, match=match)
    return match, live


def _current_set_score(live):
    obj, _ = SetScore.objects.get_or_create(
        live_match=live,
        set_number=live.current_set,
        defaults={'our_score': 0, 'opponent_score': 0},
    )
    return obj


def _sets_won(live):
    our = sum(1 for s in live.set_scores.filter(is_complete=True) if s.our_score > s.opponent_score)
    theirs = sum(1 for s in live.set_scores.filter(is_complete=True) if s.opponent_score > s.our_score)
    return our, theirs


def _rotation_after_sideout(current):
    return (current % 6) + 1


def _get_lineup(live):
    lineup_action = live.actions.filter(
        action_type='lineup', is_undone=False
    ).order_by('-timestamp').first()
    if lineup_action and lineup_action.data.get('positions'):
        return lineup_action.data['positions']
    return {}


def _get_libero_id(live):
    la = live.actions.filter(action_type='libero_swap', is_undone=False).order_by('-timestamp').first()
    if la:
        return la.data.get('libero_id')
    return None


def _get_timeouts(live):
    used = live.actions.filter(
        action_type='timeout', set_number=live.current_set, is_undone=False
    ).count()
    return used, max(0, 2 - used)


def _regular_subs(live):
    return [
        s for s in live.actions.filter(
            action_type='substitution', set_number=live.current_set, is_undone=False
        ) if not s.data.get('is_libero_swap')
    ]


def _build_context(live, team, players):
    match = live.match
    set_score = _current_set_score(live)
    our_sets, their_sets = _sets_won(live)
    all_set_scores = list(live.set_scores.filter(is_complete=True))
    lineup = _get_lineup(live)
    reg_subs = _regular_subs(live)
    subs_remaining = max(0, 6 - len(reg_subs))
    libero_id = _get_libero_id(live)
    libero_player = players.filter(pk=libero_id).first() if libero_id else None
    _, timeouts_remaining = _get_timeouts(live)

    libero_out_ids = set()
    for ls in live.actions.filter(action_type='libero_swap', is_undone=False):
        pid = ls.data.get('replaced_player_id')
        if pid:
            libero_out_ids.add(int(pid))

    position_players = {}
    for pos_str, pid in lineup.items():
        p = players.filter(pk=int(pid)).first()
        if p:
            position_players[int(pos_str)] = p

    return {
        'match': match,
        'live': live,
        'team': team,
        'players': players,
        'set_score': set_score,
        'our_sets': our_sets,
        'their_sets': their_sets,
        'all_set_scores': all_set_scores,
        'lineup': lineup,
        'position_players': position_players,
        'subs_used': len(reg_subs),
        'subs_remaining': subs_remaining,
        'libero_player': libero_player,
        'libero_id': libero_id,
        'libero_out_ids': list(libero_out_ids),
        'timeouts_remaining': timeouts_remaining,
    }


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@login_required
def live_match_view(request, match_id):
    team = get_user_team(request.user)
    if not team:
        return redirect('dashboard')
    match, live = _get_live(match_id)
    players = team.players.filter(is_active=True)
    ctx = _build_context(live, team, players)
    ctx['high_contrast'] = request.session.get('high_contrast', False)
    return render(request, 'matches/live_match.html', ctx)


@login_required
def start_match(request, match_id):
    if not request.user.is_staff_role:
        messages.error(request, "Only staff can start a match.")
        return redirect('dashboard')
    match = get_object_or_404(Match, pk=match_id)
    team = get_user_team(request.user)
    if not team or match.team != team:
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    live, created = LiveMatch.objects.get_or_create(
        match=match,
        defaults={'current_set': 1, 'is_active': True, 'our_serve': True, 'current_rotation': 1}
    )
    if created:
        SetScore.objects.create(live_match=live, set_number=1)
    return redirect('live_match', match_id=match_id)


@login_required
@require_POST
def record_point(request, match_id):
    match, live = _get_live(match_id)
    data = json.loads(request.body)
    scored_by_us = data.get('us', True)
    tag_type = data.get('tag')
    player_id = data.get('player_id')

    set_score = _current_set_score(live)
    if scored_by_us:
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
    action = Action.objects.create(
        live_match=live,
        action_type=action_type,
        set_number=live.current_set,
        rotation=live.current_rotation,
        data={'our_score': set_score.our_score, 'opponent_score': set_score.opponent_score},
    )
    if tag_type and player_id:
        try:
            player = Player.objects.get(pk=player_id)
            ActionTag.objects.create(action=action, tag_type=tag_type, player=player)
        except Player.DoesNotExist:
            pass

    set_over = _check_set_over(live, set_score)
    match_over = False
    if set_over:
        our_sets, their_sets = _sets_won(live)
        if our_sets >= 3 or their_sets >= 3:
            match_over = True
            _end_match(live)
        else:
            _start_new_set(live)

    live.save()
    our_sets, their_sets = _sets_won(live)
    return JsonResponse({
        'ok': True,
        'our_score': set_score.our_score,
        'opponent_score': set_score.opponent_score,
        'our_serve': live.our_serve,
        'rotation': live.current_rotation,
        'current_set': live.current_set,
        'our_sets': our_sets,
        'their_sets': their_sets,
        'set_over': set_over,
        'match_over': match_over,
    })


def _check_set_over(live, set_score):
    our = set_score.our_score
    opp = set_score.opponent_score
    target = 15 if live.current_set == 5 else 25
    if (our >= target and our - opp >= 2) or (opp >= target and opp - our >= 2):
        set_score.is_complete = True
        set_score.save()
        return True
    return False


def _start_new_set(live):
    live.current_set += 1
    live.current_rotation = 1
    live.our_serve = not live.our_serve
    live.save()
    SetScore.objects.get_or_create(live_match=live, set_number=live.current_set)


def _end_match(live):
    live.is_active = False
    live.ended_at = timezone.now()
    live.save()
    live.match.status = 'completed'
    live.match.save()


@login_required
@require_POST
def manual_rotate(request, match_id):
    match, live = _get_live(match_id)
    data = json.loads(request.body)
    direction = data.get('direction', 'forward')
    if direction == 'forward':
        live.current_rotation = _rotation_after_sideout(live.current_rotation)
    else:
        live.current_rotation = ((live.current_rotation - 2) % 6) + 1
    live.save()
    Action.objects.create(
        live_match=live, action_type='rotation', set_number=live.current_set,
        rotation=live.current_rotation, data={'manual': True, 'direction': direction},
    )
    return JsonResponse({'ok': True, 'rotation': live.current_rotation})


@login_required
@require_POST
def make_substitution(request, match_id):
    match, live = _get_live(match_id)
    data = json.loads(request.body)
    player_in_id = data.get('player_in')
    player_out_id = data.get('player_out')
    is_libero = data.get('is_libero_swap', False)

    if not player_in_id or not player_out_id:
        return JsonResponse({'ok': False, 'error': 'Select both players.'}, status=400)

    if not is_libero:
        reg = _regular_subs(live)
        if len(reg) >= 6:
            return JsonResponse({'ok': False, 'error': 'Substitution limit (6) reached.'}, status=400)

    Action.objects.create(
        live_match=live, action_type='substitution', set_number=live.current_set,
        rotation=live.current_rotation,
        data={'player_in_id': player_in_id, 'player_out_id': player_out_id, 'is_libero_swap': is_libero},
    )
    subs_remaining = max(0, 6 - len(_regular_subs(live)))
    return JsonResponse({'ok': True, 'subs_remaining': subs_remaining})


@login_required
@require_POST
def libero_swap(request, match_id):
    match, live = _get_live(match_id)
    data = json.loads(request.body)
    libero_id = data.get('libero_id')
    replaced_id = data.get('replaced_id')
    swap_in = data.get('swap_in', True)
    if not libero_id or not replaced_id:
        return JsonResponse({'ok': False, 'error': 'Select libero and player.'}, status=400)
    Action.objects.create(
        live_match=live, action_type='libero_swap', set_number=live.current_set,
        rotation=live.current_rotation,
        data={'libero_id': libero_id, 'replaced_player_id': replaced_id, 'swap_in': swap_in},
    )
    return JsonResponse({'ok': True})


@login_required
@require_POST
def call_timeout(request, match_id):
    match, live = _get_live(match_id)
    used, remaining = _get_timeouts(live)
    if remaining <= 0:
        return JsonResponse({'ok': False, 'error': 'No timeouts remaining.'}, status=400)
    Action.objects.create(
        live_match=live, action_type='timeout', set_number=live.current_set,
        rotation=live.current_rotation, data={},
    )
    return JsonResponse({'ok': True, 'timeouts_remaining': remaining - 1})


@login_required
@require_POST
def set_lineup(request, match_id):
    match, live = _get_live(match_id)
    data = json.loads(request.body)
    positions = data.get('positions', {})
    Action.objects.create(
        live_match=live, action_type='lineup', set_number=live.current_set,
        rotation=live.current_rotation, data={'positions': positions},
    )
    return JsonResponse({'ok': True})


@login_required
def toggle_high_contrast(request, match_id):
    current = request.session.get('high_contrast', False)
    request.session['high_contrast'] = not current
    return redirect('live_match', match_id=match_id)


@login_required
def match_state(request, match_id):
    match, live = _get_live(match_id)
    team = get_user_team(request.user)
    set_score = _current_set_score(live)
    our_sets, their_sets = _sets_won(live)
    _, timeouts_remaining = _get_timeouts(live)
    subs_remaining = max(0, 6 - len(_regular_subs(live)))
    return JsonResponse({
        'our_score': set_score.our_score,
        'opponent_score': set_score.opponent_score,
        'our_serve': live.our_serve,
        'rotation': live.current_rotation,
        'current_set': live.current_set,
        'our_sets': our_sets,
        'their_sets': their_sets,
        'subs_remaining': subs_remaining,
        'timeouts_remaining': timeouts_remaining,
        'is_active': live.is_active,
    })
