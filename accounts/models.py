from django.contrib.auth.models import AbstractUser
from django.conf import settings
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
        ('manager', 'Manager'),
        ('player', 'Player'),
        ('parent', 'Parent'),
        ('director', 'Club Director'),
        ('fan', 'Fan'),
    ]
    COLOR_BLIND_MODE_CHOICES = [
        ('off', 'Off'),
        ('protanopia', 'Protanopia'),
        ('deuteranopia', 'Deuteranopia'),
        ('tritanopia', 'Tritanopia'),
    ]
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='fan')
    club = models.ForeignKey(Club, on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    high_contrast = models.BooleanField(default=False)
    color_blind_mode = models.CharField(max_length=20, choices=COLOR_BLIND_MODE_CHOICES, default='off')

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


class Notification(models.Model):
    NOTIF_TYPES = [
        ('match', 'Match'),
        ('practice', 'Practice'),
        ('announcement', 'Announcement'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    notif_type = models.CharField(max_length=20, choices=NOTIF_TYPES, default='match')
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.notif_type}: {self.title}"

