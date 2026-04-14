from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('matches', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='livematch',
            name='bench',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='livematch',
            name='first_server',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='livematch',
            name='lineup',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='action',
            name='action_type',
            field=models.CharField(choices=[('point_won', 'Point Won'), ('point_lost', 'Point Lost'), ('substitution', 'Substitution'), ('timeout', 'Timeout'), ('rotation', 'Rotation'), ('undo', 'Undo'), ('lineup', 'Lineup'), ('match_start', 'Match Start'), ('technical_timeout', 'Technical Timeout')], max_length=20),
        ),
    ]
