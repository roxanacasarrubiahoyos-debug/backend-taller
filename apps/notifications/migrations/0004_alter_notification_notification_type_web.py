from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_web_push_subscription'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                max_length=40,
                choices=[
                    ('incident_created', 'Incidente creado'),
                    ('workshop_assigned', 'Taller asignado'),
                    ('technician_assigned', 'Orden asignada al técnico'),
                    ('technician_nearby', 'Técnico cerca de tu ubicación'),
                    ('technician_in_route', 'Técnico en camino'),
                    ('service_completed', 'Servicio completado'),
                    ('payment_required', 'Pago requerido'),
                    ('payment_confirmed', 'Pago confirmado'),
                    ('new_request', 'Nueva solicitud (taller)'),
                    ('status_updated', 'Estado actualizado'),
                    ('new_rating', 'Nueva calificación (taller)'),
                    ('workshop_verified', 'Taller verificado'),
                    ('workshop_pending_review', 'Taller pendiente de revisión'),
                ],
            ),
        ),
    ]
