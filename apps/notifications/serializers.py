from rest_framework import serializers
from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    incident_id = serializers.IntegerField(source='incident.id', read_only=True, allow_null=True)

    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'body', 'notification_type', 'incident', 'incident_id',
            'data', 'is_read', 'push_sent', 'created_at'
        ]
        read_only_fields = ['id', 'push_sent', 'created_at']
