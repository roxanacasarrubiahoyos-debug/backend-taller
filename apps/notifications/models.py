from django.db import models


class NotificationType(models.TextChoices):
    INCIDENT_CREATED = 'incident_created', 'Incidente creado'
    WORKSHOP_ASSIGNED = 'workshop_assigned', 'Taller asignado'
    TECHNICIAN_ASSIGNED = 'technician_assigned', 'Orden asignada al técnico'
    TECHNICIAN_NEARBY = 'technician_nearby', 'Técnico cerca de tu ubicación'
    TECHNICIAN_IN_ROUTE = 'technician_in_route', 'Técnico en camino'
    SERVICE_COMPLETED = 'service_completed', 'Servicio completado'
    PAYMENT_REQUIRED = 'payment_required', 'Pago requerido'
    PAYMENT_CONFIRMED = 'payment_confirmed', 'Pago confirmado'
    NEW_REQUEST = 'new_request', 'Nueva solicitud (taller)'
    STATUS_UPDATED = 'status_updated', 'Estado actualizado'
    NEW_RATING = 'new_rating', 'Nueva calificación (taller)'
    WORKSHOP_VERIFIED = 'workshop_verified', 'Taller verificado (panel)'
    WORKSHOP_PENDING_REVIEW = 'workshop_pending_review', 'Taller pendiente de revisión (admin)'


class Notification(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=150)
    body = models.TextField()
    notification_type = models.CharField(max_length=40, choices=NotificationType.choices)
    incident = models.ForeignKey(
        'incidents.Incident', on_delete=models.SET_NULL, null=True, blank=True
    )
    data = models.JSONField(default=dict)  # Payload adicional para la app
    is_read = models.BooleanField(default=False)
    push_sent = models.BooleanField(default=False)  # Si se envió push Firebase
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.title}"


from apps.notifications.web_push_models import WebPushSubscription  # noqa: E402, F401
