from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0003_assignment_client_nearby_notified_at'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='assignment',
            name='client_selected_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='ServiceQuote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('estimated_repair_minutes', models.PositiveIntegerField(
                    help_text='Tiempo estimado de reparación (no confundir con ETA de llegada)',
                )),
                ('damage_description', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[
                        ('sent', 'Enviada'),
                        ('approved', 'Aprobada por cliente'),
                        ('rejected', 'Rechazada por cliente'),
                        ('superseded', 'Reemplazada'),
                    ],
                    default='sent',
                    max_length=20,
                )),
                ('client_responded_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('assignment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='quotes',
                    to='assignments.assignment',
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'service_quotes',
                'ordering': ['-created_at'],
            },
        ),
    ]
