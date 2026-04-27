# Generated for VolleyPilot live-match performance improvements

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('matches', '0004_alter_action_id_alter_actiontag_id_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='setscore',
            index=models.Index(fields=['live_match', 'set_number'], name='setscore_live_set_idx'),
        ),
        migrations.AddIndex(
            model_name='action',
            index=models.Index(fields=['live_match', 'set_number', 'action_type'], name='action_live_set_type_idx'),
        ),
        migrations.AddIndex(
            model_name='action',
            index=models.Index(fields=['live_match', 'timestamp'], name='action_live_time_idx'),
        ),
        migrations.AddIndex(
            model_name='action',
            index=models.Index(fields=['live_match', 'rotation'], name='action_live_rotation_idx'),
        ),
        migrations.AddIndex(
            model_name='actiontag',
            index=models.Index(fields=['tag_type'], name='actiontag_type_idx'),
        ),
        migrations.AddIndex(
            model_name='actiontag',
            index=models.Index(fields=['player', 'tag_type'], name='actiontag_player_type_idx'),
        ),
    ]
