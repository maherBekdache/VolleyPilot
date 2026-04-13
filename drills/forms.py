from django import forms
from .models import Drill, DrillObservation


class DrillForm(forms.ModelForm):
    class Meta:
        model = Drill
        fields = ['name', 'category', 'duration', 'players_needed', 'difficulty', 'description']


class DrillObservationForm(forms.ModelForm):
    class Meta:
        model = DrillObservation
        fields = ['was_performed', 'actual_duration', 'notes', 'rating']
        widgets = {
            'rating': forms.NumberInput(attrs={'min': 1, 'max': 5}),
        }
