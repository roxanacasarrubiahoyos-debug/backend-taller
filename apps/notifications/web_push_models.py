from django.db import models


class WebPushSubscription(models.Model):
    """Suscripciones Web Push del panel (taller/admin). Separado de fcm_token (app móvil)."""

    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='web_push_subscriptions',
    )
    endpoint = models.TextField()
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'web_push_subscriptions'
        constraints = [
            models.UniqueConstraint(fields=['user', 'endpoint'], name='uniq_web_push_user_endpoint'),
        ]
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f'WebPush user={self.user_id} active={self.is_active}'
