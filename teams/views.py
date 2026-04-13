from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Team, Player, TeamInvitation, TeamMembership
from .forms import TeamForm, PlayerForm, TeamInvitationForm
from accounts.models import User


def get_user_team(user):
    membership = TeamMembership.objects.filter(user=user).first()
    if membership:
        return membership.team
    team = Team.objects.filter(created_by=user).first()
    if team:
        return team
    # Check if user has a linked player profile
    player = Player.objects.filter(user=user).first()
    if player:
        return player.team
    return None


@login_required
def team_create_view(request):
    # If user already has a team, go to roster
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
    return render(request, 'teams/team_form.html', {'form': form})


@login_required
def roster_view(request):
    # Fans see league-wide rosters with team filter
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
            # Auto-link if a user with this email already exists
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
            return redirect('roster')
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
        player.save()
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
            messages.success(request, f'Invitation sent to {invite.email}')
            return redirect('roster')
    else:
        form = TeamInvitationForm()
    return render(request, 'teams/invite_form.html', {'form': form, 'team': team})


def accept_invite_view(request, token):
    invite = get_object_or_404(TeamInvitation, token=token, status='pending')
    if not request.user.is_authenticated:
        messages.info(request, 'Please log in or register to accept the invitation.')
        return redirect(f'/accounts/login/?next=/teams/invite/{token}/accept/')
    if request.method == 'POST':
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
    return render(request, 'teams/accept_invite.html', {'invite': invite})

