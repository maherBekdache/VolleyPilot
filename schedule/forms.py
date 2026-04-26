from django import forms
from .models import Match, Practice


class MatchForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = ['title', 'date', 'time', 'location', 'opponent', 'is_home', 'ruleset', 'substitution_limit']
        help_texts = {
            'substitution_limit': 'VolleyPilot enforces this limit for regular substitutions during each set.',
        }
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'time': forms.TimeInput(attrs={'type': 'time'}),
        }


class PracticeForm(forms.ModelForm):
    class Meta:
        model = Practice
        fields = ['date', 'time', 'location', 'focus']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'time': forms.TimeInput(attrs={'type': 'time'}),
        }
