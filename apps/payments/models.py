from django.db import models
from django.utils import timezone


class CommissionConfig(models.Model):
    """
    Configuración de comisión gestionada SOLO por el Admin.
    Porcentaje que el taller paga a la plataforma.
    """
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    description = models.CharField(max_length=200, blank=True)
    effective_from = models.DateField()
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'commission_configs'
        ordering = ['-effective_from']

    @classmethod
    def get_applicable_for_date(cls, on_date=None):
        """
        Tarifa en vigor: la fila con effective_from más reciente que ya comenzó (<= on_date).
        No depende de is_active; ese flag es solo ayuda en el historial administrativo.
        """
        d = on_date if on_date is not None else timezone.localdate()
        return cls.objects.filter(effective_from__lte=d).order_by('-effective_from').first()

    def __str__(self):
        return f"Commission {self.percentage}% - Effective from {self.effective_from}"


class PaymentStatus(models.TextChoices):
    PENDING = 'pending', 'Pendiente'
    CLIENT_PAID = 'client_paid', 'Cliente pagó'
    COMMISSION_SETTLED = 'commission_settled', 'Comisión liquidada'
    FAILED = 'failed', 'Fallido'
    REFUNDED = 'refunded', 'Reembolsado'


class Payment(models.Model):
    """
    Flujo Stripe:
    1. Cliente paga el total del servicio (PaymentIntent al cliente).
    2. La plataforma retiene la comisión.
    3. El taller recibe el neto (Transfer vía Stripe Connect).
    """
    assignment = models.OneToOneField(
        'assignments.Assignment', on_delete=models.CASCADE, related_name='payment'
    )
    commission_config = models.ForeignKey(
        CommissionConfig, on_delete=models.SET_NULL, null=True
    )

    # Montos
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)  # Lo que paga el cliente
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)  # % aplicado
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2)  # Monto comisión
    workshop_net_amount = models.DecimalField(max_digits=10, decimal_places=2)  # total - comisión

    # Stripe
    stripe_payment_intent_id = models.CharField(max_length=100, blank=True)  # Cobro al cliente
    stripe_transfer_id = models.CharField(max_length=100, blank=True)  # Pago al taller
    stripe_charge_id = models.CharField(max_length=100, blank=True)

    status = models.CharField(
        max_length=30, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    currency = models.CharField(max_length=3, default='usd')
    paid_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payments'

    def __str__(self):
        return f"Payment #{self.id} - ${self.total_amount} - {self.get_status_display()}"


class BillingInterval(models.TextChoices):
    MONTH = 'month', 'Mensual'
    YEAR = 'year', 'Anual'


class WorkshopSubscriptionPlan(models.Model):
    """Plan de suscripción creado por el administrador (sincronizado con Stripe)."""
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='usd')
    billing_interval = models.CharField(
        max_length=10,
        choices=BillingInterval.choices,
        default=BillingInterval.MONTH,
    )
    max_technicians = models.PositiveIntegerField(default=5)
    max_monthly_incidents = models.PositiveIntegerField(
        default=100,
        help_text='Límite orientativo de incidentes atendidos por mes',
    )
    features = models.JSONField(default=list, blank=True)
    stripe_product_id = models.CharField(max_length=120, blank=True)
    stripe_price_id = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'workshop_subscription_plans'
        ordering = ['sort_order', 'price_amount']

    def __str__(self):
        return f'{self.name} (${self.price_amount}/{self.billing_interval})'


class WorkshopSubscriptionStatus(models.TextChoices):
    PENDING = 'pending', 'Pendiente de pago'
    ACTIVE = 'active', 'Activa'
    PAST_DUE = 'past_due', 'Pago atrasado'
    CANCELED = 'canceled', 'Cancelada'
    INCOMPLETE = 'incomplete', 'Incompleta'


class WorkshopOwnerSubscription(models.Model):
    owner = models.OneToOneField(
        'users.WorkshopOwnerProfile',
        on_delete=models.CASCADE,
        related_name='subscription',
    )
    plan = models.ForeignKey(
        WorkshopSubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subscriptions',
    )
    status = models.CharField(
        max_length=20,
        choices=WorkshopSubscriptionStatus.choices,
        default=WorkshopSubscriptionStatus.PENDING,
    )
    stripe_subscription_id = models.CharField(max_length=120, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'workshop_owner_subscriptions'

    @property
    def is_operational(self) -> bool:
        return self.status in (
            WorkshopSubscriptionStatus.ACTIVE,
            WorkshopSubscriptionStatus.PAST_DUE,
        )

    def __str__(self):
        return f'Subscription owner={self.owner_id} status={self.status}'
