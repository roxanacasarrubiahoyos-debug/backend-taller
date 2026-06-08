from django.db import models


class VehicleType(models.TextChoices):
    CAR = 'car', 'Automóvil'
    MOTORCYCLE = 'motorcycle', 'Motocicleta'
    TRUCK = 'truck', 'Camión'
    VAN = 'van', 'Camioneta'
    BUS = 'bus', 'Bus'


class Vehicle(models.Model):
    client = models.ForeignKey(
        'users.ClientProfile', on_delete=models.CASCADE, related_name='vehicles'
    )
    brand = models.CharField(max_length=60)
    model = models.CharField(max_length=60)
    year = models.PositiveSmallIntegerField()
    plate = models.CharField(max_length=20, unique=True)
    color = models.CharField(max_length=40)
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices)
    vin = models.CharField(max_length=17, blank=True)  # VIN / chasis
    is_active = models.BooleanField(default=True)
    photo = models.ImageField(upload_to='vehicles/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'vehicles'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.brand} {self.model} ({self.plate})"
