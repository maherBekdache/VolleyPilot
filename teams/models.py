from django.conf import settings
from django.db import models
import uuid


class Team(models.Model):
    name = models.CharField(max_length=100)
    age_group = models.CharField(max_length=50, blank=True)
    club_affiliation = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_teams')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Player(models.Model):
    POSITION_CHOICES = [
        ('Setter', 'Setter'),
        ('Outside Hitter', 'Outside Hitter'),
        ('Middle Blocker', 'Middle Blocker'),
        ('Opposite', 'Opposite'),
        ('Libero', 'Libero'),
        ('Defensive Specialist', 'Defensive Specialist'),
    ]
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='players')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='player_profiles')
    email = models.EmailField(blank=True, default='')
    name = models.CharField(max_length=100)
    jersey_number = models.PositiveIntegerField()
    position = models.CharField(max_length=30, choices=POSITION_CHOICES)
    height = models.CharField(max_length=10, blank=True)
    year = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['team', 'jersey_number']

    def __str__(self):
        return f"#{self.jersey_number} {self.name}"


class TeamInvitation(models.Model):
    ROLE_CHOICES = [
        ('coach', 'Coach'),
        ('assistant', 'Assistant Coach'),
        ('manager', 'Manager'),
        ('parent', 'Parent'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    role = models.CharField(max_length=20)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invite {self.email} to {self.team.name}"

    def get_role_display(self):
        return dict(self.ROLE_CHOICES).get(self.role, self.role.title())


class TeamMembership(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='team_memberships')
    role = models.CharField(max_length=20)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['team', 'user']

    def __str__(self):
        return f"{self.user} - {self.team.name} ({self.role})"

