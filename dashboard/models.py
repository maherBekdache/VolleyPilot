from django.db import models

from .security import decrypt_json, encrypt_json, storage_encryption_enabled


class MLTrainingSample(models.Model):
    """An anonymized match sample prepared for future model training."""

    team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='ml_training_samples')
    source_match = models.OneToOneField(
        'schedule.Match',
        on_delete=models.CASCADE,
        related_name='ml_training_sample',
        null=True,
        blank=True,
    )
    sample_id = models.CharField(max_length=32, unique=True)
    team_hash = models.CharField(max_length=32, db_index=True)
    opponent_hash = models.CharField(max_length=32, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    encrypted_payload = models.TextField(blank=True, default='')
    is_encrypted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['team', 'updated_at'], name='mlsample_team_updated_idx'),
            models.Index(fields=['sample_id'], name='mlsample_sample_id_idx'),
        ]

    def set_payload(self, payload):
        if storage_encryption_enabled():
            self.encrypted_payload = encrypt_json(payload)
            self.payload = {}
            self.is_encrypted = True
        else:
            self.payload = payload
            self.encrypted_payload = ''
            self.is_encrypted = False

    def get_payload(self):
        if self.is_encrypted:
            return decrypt_json(self.encrypted_payload)
        return self.payload or {}

    def __str__(self):
        return f"ML sample {self.sample_id}"
