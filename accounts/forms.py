from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User
from teams.models import Team


TEAM_ROLES = {'coach', 'assistant', 'manager', 'player', 'parent', 'director'}


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    role = forms.ChoiceField(choices=User.ROLE_CHOICES, initial='fan')
    team = forms.ModelChoiceField(
        queryset=Team.objects.all(),
        required=False,
        empty_label='— Select a team —',
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'team', 'password1', 'password2']

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        team = cleaned_data.get('team')
        if role in TEAM_ROLES and not team:
            self.add_error('team', 'Please select a team for this role.')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']
        user.role = self.cleaned_data['role']
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']


class RoleAssignmentForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['role']
