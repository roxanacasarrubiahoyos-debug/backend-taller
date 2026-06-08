# Generated manually — Fase 9 métricas

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='assignment',
            name='arrived_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
