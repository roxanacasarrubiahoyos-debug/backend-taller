# Generated manually — Fase 9: rating por servicio (assignment)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0002_assignment_arrived_at'),
        ('workshops', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='workshoprating',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='workshoprating',
            name='assignment',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='client_rating',
                to='assignments.assignment',
            ),
        ),
    ]
