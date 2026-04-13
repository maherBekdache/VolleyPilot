from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import RegistrationForm, ProfileForm, RoleAssignmentForm
from .models import User


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            team = form.cleaned_data.get('team')
            # Auto-link player profile if email matches
            from teams.models import Player, TeamMembership
            player = Player.objects.filter(email=user.email, user__isnull=True).first()
            if player:
                player.user = user
                player.save(update_fields=['user'])
                if not team:
                    team = player.team
                if user.role != 'player':
                    user.role = 'player'
                    user.save(update_fields=['role'])
            # Create team membership for team-related roles
            from accounts.forms import TEAM_ROLES
            if team and user.role in TEAM_ROLES:
                TeamMembership.objects.get_or_create(
                    user=user, team=team, defaults={'role': user.role}
                )
            login(request, user)
            messages.success(request, 'Account created successfully!')
            return redirect('dashboard')
    else:
        form = RegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def profile_view(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('profile')
    else:
        form = ProfileForm(instance=request.user)
    return render(request, 'accounts/profile.html', {'form': form})


@login_required
def manage_roles_view(request):
    if not request.user.is_coach:
        messages.error(request, 'You do not have permission to manage roles.')
        return redirect('dashboard')
    users = User.objects.exclude(pk=request.user.pk).order_by('last_name')
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        user = get_object_or_404(User, pk=user_id)
        form = RoleAssignmentForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Role updated for {user.get_full_name()}.')
            return redirect('manage_roles')
    return render(request, 'accounts/manage_roles.html', {'users': users})

