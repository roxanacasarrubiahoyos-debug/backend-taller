# Generated manually for Web Push panel subscriptions

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_alter_notification_notification_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WebPushSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('endpoint', models.TextField()),
                ('p256dh', models.CharField(max_length=255)),
                ('auth', models.CharField(max_length=255)),
                ('user_agent', models.CharField(blank=True, max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='web_push_subscriptions',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'db_table': 'web_push_subscriptions',
            },
        ),
        migrations.AddIndex(
            model_name='webpushsubscription',
            index=models.Index(fields=['user', 'is_active'], name='web_push_user_active_idx'),
        ),
        migrations.AddConstraint(
            model_name='webpushsubscription',
            constraint=models.UniqueConstraint(
                fields=('user', 'endpoint'),
                name='uniq_web_push_user_endpoint',
            ),
        ),
    ]
