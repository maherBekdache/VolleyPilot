from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schedule', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='match',
            name='title',
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name='match',
            name='ruleset',
            field=models.CharField(choices=[('fivb_best_of_5', 'FIVB Indoor — Best of 5'), ('best_of_3', 'Short Match — Best of 3'), ('training_scrimmage', 'Training Scrimmage')], default='fivb_best_of_5', max_length=30),
        ),
    ]
