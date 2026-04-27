from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import RegistrationForm, ProfileForm, RoleAssignmentForm, AccessibilitySettingsForm
from .models import User


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    next_url = request.GET.get('next') or request.POST.get('next') or ''
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
            if next_url:
                return redirect(next_url)
            return redirect('dashboard')
    else:
        form = RegistrationForm(initial={'email': request.GET.get('email', '')})
    return render(request, 'accounts/register.html', {'form': form, 'next_url': next_url})


@login_required
def profile_view(request):
    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'profile')
        if form_type == 'profile':
            profile_form = ProfileForm(request.POST, instance=request.user)
            accessibility_form = AccessibilitySettingsForm(instance=request.user)
            if profile_form.is_valid():
                user = profile_form.save(commit=False)
                user.username = user.email
                user.save()
                messages.success(request, 'Profile updated successfully.')
                return redirect('profile')
        elif form_type == 'accessibility':
            profile_form = ProfileForm(instance=request.user)
            accessibility_form = AccessibilitySettingsForm(request.POST, instance=request.user)
            if accessibility_form.is_valid():
                accessibility_form.save()
                messages.success(request, 'Accessibility settings updated.')
                return redirect('profile')
        else:
            profile_form = ProfileForm(instance=request.user)
            accessibility_form = AccessibilitySettingsForm(instance=request.user)
    else:
        profile_form = ProfileForm(instance=request.user)
        accessibility_form = AccessibilitySettingsForm(instance=request.user)

    return render(
        request,
        'accounts/profile.html',
        {
            'form': profile_form,
            'accessibility_form': accessibility_form,
        },
    )


@login_required
def password_change_view(request):
    pw_errors = []
    if request.method == 'POST':
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
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Password changed successfully.')
            return redirect('profile')

    return render(request, 'accounts/password_change.html', {'pw_errors': pw_errors})


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


@login_required
def notifications_view(request):
    from .models import Notification
    notifications = request.user.notifications.all()[:50]
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'accounts/notifications.html', {'notifications': notifications})
