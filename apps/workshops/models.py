from django.db import models


class ServiceCategory(models.TextChoices):
    BATTERY = 'battery', 'Batería / Eléctrico'
    TIRE = 'tire', 'Llantas / Pinchazos'
    TOWING = 'towing', 'Remolque / Grúa'
    ENGINE = 'engine', 'Motor / Sobrecalentamiento'
    ACCIDENT = 'accident', 'Accidentes / Choque'
    LOCKSMITH = 'locksmith', 'Cerrajería (llaves)'
    GENERAL = 'general', 'Mecánica General'


class Workshop(models.Model):
    owner = models.ForeignKey(
        'users.WorkshopOwnerProfile', on_delete=models.CASCADE, related_name='workshops'
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    address = models.TextField()
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to='workshops/logos/', null=True, blank=True)
    services = models.JSONField(default=list)  # Lista de ServiceCategory
    radius_km = models.PositiveIntegerField(default=15)  # Radio de servicio
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)  # Aprobado por admin
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)
    total_services = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workshops'
        indexes = [
            models.Index(fields=['latitude', 'longitude']),
            models.Index(fields=['is_active', 'is_verified']),
        ]

    def __str__(self):
        return self.name


class Technician(models.Model):
    workshop = models.ForeignKey(Workshop, on_delete=models.CASCADE, related_name='technicians')
    user = models.OneToOneField(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='technician_profile',
    )
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    specialties = models.JSONField(default=list)  # Lista de ServiceCategory
    is_available = models.BooleanField(default=True)
    current_latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    last_location_update = models.DateTimeField(null=True, blank=True)
    photo = models.ImageField(upload_to='technicians/', null=True, blank=True)

    class Meta:
        db_table = 'technicians'

    def __str__(self):
        return f"{self.name} - {self.workshop.name}"


class WorkshopRating(models.Model):
    workshop = models.ForeignKey(Workshop, on_delete=models.CASCADE, related_name='ratings')
    client = models.ForeignKey('users.ClientProfile', on_delete=models.CASCADE)
    assignment = models.OneToOneField(
        'assignments.Assignment',
        on_delete=models.CASCADE,
        related_name='client_rating',
        null=True,
        blank=True,
    )
    score = models.PositiveSmallIntegerField()  # 1–5
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workshop_ratings'

    def __str__(self):
        return f"{self.workshop.name} - {self.score}/5"
