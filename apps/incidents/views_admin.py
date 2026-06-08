from rest_framework import viewsets
from apps.incidents.models import Incident
from apps.incidents.serializers import IncidentSerializer, IncidentDetailSerializer
from apps.users.permissions import IsAdmin


class IncidentAdminViewSet(viewsets.ReadOnlyModelViewSet):
    """Visualización de todos los incidentes (solo admin)"""
    queryset = Incident.objects.all().order_by('-created_at')
    permission_classes = [IsAdmin]
    filterset_fields = ['status', 'priority', 'incident_type']
    search_fields = ['description', 'address_text', 'client__user__email']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return IncidentDetailSerializer
        return IncidentSerializer
