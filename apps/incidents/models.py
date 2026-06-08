from django.db import models


class IncidentStatus(models.TextChoices):
    PENDING = 'pending', 'Pendiente'
    ANALYZING = 'analyzing', 'Analizando con IA'
    WAITING_WORKSHOP = 'waiting_workshop', 'Esperando taller'
    ASSIGNED = 'assigned', 'Taller asignado'
    IN_PROGRESS = 'in_progress', 'En atención'
    COMPLETED = 'completed', 'Completado'
    CANCELLED = 'cancelled', 'Cancelado'


class IncidentPriority(models.TextChoices):
    LOW = 'low', 'Baja'
    MEDIUM = 'medium', 'Media'
    HIGH = 'high', 'Alta'
    CRITICAL = 'critical', 'Crítica'


class IncidentType(models.TextChoices):
    BATTERY = 'battery', 'Batería'
    TIRE = 'tire', 'Llanta'
    ACCIDENT = 'accident', 'Choque / Accidente'
    ENGINE = 'engine', 'Motor'
    LOCKSMITH = 'locksmith', 'Llaves / Cerrajería'
    OVERHEATING = 'overheating', 'Sobrecalentamiento'
    OTHER = 'other', 'Otro'
    UNCERTAIN = 'uncertain', 'Incierto'


class Incident(models.Model):
    client = models.ForeignKey(
        'users.ClientProfile', on_delete=models.CASCADE, related_name='incidents'
    )
    vehicle = models.ForeignKey(
        'vehicles.Vehicle', on_delete=models.SET_NULL, null=True, related_name='incidents'
    )

    # Estado y clasificación
    status = models.CharField(
        max_length=30, choices=IncidentStatus.choices, default=IncidentStatus.PENDING
    )
    priority = models.CharField(
        max_length=20, choices=IncidentPriority.choices, null=True, blank=True
    )
    incident_type = models.CharField(
        max_length=20, choices=IncidentType.choices, default=IncidentType.UNCERTAIN
    )

    # Descripción manual
    description = models.TextField(blank=True)

    # Geolocalización del incidente
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    address_text = models.TextField(blank=True)

    # Resultados IA
    ai_transcription = models.TextField(blank=True)  # Whisper: audio → texto
    ai_classification_raw = models.JSONField(null=True, blank=True)  # Output TensorFlow bruto
    ai_summary = models.TextField(blank=True)  # Ficha estructurada (GPT)
    ai_confidence = models.FloatField(null=True, blank=True)  # Confianza clasificación

    # Idempotencia app móvil / offline (UUID del cliente)
    client_request_id = models.CharField(
        max_length=36, unique=True, null=True, blank=True, db_index=True
    )

    # Metadatos
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'incidents'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['created_at']),
            models.Index(fields=['client']),
        ]

    def __str__(self):
        return f"Incident #{self.id} - {self.get_status_display()}"


class EvidenceType(models.TextChoices):
    IMAGE = 'image', 'Imagen'
    AUDIO = 'audio', 'Audio'
    TEXT = 'text', 'Texto adicional'


class Evidence(models.Model):
    """
    Evidencias adjuntas al incidente.
    Archivos físicos guardados en /media/incidents/ del servidor local.
    """
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='evidences')
    evidence_type = models.CharField(max_length=10, choices=EvidenceType.choices)

    # Archivo local — NUNCA AWS/S3
    file = models.FileField(upload_to='incidents/files/%Y/%m/%d/')

    # Para audios
    transcription = models.TextField(blank=True)  # Texto generado por Whisper
    transcription_done = models.BooleanField(default=False)

    # Para imágenes
    image_analysis = models.JSONField(null=True, blank=True)  # Output análisis TF
    label = models.CharField(max_length=60, blank=True)  # Etiqueta principal detectada

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'evidences'

    def __str__(self):
        return f"Evidence {self.evidence_type} - Incident #{self.incident.id}"


class IncidentStatusHistory(models.Model):
    """Trazabilidad completa de cambios de estado."""
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='status_history')
    previous_status = models.CharField(max_length=30, choices=IncidentStatus.choices, blank=True)
    new_status = models.CharField(max_length=30, choices=IncidentStatus.choices)
    changed_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'incident_status_history'
        ordering = ['-changed_at']

    def __str__(self):
        return f"Incident #{self.incident.id}: {self.previous_status} → {self.new_status}"


class IncidentCycleMetric(models.Model):
    """Métricas de un ciclo completo (asignación → cierre) para reportes y reentrenamiento IA."""

    assignment = models.OneToOneField(
        'assignments.Assignment',
        on_delete=models.CASCADE,
        related_name='cycle_metric',
    )
    seconds_to_assignment = models.PositiveIntegerField(null=True, blank=True)
    seconds_to_arrival = models.PositiveIntegerField(null=True, blank=True)
    seconds_total_resolution = models.PositiveIntegerField(null=True, blank=True)
    service_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ai_confidence = models.FloatField(null=True, blank=True)
    ai_predicted_type = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'incident_cycle_metrics'

    def __str__(self):
        return f"CycleMetric assignment={self.assignment_id}"
