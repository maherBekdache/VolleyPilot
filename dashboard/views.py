import json
import hashlib
import urllib.error
import urllib.request
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import timedelta
from io import BytesIO
from teams.views import get_user_team
from teams.models import Player, Team, TeamAnnouncement
from schedule.models import Match, Practice, AvailabilityResponse
from matches.models import LiveMatch, Action, ActionTag, SetScore
from django.db.models import Count, Q, Sum, F
from .ml import anonymized_dataset_for_team


@login_required
def dashboard_view(request):
    team = get_user_team(request.user)
    if not team and not request.user.is_fan_role:
        if request.user.is_staff_role:
            return redirect('team_create')
        return render(request, 'teams/no_team.html')

    # Fans see league-wide data
    if request.user.is_fan_role:
        today = timezone.now().date()
        from schedule.models import Match as MatchModel
        upcoming_matches = MatchModel.objects.filter(date__gte=today, status='scheduled').order_by('date', 'time')[:5]
        all_teams = Team.objects.all()
        return render(request, 'dashboard/fan_dashboard.html', {
            'upcoming_matches': upcoming_matches,
            'all_teams': all_teams,
        })

    today = timezone.now().date()
    player_count = team.players.filter(is_active=True).count()
    upcoming_matches = team.matches.filter(date__gte=today, status='scheduled')[:3]
    recent_results = team.matches.filter(status='completed').order_by('-date')[:3]
    week_start = today
    week_end = today + timedelta(days=7)
    week_practices = team.practices.filter(date__gte=week_start, date__lte=week_end, status='scheduled')
    wins = 0
    losses = 0
    results_data = []
    for m in team.matches.filter(status='completed').order_by('-date'):
        live = getattr(m, 'live', None)
        if live:
            our_sets = live.set_scores.filter(is_complete=True, our_score__gt=F('opponent_score')).count()
            their_sets = live.set_scores.filter(is_complete=True, opponent_score__gt=F('our_score')).count()
            result = 'win' if our_sets > their_sets else 'loss'
            if result == 'win':
                wins += 1
            else:
                losses += 1
            set_scores = [f"{s.our_score}-{s.opponent_score}" for s in live.set_scores.filter(is_complete=True)]
            results_data.append({
                'match': m, 'result': result,
                'our_sets': our_sets, 'their_sets': their_sets,
                'set_scores': set_scores,
            })
    total_matches = wins + losses
    win_rate = round((wins / total_matches * 100)) if total_matches > 0 else 0
    # Availability responses for current player
    pending_responses = []
    if request.user.is_player_role:
        player = Player.objects.filter(user=request.user, team=team).first()
        if player:
            pending_responses = AvailabilityResponse.objects.filter(
                player=player, status='pending'
            ).select_related('request')

    # Calendar events
    cal_matches = team.matches.exclude(status='cancelled')
    cal_practices = team.practices.exclude(status='cancelled')
    calendar_events = []
    for m in cal_matches:
        calendar_events.append({
            'date': m.date.isoformat(),
            'type': 'match',
            'title': ('vs' if m.is_home else '@') + ' ' + m.opponent,
            'time': m.time.strftime('%I:%M %p'),
            'is_home': m.is_home,
        })
    for p in cal_practices:
        calendar_events.append({
            'date': p.date.isoformat(),
            'type': 'practice',
            'title': 'Practice: ' + p.focus,
            'time': p.time.strftime('%I:%M %p'),
        })

    rotation_summary = []
    for rot in range(1, 7):
        won = Action.objects.filter(
            live_match__match__team=team,
            action_type__in=['point_won', 'sideout'],
            rotation=rot,
            is_undone=False,
        ).count()
        lost = Action.objects.filter(
            live_match__match__team=team,
            action_type='point_lost',
            rotation=rot,
            is_undone=False,
        ).count()
        total = won + lost
        rotation_summary.append({
            'rotation': rot,
            'won': won,
            'lost': lost,
            'pct': round(won / total * 100) if total else 0,
        })
    strongest_rotation = max(rotation_summary, key=lambda item: item['pct'], default=None)
    recent_announcements = TeamAnnouncement.objects.filter(team=team).order_by('-created_at')[:3]

    return render(request, 'dashboard/index.html', {
        'team': team,
        'player_count': player_count,
        'upcoming_matches': upcoming_matches,
        'week_practices': week_practices,
        'win_rate': win_rate,
        'wins': wins,
        'losses': losses,
        'total_matches': total_matches,
        'results_data': results_data[:3],
        'pending_responses': pending_responses,
        'rotation_summary': rotation_summary,
        'strongest_rotation': strongest_rotation,
        'calendar_events_json': json.dumps(calendar_events),
        'recent_announcements': recent_announcements,
    })


def _completed_team_lives(team):
    return LiveMatch.objects.filter(
        match__team=team,
        match__status='completed',
    ).select_related('match').prefetch_related('set_scores')


def _win_loss_for_live(live):
    our_sets = live.set_scores.filter(is_complete=True, our_score__gt=F('opponent_score')).count()
    their_sets = live.set_scores.filter(is_complete=True, opponent_score__gt=F('our_score')).count()
    return our_sets, their_sets, our_sets > their_sets


def _rotation_loss_patterns(team):
    losses_by_rotation = {rot: 0 for rot in range(1, 7)}
    totals_by_rotation = {rot: 0 for rot in range(1, 7)}

    actions = Action.objects.filter(
        live_match__match__team=team,
        is_undone=False,
        action_type__in=['point_won', 'sideout', 'point_lost'],
        rotation__in=[1, 2, 3, 4, 5, 6],
    )
    for action in actions:
        rot = action.rotation
        totals_by_rotation[rot] += 1
        if action.action_type == 'point_lost':
            losses_by_rotation[rot] += 1

    rows = []
    for rot in range(1, 7):
        total = totals_by_rotation[rot]
        losses = losses_by_rotation[rot]
        loss_pct = round((losses / total) * 100, 1) if total else 0.0
        rows.append({
            'rotation': rot,
            'lost_points': losses,
            'total_points': total,
            'loss_pct': loss_pct,
        })
    rows.sort(key=lambda x: (x['loss_pct'], x['lost_points']), reverse=True)

    top = rows[0] if rows else None
    pattern_note = 'No action data yet.'
    if top and top['total_points'] > 0:
        pattern_note = (
            f"Rotation {top['rotation']} has the highest loss share "
            f"({top['loss_pct']}% across {top['total_points']} tracked rallies)."
        )
    return rows, pattern_note


def _training_recommendations(team, rotation_rows):
    recs = []
    worst = rotation_rows[0] if rotation_rows else None
    if worst and worst['loss_pct'] >= 55 and worst['total_points'] >= 10:
        recs.append({
            'title': f"Rotation {worst['rotation']} stabilization",
            'detail': (
                'Run serve-receive reps starting from this rotation, followed by first-ball '
                'sideout drills under time pressure.'
            ),
            'priority': 'High',
        })

    tags = ActionTag.objects.filter(action__live_match__match__team=team)
    serve_errors = tags.filter(tag_type='serve_error').count()
    attack_errors = tags.filter(tag_type='attack_error').count()
    digs = tags.filter(tag_type='dig').count()
    kills = tags.filter(tag_type='kill').count()

    if serve_errors >= max(6, kills // 2):
        recs.append({
            'title': 'Serving consistency block',
            'detail': 'Add a 15-minute zone-serving ladder with miss penalties and recovery routine.',
            'priority': 'High',
        })
    if attack_errors >= max(6, kills // 2):
        recs.append({
            'title': 'High-ball decision training',
            'detail': 'Use constrained scrimmage where hitters must choose roll/line/hand tools over low-percentage swings.',
            'priority': 'Medium',
        })
    if digs <= max(8, kills // 3):
        recs.append({
            'title': 'Backcourt reaction and platform control',
            'detail': 'Schedule repetitive dig channels and blocker-touch read drills twice weekly.',
            'priority': 'Medium',
        })

    if not recs:
        recs.append({
            'title': 'Maintain current training cycle',
            'detail': 'No major statistical weakness detected yet; keep balanced technical and tactical sessions.',
            'priority': 'Low',
        })

    return recs


def _opponent_insights(team):
    lives = list(_completed_team_lives(team))
    by_opp = {}
    for live in lives:
        opp = (live.match.opponent or '').strip() or 'Unknown Opponent'
        bucket = by_opp.setdefault(opp, {'wins': 0, 'losses': 0, 'matches': 0})
        _, _, won = _win_loss_for_live(live)
        bucket['matches'] += 1
        if won:
            bucket['wins'] += 1
        else:
            bucket['losses'] += 1

    rows = []
    for opp, stats in by_opp.items():
        matches = stats['matches']
        win_pct = round((stats['wins'] / matches) * 100) if matches else 0
        rows.append({
            'opponent': opp,
            'matches': matches,
            'wins': stats['wins'],
            'losses': stats['losses'],
            'win_pct': win_pct,
        })
    rows.sort(key=lambda r: r['matches'], reverse=True)

    top = rows[0] if rows else None
    note = 'No completed opponent history yet.'
    if top:
        note = (
            f"Most faced opponent: {top['opponent']} ({top['wins']}-{top['losses']}, "
            f"{top['win_pct']}% win rate)."
        )
    return rows, note


def _specific_opponent_analytics(team, opponent_name):
    lives = _completed_team_lives(team).filter(match__opponent__iexact=opponent_name)
    lives = list(lives)
    if not lives:
        return None

    wins = losses = 0
    action_won = action_lost = 0
    sideout_won = sideout_chances = 0
    errors = {'serve_error': 0, 'attack_error': 0}
    rotation_losses = {r: 0 for r in range(1, 7)}

    for live in lives:
        _, _, won = _win_loss_for_live(live)
        wins += 1 if won else 0
        losses += 0 if won else 1

        actions = Action.objects.filter(
            live_match=live,
            is_undone=False,
            action_type__in=['point_won', 'sideout', 'point_lost'],
        )
        for a in actions:
            if a.action_type in ('point_won', 'sideout'):
                action_won += 1
            elif a.action_type == 'point_lost':
                action_lost += 1
                if a.rotation in rotation_losses:
                    rotation_losses[a.rotation] += 1

            our_serve = (a.data or {}).get('our_serve', True)
            if not our_serve:
                sideout_chances += 1
                if a.action_type in ('point_won', 'sideout'):
                    sideout_won += 1

        tags = ActionTag.objects.filter(action__live_match=live)
        errors['serve_error'] += tags.filter(tag_type='serve_error').count()
        errors['attack_error'] += tags.filter(tag_type='attack_error').count()

    matches = len(lives)
    win_pct = round((wins / matches) * 100) if matches else 0
    total_rallies = action_won + action_lost
    rally_win_pct = round((action_won / total_rallies) * 100, 1) if total_rallies else 0.0
    sideout_pct = round((sideout_won / sideout_chances) * 100, 1) if sideout_chances else 0.0

    worst_rotation = max(rotation_losses.items(), key=lambda item: item[1])
    worst_rotation_label = f"R{worst_rotation[0]}" if worst_rotation[1] > 0 else 'N/A'

    return {
        'opponent': opponent_name,
        'matches': matches,
        'wins': wins,
        'losses': losses,
        'win_rate': win_pct,
        'rally_win_pct': rally_win_pct,
        'sideout_pct': sideout_pct,
        'serve_errors': errors['serve_error'],
        'attack_errors': errors['attack_error'],
        'worst_rotation': worst_rotation_label,
    }


def _predictive_summary(team, opponent_rows):
    # Future-feature style prediction heuristic (VT-106)
    lives = list(_completed_team_lives(team))
    wins = 0
    losses = 0
    for live in lives:
        _, _, won = _win_loss_for_live(live)
        wins += 1 if won else 0
        losses += 0 if won else 1
    total = wins + losses

    sideout_actions = Action.objects.filter(
        live_match__match__team=team,
        is_undone=False,
        action_type__in=['point_won', 'sideout', 'point_lost'],
    )
    so_chances = 0
    so_wins = 0
    for a in sideout_actions:
        our_serve = (a.data or {}).get('our_serve', True)
        if not our_serve:
            so_chances += 1
            if a.action_type in ('point_won', 'sideout'):
                so_wins += 1
    sideout_pct = (so_wins / so_chances * 100) if so_chances else 50.0

    base = 0.5
    if total:
        base += ((wins - losses) / total) * 0.22
    base += ((sideout_pct - 50.0) / 50.0) * 0.18

    next_match = team.matches.filter(status='scheduled', date__gte=timezone.now().date()).order_by('date', 'time').first()
    if next_match:
        row = next((r for r in opponent_rows if r['opponent'].lower() == next_match.opponent.lower()), None)
        if row and row['matches']:
            base += ((row['wins'] - row['losses']) / row['matches']) * 0.12

    probability = max(0.05, min(0.95, base))
    confidence = 'Low'
    if total >= 8:
        confidence = 'Medium'
    if total >= 16:
        confidence = 'High'

    return {
        'next_match': next_match,
        'win_probability_pct': round(probability * 100, 1),
        'confidence': confidence,
        'inputs': {
            'total_completed_matches': total,
            'season_record': f'{wins}-{losses}',
            'overall_sideout_pct': round(sideout_pct, 1),
        },
    }


def _get_opponent_public_profile(opponent_name):
    """
    Retrieve public profile data for an opponent team (heights, stats).
    Returns dict with opponent_stats or empty dict if team not found.
    """
    try:
        opponent_team = Team.objects.filter(name__iexact=opponent_name.strip()).first()
        if not opponent_team:
            return {}
        
        active_players = opponent_team.players.filter(is_active=True)
        player_count = active_players.count()
        
        # Calculate average height from players with height data
        heights_data = [p.height for p in active_players if p.height and p.height.strip()]
        avg_height = None
        if heights_data:
            try:
                # Parse heights like "6'2"" or "6'2\"" and convert to inches for averaging
                total_inches = 0
                valid_heights = 0
                for h in heights_data:
                    # Simple parsing: try to extract numeric values
                    h = h.replace('"', '').replace("'", "").strip()
                    if h:
                        try:
                            # Assume format "6'2" -> split and parse
                            parts = h.split()
                            if len(parts) >= 1:
                                feet_val = float(parts[0])
                                inches_val = float(parts[1]) if len(parts) > 1 else 0
                                total_inches += (feet_val * 12 + inches_val)
                                valid_heights += 1
                        except (ValueError, IndexError):
                            pass
                
                if valid_heights > 0:
                    avg_inches = total_inches / valid_heights
                    avg_feet = int(avg_inches // 12)
                    avg_inches_remainder = int(avg_inches % 12)
                    avg_height = f"{avg_feet}'{avg_inches_remainder}\""
            except Exception:
                # If height parsing fails, just skip avg_height
                pass
        
        # Opponent team stats (overall record, player composition)
        completed_matches = opponent_team.matches.filter(status='completed')
        opp_wins = 0
        opp_losses = 0
        for m in completed_matches:
            live = getattr(m, 'live', None)
            if live:
                our_sets = live.set_scores.filter(is_complete=True, our_score__gt=F('opponent_score')).count()
                their_sets = live.set_scores.filter(is_complete=True, opponent_score__gt=F('our_score')).count()
                if our_sets > their_sets:
                    opp_wins += 1
                else:
                    opp_losses += 1
        
        return {
            'player_count': player_count,
            'avg_height': avg_height,
            'overall_wins': opp_wins,
            'overall_losses': opp_losses,
            'positions': list(active_players.values_list('position', flat=True).distinct()),
        }
    except Exception:
        return {}


def _anonymized_dataset(team):
    return anonymized_dataset_for_team(team)


@login_required
def ai_analytics_view(request):
    team = get_user_team(request.user)
    if request.user.role not in ('coach', 'assistant'):
        return redirect('dashboard')
    if not team or request.user.is_fan_role:
        if request.user.is_staff_role:
            return redirect('team_create')
        return render(request, 'teams/no_team.html')

    rotation_rows, rotation_note = _rotation_loss_patterns(team)
    recommendations = _training_recommendations(team, rotation_rows)
    opponent_rows, opponent_note = _opponent_insights(team)
    predictive = _predictive_summary(team, opponent_rows)
    dataset_preview = _anonymized_dataset(team)

    selected_opponent = (request.GET.get('opponent') or 'general').strip()
    opponent_options = [row['opponent'] for row in opponent_rows]
    if selected_opponent != 'general' and selected_opponent not in opponent_options:
        selected_opponent = 'general'

    opponent_specific = None
    if selected_opponent != 'general':
        opponent_specific = _specific_opponent_analytics(team, selected_opponent)

    return render(request, 'dashboard/ai_analytics.html', {
        'team': team,
        'rotation_rows': rotation_rows,
        'rotation_note': rotation_note,
        'recommendations': recommendations,
        'opponent_rows': opponent_rows,
        'opponent_note': opponent_note,
        'predictive': predictive,
        'dataset_preview_count': dataset_preview['total_samples'],
        'opponent_options': opponent_options,
        'selected_opponent': selected_opponent,
        'opponent_specific': opponent_specific,
    })


@login_required
def export_anonymized_dataset(request):
    team = get_user_team(request.user)
    if request.user.role not in ('coach', 'assistant'):
        return redirect('dashboard')
    if not team or request.user.is_fan_role:
        return redirect('dashboard')

    payload = _anonymized_dataset(team)
    response = HttpResponse(json.dumps(payload, indent=2), content_type='application/json')
    response['Content-Disposition'] = 'attachment; filename="anonymized_match_data.json"'
    return response



def _volypilot_context(team, rotation_rows=None, recommendations=None, opponent_rows=None, predictive=None):
    rotation_rows = rotation_rows if rotation_rows is not None else _rotation_loss_patterns(team)[0]
    recommendations = recommendations if recommendations is not None else _training_recommendations(team, rotation_rows)
    opponent_rows = opponent_rows if opponent_rows is not None else _opponent_insights(team)[0]
    predictive = predictive if predictive is not None else _predictive_summary(team, opponent_rows)
    return {
        'team': team.name,
        'worst_rotations': rotation_rows[:3],
        'training_recommendations': recommendations[:5],
        'opponents': opponent_rows[:5],
        'predictive_summary': predictive,
    }


def _local_volypilot_reply(message, context):
    worst = context['worst_rotations'][0] if context['worst_rotations'] else None
    top_rec = context['training_recommendations'][0] if context['training_recommendations'] else None
    predictive = context.get('predictive_summary') or {}
    next_match = predictive.get('next_match')
    parts = ["Volypilot local insight:"]
    if worst and worst.get('total_points', 0):
        parts.append(
            f"Your biggest current risk is Rotation {worst['rotation']}, with "
            f"{worst['lost_points']} lost points and a {worst['loss_pct']}% loss share."
        )
    else:
        parts.append("There is not enough tracked rotation data yet, so keep collecting rally actions during live matches.")
    if top_rec:
        parts.append(f"Recommended focus: {top_rec['title']} — {top_rec['detail']}")
    if next_match:
        parts.append(
            f"For the next match vs {next_match.opponent}, the heuristic win probability is "
            f"{predictive['win_probability_pct']}% with {predictive['confidence']} confidence."
        )
    if 'opponent' in message.lower() and context['opponents']:
        opp = context['opponents'][0]
        parts.append(f"Most useful opponent reference: {opp['opponent']} ({opp['wins']}-{opp['losses']} historical record).")
    return " ".join(parts)


def _call_volypilot_model(message, context):
    if not settings.VOLLEYPILOT_AI_API_KEY:
        return _local_volypilot_reply(message, context), 'local'

    payload = {
        'model': settings.VOLLEYPILOT_AI_MODEL,
        'temperature': 0.2,
        'max_tokens': 450,
        'messages': [
            {
                'role': 'system',
                'content': (
                    'You are Volypilot, a concise volleyball analytics assistant for coaches. '
                    'Use only the provided VolleyPilot context. Give tactical, practical, non-medical training guidance. '
                    'Do not invent player names or personal information.'
                ),
            },
            {
                'role': 'user',
                'content': 'Context JSON:\n' + json.dumps(context, default=str) + '\n\nCoach question:\n' + message,
            },
        ],
    }
    request = urllib.request.Request(
        settings.VOLLEYPILOT_AI_API_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {settings.VOLLEYPILOT_AI_API_KEY}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.VOLLEYPILOT_AI_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode('utf-8'))
        reply = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        return (reply or _local_volypilot_reply(message, context)), 'model'
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        print("VOLYPILOT GEMINI HTTP ERROR:", exc.code, error_body)
        return _local_volypilot_reply(message, context), 'local_fallback'

    except Exception as exc:
        print("VOLYPILOT GEMINI ERROR:", repr(exc))
        return _local_volypilot_reply(message, context), 'local_fallback'


@require_POST
@login_required
def volypilot_chat(request):
    team = get_user_team(request.user)
    if request.user.role not in ('coach', 'assistant'):
        return JsonResponse({'ok': False, 'error': 'Permission denied.'}, status=403)
    if not team or request.user.is_fan_role:
        return JsonResponse({'ok': False, 'error': 'No team found.'}, status=400)
    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON.'}, status=400)
    message = (body.get('message') or '').strip()[:1200]
    if not message:
        return JsonResponse({'ok': False, 'error': 'Ask Volypilot a question first.'}, status=400)

    rotation_rows, _ = _rotation_loss_patterns(team)
    recommendations = _training_recommendations(team, rotation_rows)
    opponent_rows, _ = _opponent_insights(team)
    predictive = _predictive_summary(team, opponent_rows)
    context = _volypilot_context(team, rotation_rows, recommendations, opponent_rows, predictive)
    reply, source = _call_volypilot_model(message, context)
    return JsonResponse({'ok': True, 'reply': reply, 'source': source})

@login_required
def statistics_view(request):
    user_team = get_user_team(request.user)
    if not user_team and not request.user.is_fan_role:
        if request.user.is_staff_role:
            return redirect('team_create')
        return render(request, 'teams/no_team.html')

    # Fans default to league-wide scope
    default_scope = 'league' if request.user.is_fan_role else 'team'
    scope = request.GET.get('scope', default_scope)
    team_id = request.GET.get('team', '')
    search = request.GET.get('search', '')
    player_id = request.GET.get('player', '')

    all_teams = Team.objects.all()

    # Determine which players to show
    if player_id:
        # Single player view (linked from roster)
        single_player = Player.objects.filter(pk=player_id, is_active=True).first()
        if single_player:
            players = Player.objects.filter(pk=player_id)
            scope = 'player'
        else:
            players = Player.objects.none()
    elif scope == 'league':
        players = Player.objects.filter(is_active=True)
        if team_id:
            players = players.filter(team_id=team_id)
        if search:
            players = players.filter(name__icontains=search)
    else:
        # Default: own team
        players = user_team.players.filter(is_active=True)
        if search:
            players = players.filter(name__icontains=search)

    # Aggregate stats from ActionTags
    player_stats = []
    for p in players:
        tags = ActionTag.objects.filter(player=p)
        kills = tags.filter(tag_type='kill').count()
        blocks = tags.filter(tag_type='block').count()
        aces = tags.filter(tag_type='ace').count()
        digs = tags.filter(tag_type='dig').count()
        assists = tags.filter(tag_type='assist').count()
        errors = tags.filter(tag_type__in=['serve_error', 'attack_error']).count()
        player_stats.append({
            'player': p, 'kills': kills, 'blocks': blocks,
            'aces': aces, 'digs': digs, 'assists': assists, 'errors': errors,
        })
    total_kills = sum(s['kills'] for s in player_stats)
    total_blocks = sum(s['blocks'] for s in player_stats)
    total_aces = sum(s['aces'] for s in player_stats)
    total_digs = sum(s['digs'] for s in player_stats)
    # Top performers
    top_kills = sorted(player_stats, key=lambda x: x['kills'], reverse=True)[:5]
    top_blocks = sorted(player_stats, key=lambda x: x['blocks'], reverse=True)[:5]
    top_aces = sorted(player_stats, key=lambda x: x['aces'], reverse=True)[:5]
    top_digs = sorted(player_stats, key=lambda x: x['digs'], reverse=True)[:5]
    # Rotation stats across all completed matches
    rotation_qs = Action.objects.filter(is_undone=False)
    if scope != 'league' or not team_id:
        rotation_qs = rotation_qs.filter(live_match__match__team=user_team)
    else:
        rotation_qs = rotation_qs.filter(live_match__match__team_id=team_id)
    rotation_stats = []
    for rot in range(1, 7):
        won = rotation_qs.filter(action_type='point_won', rotation=rot).count()
        lost = rotation_qs.filter(action_type='point_lost', rotation=rot).count()
        total = won + lost
        sideout_pct = round(won / total * 100) if total > 0 else 0
        rotation_stats.append({
            'rotation': rot, 'won': won, 'lost': lost,
            'net': won - lost, 'sideout_pct': sideout_pct,
        })

    return render(request, 'dashboard/statistics.html', {
        'team': user_team,
        'player_stats': sorted(player_stats, key=lambda x: x['kills'], reverse=True),
        'total_kills': total_kills, 'total_blocks': total_blocks,
        'total_aces': total_aces, 'total_digs': total_digs,
        'top_kills': top_kills, 'top_blocks': top_blocks,
        'top_aces': top_aces, 'top_digs': top_digs,
        'rotation_stats': rotation_stats,
        'scope': scope, 'search': search, 'team_id': team_id,
        'player_id': player_id, 'all_teams': all_teams,
        'single_player': single_player if player_id else None,
    })


@login_required
def results_view(request):
    team = get_user_team(request.user)
    if not team and not request.user.is_fan_role:
        return redirect('team_create')
    filter_type = request.GET.get('filter', 'all')
    if request.user.is_fan_role:
        from schedule.models import Match as MatchQ
        completed_matches = MatchQ.objects.filter(status='completed').order_by('-date')
    else:
        completed_matches = team.matches.filter(status='completed').order_by('-date')
    results_data = []
    wins = 0
    losses = 0
    for m in completed_matches:
        live = getattr(m, 'live', None)
        if live:
            our_sets = live.set_scores.filter(is_complete=True, our_score__gt=F('opponent_score')).count()
            their_sets = live.set_scores.filter(is_complete=True, opponent_score__gt=F('our_score')).count()
            result = 'win' if our_sets > their_sets else 'loss'
            if result == 'win':
                wins += 1
            else:
                losses += 1
            set_scores = [f"{s.our_score}-{s.opponent_score}" for s in live.set_scores.filter(is_complete=True)]
            results_data.append({
                'match': m, 'result': result,
                'our_sets': our_sets, 'their_sets': their_sets,
                'set_scores': set_scores,
            })
    if filter_type == 'win':
        results_data = [r for r in results_data if r['result'] == 'win']
    elif filter_type == 'loss':
        results_data = [r for r in results_data if r['result'] == 'loss']
    total = wins + losses
    win_rate = round((wins / total * 100)) if total > 0 else 0
    return render(request, 'dashboard/results.html', {
        'results_data': results_data, 'wins': wins, 'losses': losses,
        'total': total, 'win_rate': win_rate, 'filter_type': filter_type,
    })


@login_required
def export_stats_csv(request):
    import csv
    from django.http import HttpResponse
    team = get_user_team(request.user)
    if not team:
        return redirect('dashboard')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="team_stats.csv"'
    writer = csv.writer(response)
    writer.writerow(['Player', 'Position', 'Jersey #', 'Kills', 'Blocks', 'Aces', 'Digs', 'Assists', 'Errors'])
    for p in team.players.filter(is_active=True):
        tags = ActionTag.objects.filter(player=p)
        writer.writerow([
            p.name, p.position, p.jersey_number,
            tags.filter(tag_type='kill').count(),
            tags.filter(tag_type='block').count(),
            tags.filter(tag_type='ace').count(),
            tags.filter(tag_type='dig').count(),
            tags.filter(tag_type='assist').count(),
            tags.filter(tag_type__in=['serve_error', 'attack_error']).count(),
        ])
    return response


def _build_simple_pdf(lines):
    def escape(text):
        return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

    content_lines = ['BT /F1 12 Tf 50 780 Td 14 TL']
    first = True
    for raw_line in lines:
        line = escape(raw_line)
        if first:
            content_lines.append(f'({line}) Tj')
            first = False
        else:
            content_lines.append(f'T* ({line}) Tj')
    content_lines.append('ET')
    stream = '\n'.join(content_lines).encode('latin-1', errors='replace')

    buffer = BytesIO()
    buffer.write(b'%PDF-1.4\n')
    offsets = []

    def write_obj(number, body):
        offsets.append(buffer.tell())
        buffer.write(f'{number} 0 obj\n'.encode('ascii'))
        if isinstance(body, bytes):
            buffer.write(body)
        else:
            buffer.write(body.encode('latin-1'))
        buffer.write(b'\nendobj\n')

    write_obj(1, '<< /Type /Catalog /Pages 2 0 R >>')
    write_obj(2, '<< /Type /Pages /Kids [3 0 R] /Count 1 >>')
    write_obj(3, '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>')
    write_obj(4, f'<< /Length {len(stream)} >>\nstream\n'.encode('ascii') + stream + b'\nendstream')
    write_obj(5, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')

    xref_start = buffer.tell()
    buffer.write(f'xref\n0 {len(offsets) + 1}\n'.encode('ascii'))
    buffer.write(b'0000000000 65535 f \n')
    for offset in offsets:
        buffer.write(f'{offset:010d} 00000 n \n'.encode('ascii'))
    buffer.write(
        f'trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF'.encode('ascii')
    )
    return buffer.getvalue()


@login_required
def export_stats_pdf(request):
    from django.http import HttpResponse

    team = get_user_team(request.user)
    if not team:
        return redirect('dashboard')

    lines = [f'VolleyPilot Team Statistics - {team.name}', '']
    for player in team.players.filter(is_active=True).order_by('jersey_number'):
        tags = ActionTag.objects.filter(player=player)
        lines.append(
            f'#{player.jersey_number} {player.name} | Kills {tags.filter(tag_type="kill").count()} | '
            f'Blocks {tags.filter(tag_type="block").count()} | Aces {tags.filter(tag_type="ace").count()} | '
            f'Digs {tags.filter(tag_type="dig").count()} | Assists {tags.filter(tag_type="assist").count()} | '
            f'Errors {tags.filter(tag_type__in=["serve_error", "attack_error"]).count()}'
        )

    response = HttpResponse(_build_simple_pdf(lines), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="team_stats.pdf"'
    return response

