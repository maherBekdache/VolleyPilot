from django.contrib.auth.models import AbstractUser
from django.db import models


class Club(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    ROLE_CHOICES = [
        ('coach', 'Coach'),
        ('assistant', 'Assistant Coach'),
        ('player', 'Player'),
        ('fan', 'Fan'),
    ]
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='fan')
    club = models.ForeignKey(Club, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    @property
    def is_coach(self):
        return self.role in ('coach', 'director')

    @property
    def is_staff_role(self):
        return self.role in ('coach', 'assistant', 'manager', 'director')

    @property
    def is_player_role(self):
        return self.role == 'player'

    @property
    def is_parent_role(self):
        return self.role == 'parent'

    @property
    def is_fan_role(self):
        return self.role == 'fan'

