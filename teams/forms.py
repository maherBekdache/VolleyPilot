from django import forms
from .models import Team, Player, TeamInvitation


class TeamForm(forms.ModelForm):
    AGE_CHOICES = [
        ('U12', 'U12'),
        ('U14', 'U14'),
        ('U16', 'U16'),
        ('U18', 'U18'),
        ('Adult', 'Adult'),
        ('Senior', 'Senior'),
    ]

    age_group = forms.ChoiceField(choices=[('', 'Select age group')] + AGE_CHOICES, required=False)

    class Meta:
        model = Team
        fields = ['name', 'age_group', 'club_affiliation']


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['name', 'email', 'jersey_number', 'position', 'height', 'year', 'notes']

    def __init__(self, *args, team=None, **kwargs):
        self.team = team
        super().__init__(*args, **kwargs)

    def clean_jersey_number(self):
        number = self.cleaned_data['jersey_number']
        qs = Player.objects.filter(team=self.team, jersey_number=number, is_active=True)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('This jersey number is already taken on this team.')
        return number


class TeamInvitationForm(forms.ModelForm):
    class Meta:
        model = TeamInvitation
        fields = ['email', 'role']
        widgets = {
            'role': forms.Select(choices=[
                ('assistant', 'Assistant Coach'),
                ('manager', 'Manager'),
                ('parent', 'Parent'),
            ])
        }
