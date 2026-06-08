from django.db import models


class AssignmentStatus(models.TextChoices):
    OFFERED = 'offered', 'Ofrecida al taller'
    ACCEPTED = 'accepted', 'Aceptada'
    REJECTED = 'rejected', 'Rechazada'
    IN_ROUTE = 'in_route', 'Técnico en camino'
    ARRIVED = 'arrived', 'Técnico llegó'
    IN_SERVICE = 'in_service', 'En servicio'
    COMPLETED = 'completed', 'Completada'


class Assignment(models.Model):
    incident = models.ForeignKey(
        'incidents.Incident', on_delete=models.CASCADE, related_name='assignments'
    )
    workshop = models.ForeignKey(
        'workshops.Workshop', on_delete=models.CASCADE, related_name='assignments'
    )
    technician = models.ForeignKey(
        'workshops.Technician', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assignments'
    )
    status = models.CharField(
        max_length=20, choices=AssignmentStatus.choices, default=AssignmentStatus.OFFERED
    )

    # Distancia calculada al momento de la asignación
    distance_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # Tiempo estimado de llegada
    estimated_arrival_minutes = models.PositiveIntegerField(null=True, blank=True)

    # Costo del servicio (ingresado por el taller al cerrar)
    service_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    offered_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    # Push única al cliente: técnico cerca del punto del incidente (geovalla vía WebSocket)
    client_nearby_notified_at = models.DateTimeField(null=True, blank=True)
    # Preferencia del cliente entre talleres ofrecidos (app móvil)
    client_selected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'assignments'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['incident']),
        ]

    def __str__(self):
        return f"Assignment #{self.id} - {self.workshop.name} - {self.get_status_display()}"


class ServiceQuoteStatus(models.TextChoices):
    SENT = 'sent', 'Enviada'
    APPROVED = 'approved', 'Aprobada por cliente'
    REJECTED = 'rejected', 'Rechazada por cliente'
    SUPERSEDED = 'superseded', 'Reemplazada'


class ServiceQuote(models.Model):
    """Cotización de daño / reparación asociada a una oferta de taller."""
    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name='quotes'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    estimated_repair_minutes = models.PositiveIntegerField(
        help_text='Tiempo estimado de reparación (no confundir con ETA de llegada)'
    )
    damage_description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=ServiceQuoteStatus.choices,
        default=ServiceQuoteStatus.SENT,
    )
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    client_responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'service_quotes'
        ordering = ['-created_at']

    def __str__(self):
        return f"Quote #{self.id} assignment={self.assignment_id} {self.amount}"
