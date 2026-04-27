# Generated for VolleyPilot AI analytics additions

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('schedule', '0004_alter_availabilityrequest_id_and_more'),
        ('teams', '0003_alter_player_id_alter_team_id_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='MLTrainingSample',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sample_id', models.CharField(max_length=32, unique=True)),
                ('team_hash', models.CharField(db_index=True, max_length=32)),
                ('opponent_hash', models.CharField(db_index=True, max_length=32)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('encrypted_payload', models.TextField(blank=True, default='')),
                ('is_encrypted', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('source_match', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ml_training_sample', to='schedule.match')),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ml_training_samples', to='teams.team')),
            ],
            options={
                'ordering': ['-updated_at'],
                'indexes': [
                    models.Index(fields=['team', 'updated_at'], name='mlsample_team_updated_idx'),
                    models.Index(fields=['sample_id'], name='mlsample_sample_id_idx'),
                ],
            },
        ),
    ]
