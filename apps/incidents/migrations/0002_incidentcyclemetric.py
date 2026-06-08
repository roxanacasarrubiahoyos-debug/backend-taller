# Generated manually — Fase 9 métricas de ciclo

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0002_assignment_arrived_at'),
        ('incidents', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='IncidentCycleMetric',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('seconds_to_assignment', models.PositiveIntegerField(blank=True, null=True)),
                ('seconds_to_arrival', models.PositiveIntegerField(blank=True, null=True)),
                ('seconds_total_resolution', models.PositiveIntegerField(blank=True, null=True)),
                ('service_cost', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('ai_confidence', models.FloatField(blank=True, null=True)),
                ('ai_predicted_type', models.CharField(blank=True, max_length=30)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'assignment',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cycle_metric',
                        to='assignments.assignment',
                    ),
                ),
            ],
            options={
                'db_table': 'incident_cycle_metrics',
            },
        ),
    ]
