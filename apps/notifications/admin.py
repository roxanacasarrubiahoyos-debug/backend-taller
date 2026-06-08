from django.contrib import admin
from .models import Notification, WebPushSubscription


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'notification_type', 'is_read', 'push_sent', 'created_at']
    list_filter = ['notification_type', 'is_read', 'push_sent', 'created_at']
    search_fields = ['user__username', 'title', 'body']
    raw_id_fields = ['user', 'incident']
    readonly_fields = ['created_at']


@admin.register(WebPushSubscription)
class WebPushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['user__username', 'endpoint']
    raw_id_fields = ['user']
    readonly_fields = ['created_at', 'updated_at', 'endpoint']
