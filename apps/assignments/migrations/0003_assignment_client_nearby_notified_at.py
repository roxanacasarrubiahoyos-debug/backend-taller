from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0002_assignment_arrived_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='assignment',
            name='client_nearby_notified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
