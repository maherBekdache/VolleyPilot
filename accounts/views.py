from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, update_session_auth_hash
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
            from teams.models import Player, TeamMembership
            player = Player.objects.filter(email=user.email, user__isnull=True).first()
            if player:
                player.user = user
                player.save(update_fields=['user'])
                user.role = 'player'
                user.save(update_fields=['role'])
                TeamMembership.objects.get_or_create(
                    user=user, team=player.team, defaults={'role': 'player'}
                )
            login(request, user)
            messages.success(request, 'Account created successfully!')
            return redirect('dashboard')
    else:
        form = RegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def profile_view(request):
    pw_errors = []

    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'profile')

        # VT-22: Profile information update
        if form_type == 'profile':
            form = ProfileForm(request.POST, instance=request.user)
            if form.is_valid():
                user = form.save(commit=False)
                # Keep username in sync with email
                user.username = user.email
                user.save()
                messages.success(request, 'Profile updated successfully.')
                return redirect('profile')

        # VT-23: Password change
        elif form_type == 'password':
            old_password = request.POST.get('old_password', '')
            new_password1 = request.POST.get('new_password1', '')
            new_password2 = request.POST.get('new_password2', '')

            if not request.user.check_password(old_password):
                pw_errors.append('Current password is incorrect.')
            elif len(new_password1) < 8:
                pw_errors.append('New password must be at least 8 characters.')
            elif new_password1 != new_password2:
                pw_errors.append('New passwords do not match.')
            else:
                request.user.set_password(new_password1)
                request.user.save()
                # Keep the user logged in after password change
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Password changed successfully.')
                return redirect('profile')

            form = ProfileForm(instance=request.user)
        else:
            form = ProfileForm(instance=request.user)
    else:
        form = ProfileForm(instance=request.user)

    return render(request, 'accounts/profile.html', {'form': form, 'pw_errors': pw_errors})


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
