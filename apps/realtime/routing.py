from django.urls import re_path

from apps.realtime import consumers

websocket_urlpatterns = [
    re_path(r'ws/incident/(?P<incident_id>\d+)/$', consumers.IncidentTrackingConsumer.as_asgi()),
]
