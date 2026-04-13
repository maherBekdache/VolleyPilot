from django.db import models


class LiveMatch(models.Model):
    match = models.OneToOneField('schedule.Match', on_delete=models.CASCADE, related_name='live')
    current_set = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    our_serve = models.BooleanField(default=True)
    current_rotation = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Live: {self.match}"


class SetScore(models.Model):
    live_match = models.ForeignKey(LiveMatch, on_delete=models.CASCADE, related_name='set_scores')
    set_number = models.PositiveIntegerField()
    our_score = models.PositiveIntegerField(default=0)
    opponent_score = models.PositiveIntegerField(default=0)
    is_complete = models.BooleanField(default=False)

    class Meta:
        unique_together = ['live_match', 'set_number']
        ordering = ['set_number']

    def __str__(self):
        return f"Set {self.set_number}: {self.our_score}-{self.opponent_score}"


class Action(models.Model):
    ACTION_TYPES = [
        ('point_won', 'Point Won'),
        ('point_lost', 'Point Lost'),
        ('substitution', 'Substitution'),
        ('timeout', 'Timeout'),
        ('rotation', 'Rotation'),
        ('undo', 'Undo'),
    ]
    live_match = models.ForeignKey(LiveMatch, on_delete=models.CASCADE, related_name='actions')
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    set_number = models.PositiveIntegerField()
    rotation = models.PositiveIntegerField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    data = models.JSONField(default=dict, blank=True)
    is_undone = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.action_type} at {self.timestamp}"


class ActionTag(models.Model):
    TAG_CHOICES = [
        ('kill', 'Kill'),
        ('block', 'Block'),
        ('ace', 'Ace'),
        ('assist', 'Assist'),
        ('dig', 'Dig'),
        ('serve_error', 'Serve Error'),
        ('attack_error', 'Attack Error'),
        ('opponent_error', 'Opponent Error'),
    ]
    action = models.ForeignKey(Action, on_delete=models.CASCADE, related_name='tags')
    tag_type = models.CharField(max_length=20, choices=TAG_CHOICES)
    player = models.ForeignKey('teams.Player', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return f"{self.tag_type} by {self.player}"

