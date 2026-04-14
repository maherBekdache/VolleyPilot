from django.conf import settings
from django.db import models


class Match(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    RULESET_CHOICES = [
        ('fivb_best_of_5', 'FIVB Indoor — Best of 5'),
        ('best_of_3', 'Short Match — Best of 3'),
        ('training_scrimmage', 'Training Scrimmage'),
    ]

    team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='matches')
    title = models.CharField(max_length=120, blank=True)
    date = models.DateField()
    time = models.TimeField()
    location = models.CharField(max_length=200)
    opponent = models.CharField(max_length=100)
    is_home = models.BooleanField(default=True)
    ruleset = models.CharField(max_length=30, choices=RULESET_CHOICES, default='fivb_best_of_5')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='scheduled')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        verbose_name_plural = 'matches'
        ordering = ['date', 'time']

    def __str__(self):
        prefix = 'vs' if self.is_home else '@'
        return f"{self.display_title} {prefix} {self.opponent} on {self.date}"

    @property
    def display_title(self):
        return self.title or 'Match'


class Practice(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='practices')
    date = models.DateField()
    time = models.TimeField()
    location = models.CharField(max_length=200)
    focus = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='scheduled')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['date', 'time']

    def __str__(self):
        return f"Practice: {self.focus} on {self.date}"


class AvailabilityRequest(models.Model):
    EVENT_TYPE_CHOICES = [
        ('match', 'Match'),
        ('practice', 'Practice'),
    ]
    event_type = models.CharField(max_length=10, choices=EVENT_TYPE_CHOICES)
    match = models.ForeignKey(Match, on_delete=models.CASCADE, null=True, blank=True, related_name='availability_requests')
    practice = models.ForeignKey(Practice, on_delete=models.CASCADE, null=True, blank=True, related_name='availability_requests')
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.event_type == 'match' and self.match:
            return f"Availability for {self.match}"
        return f"Availability for {self.practice}"

    @property
    def event(self):
        return self.match if self.event_type == 'match' else self.practice


class AvailabilityResponse(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('available', 'Available'),
        ('unavailable', 'Unavailable'),
        ('maybe', 'Maybe'),
    ]
    request = models.ForeignKey(AvailabilityRequest, on_delete=models.CASCADE, related_name='responses')
    player = models.ForeignKey('teams.Player', on_delete=models.CASCADE)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ['request', 'player']

    def __str__(self):
        return f"{self.player.name}: {self.status}"
