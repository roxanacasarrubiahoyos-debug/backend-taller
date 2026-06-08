from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    ADMIN = 'admin', 'Administrador'
    WORKSHOP_OWNER = 'workshop_owner', 'Dueño de Taller'
    CLIENT = 'client', 'Cliente'
    TECHNICIAN = 'technician', 'Técnico'


class User(AbstractUser):
    """
    Usuario base unificado con rol.
    El perfil detallado se extiende en ClientProfile o WorkshopOwnerProfile.
    """
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CLIENT)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='profiles/avatars/', null=True, blank=True)
    fcm_token = models.TextField(blank=True)  # Token Firebase para push notifications
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['email']),
        ]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class ClientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client_profile')
    address = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    stripe_customer_id = models.CharField(max_length=100, blank=True)  # ID en Stripe

    class Meta:
        db_table = 'client_profiles'

    def __str__(self):
        return f"Client: {self.user.username}"


class WorkshopOwnerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='owner_profile')
    national_id = models.CharField(max_length=30)  # NIT / cédula empresa
    stripe_customer_id = models.CharField(max_length=100, blank=True)  # Cliente Stripe (suscripción)
    stripe_account_id = models.CharField(max_length=100, blank=True)  # Stripe Connect

    class Meta:
        db_table = 'workshop_owner_profiles'

    def __str__(self):
        return f"Owner: {self.user.username}"
