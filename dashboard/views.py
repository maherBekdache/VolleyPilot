import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from io import BytesIO
from teams.views import get_user_team
from teams.models import Player, Team
from schedule.models import Match, Practice, AvailabilityResponse
from matches.models import LiveMatch, Action, ActionTag, SetScore
from django.db.models import Count, Q, Sum, F


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
    })


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

