from django.conf import settings
from django.db import models


class Drill(models.Model):
    CATEGORY_CHOICES = [
        ('Passing', 'Passing'),
        ('Serving', 'Serving'),
        ('Hitting', 'Hitting'),
        ('Blocking', 'Blocking'),
        ('Defense', 'Defense'),
        ('Setting', 'Setting'),
        ('Game-like', 'Game-like'),
    ]
    DIFFICULTY_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    duration = models.CharField(max_length=20)
    players_needed = models.CharField(max_length=20)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES)
    description = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name


class PracticeDrill(models.Model):
    practice = models.ForeignKey('schedule.Practice', on_delete=models.CASCADE, related_name='practice_drills')
    drill = models.ForeignKey(Drill, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    planned_duration = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.drill.name} in {self.practice}"


class DrillObservation(models.Model):
    practice_drill = models.OneToOneField(PracticeDrill, on_delete=models.CASCADE, related_name='observation')
    was_performed = models.BooleanField(default=False)
    actual_duration = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    rating = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"Observation: {self.practice_drill.drill.name}"

