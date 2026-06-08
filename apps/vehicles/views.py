from rest_framework import viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from apps.vehicles.models import Vehicle
from apps.vehicles.serializers import VehicleSerializer, VehicleCreateSerializer, VehicleUpdateSerializer
from apps.users.permissions import IsClient


class VehicleViewSet(viewsets.ModelViewSet):
    """CRUD de vehículos del cliente"""
    permission_classes = [IsClient]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action == 'create':
            return VehicleCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return VehicleUpdateSerializer
        return VehicleSerializer

    def get_queryset(self):
        return Vehicle.objects.filter(client=self.request.user.client_profile)

    def perform_create(self, serializer):
        serializer.save(client=self.request.user.client_profile)
