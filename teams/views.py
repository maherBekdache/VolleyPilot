from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count
from django.core.mail import send_mail
from django.urls import reverse
from .models import Team, Player, TeamInvitation, TeamMembership
from .forms import TeamForm, PlayerForm, TeamInvitationForm
from accounts.models import User
from matches.models import ActionTag


def get_user_team(user):
    membership = TeamMembership.objects.filter(user=user).first()
    if membership:
        return membership.team
    team = Team.objects.filter(created_by=user).first()
    if team:
        return team
    player = Player.objects.filter(user=user).first()
    if player:
        return player.team
    return None


@login_required
def team_create_view(request):
    if get_user_team(request.user):
        return redirect('roster')
    if not request.user.is_staff_role:
        messages.info(request, 'You need to be added to a team by a coach.')
        return render(request, 'teams/no_team.html')
    if request.method == 'POST':
        form = TeamForm(request.POST)
        if form.is_valid():
            team = form.save(commit=False)
            team.created_by = request.user
            team.save()
            TeamMembership.objects.create(team=team, user=request.user, role=request.user.role)
            messages.success(request, f'Team "{team.name}" created!')
            return redirect('roster')
    else:
        form = TeamForm()
    return render(request, 'teams/team_form.html', {
        'form': form,
        'age_choices': TeamForm.AGE_CHOICES,
    })


@login_required
def team_settings_view(request):
    team = get_user_team(request.user)
    if not team or not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('roster')
    if request.method == 'POST':
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            messages.success(request, 'Team defaults updated.')
            return redirect('team_settings')
    else:
        form = TeamForm(instance=team)
    return render(request, 'teams/team_form.html', {
        'form': form,
        'age_choices': TeamForm.AGE_CHOICES,
    })


@login_required
def roster_view(request):
    if request.user.is_fan_role:
        team_id = request.GET.get('team', '')
        teams = Team.objects.all()
        if team_id:
            team = get_object_or_404(Team, pk=team_id)
            players = team.players.filter(is_active=True)
        else:
            team = None
            players = Player.objects.filter(is_active=True)
        search = request.GET.get('search', '')
        position = request.GET.get('position', 'all')
        if search:
            players = players.filter(name__icontains=search)
        if position != 'all':
            players = players.filter(position=position)
        return render(request, 'teams/roster.html', {
            'team': team,
            'players': players,
            'search': search,
            'position': position,
            'all_teams': teams,
            'is_fan': True,
            'selected_team': team_id,
        })

    team = get_user_team(request.user)
    if not team:
        return redirect('team_create')
    players = team.players.filter(is_active=True)
    search = request.GET.get('search', '')
    position = request.GET.get('position', 'all')
    if search:
        players = players.filter(name__icontains=search)
    if position != 'all':
        players = players.filter(position=position)
    return render(request, 'teams/roster.html', {
        'team': team,
        'players': players,
        'search': search,
        'position': position,
    })


@login_required
def player_profile_view(request, pk):
    if request.user.is_fan_role:
        player = get_object_or_404(Player, pk=pk, is_active=True)
        can_manage = False
    else:
        team = get_user_team(request.user)
        player = get_object_or_404(Player, pk=pk, team=team, is_active=True)
        can_manage = request.user.is_staff_role

    tags = ActionTag.objects.filter(player=player)
    stats = {
        'kills': tags.filter(tag_type='kill').count(),
        'blocks': tags.filter(tag_type='block').count(),
        'aces': tags.filter(tag_type='ace').count(),
        'assists': tags.filter(tag_type='assist').count(),
        'digs': tags.filter(tag_type='dig').count(),
        'errors': tags.filter(tag_type__in=['serve_error', 'attack_error']).count(),
    }
    recent_tags = tags.select_related('action', 'action__live_match', 'action__live_match__match').order_by('-action__timestamp')[:8]
    total_actions = tags.count()
    return render(request, 'teams/player_profile.html', {
        'player': player,
        'stats': stats,
        'recent_tags': recent_tags,
        'total_actions': total_actions,
        'can_manage': can_manage,
    })


@login_required
def player_add_view(request):
    team = get_user_team(request.user)
    if not team or not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('roster')
    if request.method == 'POST':
        form = PlayerForm(request.POST, team=team)
        if form.is_valid():
            player = form.save(commit=False)
            player.team = team
            if player.email:
                existing_user = User.objects.filter(email=player.email).first()
                if existing_user:
                    player.user = existing_user
                    existing_user.role = 'player'
                    existing_user.save(update_fields=['role'])
                    TeamMembership.objects.get_or_create(
                        user=existing_user, team=team, defaults={'role': 'player'}
                    )
            player.save()
            messages.success(request, f'{player.name} added to roster.')
            return redirect('roster')
    else:
        form = PlayerForm(team=team)
    return render(request, 'teams/player_form.html', {'form': form, 'action': 'Add'})


@login_required
def player_edit_view(request, pk):
    team = get_user_team(request.user)
    player = get_object_or_404(Player, pk=pk, team=team, is_active=True)
    if not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('roster')
    if request.method == 'POST':
        form = PlayerForm(request.POST, instance=player, team=team)
        if form.is_valid():
            form.save()
            messages.success(request, f'{player.name} updated.')
            return redirect('player_profile', pk=player.pk)
    else:
        form = PlayerForm(instance=player, team=team)
    return render(request, 'teams/player_form.html', {'form': form, 'action': 'Edit'})


@login_required
def player_delete_view(request, pk):
    team = get_user_team(request.user)
    player = get_object_or_404(Player, pk=pk, team=team, is_active=True)
    if not request.user.is_staff_role:
        messages.error(request, 'Permission denied.')
        return redirect('roster')
    if request.method == 'POST':
        player.is_active = False
        player.save(update_fields=['is_active'])
        messages.success(request, f'{player.name} removed from roster.')
        return redirect('roster')
    return render(request, 'teams/player_confirm_delete.html', {'player': player})


@login_required
def invite_view(request):
    team = get_user_team(request.user)
    if not team or not request.user.is_coach:
        messages.error(request, 'Permission denied.')
        return redirect('roster')
    if request.method == 'POST':
        form = TeamInvitationForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.team = team
            invite.save()
            accept_url = request.build_absolute_uri(reverse('accept_invite', args=[invite.token]))
            send_mail(
                subject=f"You're invited to join {team.name} on VolleyPilot",
                message=(
                    f"Hello,\n\n{request.user.get_full_name() or request.user.email} invited you to join "
                    f"{team.name} as {invite.get_role_display()}.\n\n"
                    f"Use this link to accept or decline the invitation:\n{accept_url}\n"
                ),
                from_email=None,
                recipient_list=[invite.email],
                fail_silently=True,
            )
            messages.success(request, f'Invitation created for {invite.email}. Share this link if needed: {accept_url}')
            return redirect('roster')
    else:
        form = TeamInvitationForm()
    pending_invites = TeamInvitation.objects.filter(team=team).order_by('-created_at')[:20]
    for invite in pending_invites:
        invite.accept_url = request.build_absolute_uri(reverse('accept_invite', args=[invite.token]))
    return render(request, 'teams/invite_form.html', {'form': form, 'team': team, 'pending_invites': pending_invites})


def accept_invite_view(request, token):
    invite = get_object_or_404(TeamInvitation, token=token, status='pending')
    if not request.user.is_authenticated:
        messages.info(request, 'Please log in or register to accept the invitation.')
        next_url = reverse('accept_invite', args=[token])
        return redirect(f'/accounts/login/?next={next_url}')
    email_matches = request.user.email.lower() == invite.email.lower()
    if request.method == 'POST':
        if not email_matches:
            messages.error(request, f'This invitation is for {invite.email}. Please sign in with that account first.')
            return redirect('dashboard')
        action = request.POST.get('action')
        if action == 'accept':
            TeamMembership.objects.get_or_create(
                team=invite.team, user=request.user,
                defaults={'role': invite.role}
            )
            invite.status = 'accepted'
            invite.save()
            request.user.role = invite.role
            request.user.save()
            messages.success(request, f'You joined {invite.team.name}!')
        else:
            invite.status = 'declined'
            invite.save()
            messages.info(request, 'Invitation declined.')
        return redirect('dashboard')
    return render(request, 'teams/accept_invite.html', {'invite': invite, 'email_matches': email_matches})
