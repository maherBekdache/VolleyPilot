from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Match, Practice, AvailabilityRequest, AvailabilityResponse
from .forms import MatchForm, PracticeForm
from teams.views import get_user_team


@login_required
def schedule_view(request):
    team = get_user_team(request.user)
    if not team and not request.user.is_fan_role:
        return redirect('team_create')
    today = timezone.now().date()
    player_profile = None
    if team and request.user.is_player_role:
        from teams.models import Player
        player_profile = Player.objects.filter(team=team, user=request.user).first()
    if request.user.is_fan_role:
        matches = Match.objects.all()
        practices = Practice.objects.none()
    else:
        matches = team.matches.all()
        practices = team.practices.all()
    events = []
    for m in matches:
        availability_request = m.availability_requests.order_by('-sent_at').first()
        response = None
        if availability_request and player_profile:
            response = availability_request.responses.filter(player=player_profile).first()
        prefix = f"{m.team.name} " if request.user.is_fan_role else ""
        events.append({
            'type': 'game', 'id': m.id, 'date': m.date, 'time': m.time,
            'title': f"{prefix}{m.display_title}: {'vs' if m.is_home else '@'} {m.opponent}",
            'location': m.location, 'is_home': m.is_home, 'status': m.status,
            'avail_request': bool(availability_request),
            'avail_request_id': availability_request.id if availability_request else None,
            'availability_response': response,
            'past': m.date < today,
            'ruleset': m.get_ruleset_display(),
            'can_start': (not request.user.is_fan_role and request.user.is_staff_role and m.status == 'scheduled'),
            'has_live': hasattr(m, 'live'),
        })
    for p in practices:
        availability_request = p.availability_requests.order_by('-sent_at').first()
        response = None
        if availability_request and player_profile:
            response = availability_request.responses.filter(player=player_profile).first()
        events.append({
            'type': 'practice', 'id': p.id, 'date': p.date, 'time': p.time,
            'title': f"Practice: {p.focus}",
            'location': p.location, 'status': p.status,
            'avail_request': bool(availability_request),
            'avail_request_id': availability_request.id if availability_request else None,
            'availability_response': response,
            'past': p.date < today,
        })
    events.sort(key=lambda e: (e['date'], e['time']))
    tab = request.GET.get('tab', 'upcoming')
    if tab == 'completed':
        filtered = [e for e in events if e['past'] or e['status'] == 'completed']
    else:
        filtered = [e for e in events if not e['past'] and e['status'] != 'completed']
    return render(request, 'schedule/schedule.html', {
        'events': filtered, 'team': team, 'tab': tab,
    })


@login_required
def match_create_view(request):
    team = get_user_team(request.user)
    if not team or not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('schedule')
    if request.method == 'POST':
        form = MatchForm(request.POST)
        if form.is_valid():
            match = form.save(commit=False)
            match.team = team
            match.created_by = request.user
            match.save()
            messages.success(request, 'Match event created successfully.')
            return redirect('schedule')
    else:
        form = MatchForm()
    return render(request, 'schedule/event_form.html', {'form': form, 'event_type': 'Match'})


@login_required
def match_edit_view(request, pk):
    team = get_user_team(request.user)
    match = get_object_or_404(Match, pk=pk, team=team)
    if not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('schedule')
    if request.method == 'POST':
        form = MatchForm(request.POST, instance=match)
        if form.is_valid():
            form.save()
            messages.success(request, 'Match updated.')
            return redirect('schedule')
    else:
        form = MatchForm(instance=match)
    return render(request, 'schedule/event_form.html', {'form': form, 'event_type': 'Match'})


@login_required
def match_cancel_view(request, pk):
    team = get_user_team(request.user)
    match = get_object_or_404(Match, pk=pk, team=team)
    if not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('schedule')
    if request.method == 'POST':
        match.status = 'cancelled'
        match.save(update_fields=['status'])
        messages.success(request, 'Match cancelled.')
        return redirect('schedule')
    return render(request, 'schedule/confirm_cancel.html', {'event': match, 'event_type': 'Match'})


@login_required
def practice_create_view(request):
    team = get_user_team(request.user)
    if not team or not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('schedule')
    if request.method == 'POST':
        form = PracticeForm(request.POST)
        if form.is_valid():
            practice = form.save(commit=False)
            practice.team = team
            practice.created_by = request.user
            practice.save()
            messages.success(request, 'Practice session created.')
            return redirect('schedule')
    else:
        form = PracticeForm()
    return render(request, 'schedule/event_form.html', {'form': form, 'event_type': 'Practice'})


@login_required
def practice_edit_view(request, pk):
    team = get_user_team(request.user)
    practice = get_object_or_404(Practice, pk=pk, team=team)
    if not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('schedule')
    if request.method == 'POST':
        form = PracticeForm(request.POST, instance=practice)
        if form.is_valid():
            form.save()
            messages.success(request, 'Practice updated.')
            return redirect('schedule')
    else:
        form = PracticeForm(instance=practice)
    return render(request, 'schedule/event_form.html', {'form': form, 'event_type': 'Practice'})


@login_required
def practice_detail_view(request, pk):
    team = get_user_team(request.user)
    practice = get_object_or_404(Practice, pk=pk, team=team)
    practice_drills = practice.practice_drills.select_related('drill')
    return render(request, 'schedule/practice_detail.html', {
        'practice': practice,
        'practice_drills': practice_drills,
    })


@login_required
def request_availability_view(request, event_type, pk):
    team = get_user_team(request.user)
    if not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('schedule')
    if event_type == 'match':
        event = get_object_or_404(Match, pk=pk, team=team)
        avail_req, created = AvailabilityRequest.objects.get_or_create(
            event_type='match', match=event,
            defaults={'sent_by': request.user}
        )
    else:
        event = get_object_or_404(Practice, pk=pk, team=team)
        avail_req, created = AvailabilityRequest.objects.get_or_create(
            event_type='practice', practice=event,
            defaults={'sent_by': request.user}
        )
    players = team.players.filter(is_active=True)
    for player in players:
        AvailabilityResponse.objects.get_or_create(request=avail_req, player=player)
    if created:
        messages.success(request, 'Availability request sent to all players.')
    else:
        messages.info(request, 'Availability request was already created for this event.')
    return redirect('schedule')


@login_required
def availability_respond_view(request, pk):
    response = get_object_or_404(AvailabilityResponse, pk=pk)
    if response.player.user_id != request.user.id:
        messages.error(request, 'You can only update your own availability response.')
        return redirect('schedule')
    if request.method == 'POST':
        status = request.POST.get('status')
        if status in ('available', 'unavailable', 'maybe'):
            response.status = status
            response.responded_at = timezone.now()
            response.save()
            messages.success(request, 'Availability updated.')
    return redirect('schedule')


@login_required
def availability_summary_view(request, event_type, pk):
    team = get_user_team(request.user)
    if event_type == 'match':
        event = get_object_or_404(Match, pk=pk, team=team)
        avail_req = event.availability_requests.first()
    else:
        event = get_object_or_404(Practice, pk=pk, team=team)
        avail_req = event.availability_requests.first()
    responses = avail_req.responses.select_related('player') if avail_req else []
    summary = {'available': 0, 'unavailable': 0, 'maybe': 0, 'pending': 0}
    for r in responses:
        summary[r.status] = summary.get(r.status, 0) + 1
    return render(request, 'schedule/availability_summary.html', {
        'event': event, 'event_type': event_type,
        'responses': responses, 'summary': summary,
    })
