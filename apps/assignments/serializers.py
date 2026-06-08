from decimal import Decimal

from rest_framework import serializers

from apps.assignments.models import Assignment, ServiceQuote
from apps.incidents.serializers import IncidentSerializer
from apps.workshops.serializers import TechnicianSerializer, WorkshopSerializer


class ServiceQuoteSerializer(serializers.ModelSerializer):
    workshop_name = serializers.CharField(source='assignment.workshop.name', read_only=True)
    workshop_id = serializers.IntegerField(source='assignment.workshop_id', read_only=True)
    assignment_id = serializers.IntegerField(source='assignment.id', read_only=True)
    assignment_status = serializers.CharField(source='assignment.status', read_only=True)
    estimated_arrival_minutes = serializers.IntegerField(
        source='assignment.estimated_arrival_minutes', read_only=True, allow_null=True
    )

    class Meta:
        model = ServiceQuote
        fields = [
            'id',
            'assignment_id',
            'workshop_id',
            'workshop_name',
            'assignment_status',
            'amount',
            'estimated_repair_minutes',
            'estimated_arrival_minutes',
            'damage_description',
            'status',
            'created_at',
            'client_responded_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'created_at',
            'client_responded_at',
            'workshop_name',
            'workshop_id',
            'assignment_id',
            'assignment_status',
            'estimated_arrival_minutes',
        ]


class ServiceQuoteCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal('0.01')
    )
    estimated_repair_minutes = serializers.IntegerField(min_value=1, max_value=60 * 24 * 14)
    damage_description = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class AssignmentDetailSerializer(serializers.ModelSerializer):
    """Detalle de asignación para la app cliente."""

    incident = IncidentSerializer(read_only=True)
    incident_type = serializers.CharField(
        source='incident.get_incident_type_display', read_only=True
    )
    workshop = WorkshopSerializer(read_only=True)
    workshop_name = serializers.CharField(source='workshop.name', read_only=True)
    technician = TechnicianSerializer(read_only=True)
    technician_name = serializers.SerializerMethodField()
    client_rating = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            'id',
            'incident',
            'incident_type',
            'workshop',
            'workshop_name',
            'technician',
            'technician_name',
            'status',
            'distance_km',
            'estimated_arrival_minutes',
            'service_cost',
            'offered_at',
            'accepted_at',
            'arrived_at',
            'completed_at',
            'rejection_reason',
            'client_rating',
        ]

    def get_technician_name(self, obj):
        return obj.technician.name if obj.technician else None

    def get_client_rating(self, obj):
        try:
            cr = obj.client_rating
            if cr:
                return {'score': cr.score, 'comment': cr.comment}
        except Exception:
            pass
        return None


class TechnicianAssignmentListSerializer(serializers.ModelSerializer):
    """Listado de órdenes para la app del técnico."""

    incident_id = serializers.IntegerField(source='incident.id', read_only=True)
    workshop_name = serializers.CharField(source='workshop.name', read_only=True)
    address_text = serializers.CharField(source='incident.address_text', read_only=True)
    vehicle_label = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            'id',
            'incident_id',
            'status',
            'workshop_name',
            'vehicle_label',
            'address_text',
            'distance_km',
            'estimated_arrival_minutes',
            'offered_at',
            'accepted_at',
            'completed_at',
        ]

    def get_vehicle_label(self, obj):
        v = obj.incident.vehicle
        if not v:
            return None
        return f'{v.brand} {v.model} ({v.plate})'


class TechnicianAssignmentDetailSerializer(serializers.ModelSerializer):
    """Detalle de orden para la app del técnico."""

    incident = IncidentSerializer(read_only=True)
    workshop = WorkshopSerializer(read_only=True)
    workshop_name = serializers.CharField(source='workshop.name', read_only=True)
    technician = TechnicianSerializer(read_only=True)
    client_name = serializers.CharField(
        source='incident.client.user.get_full_name', read_only=True
    )

    class Meta:
        model = Assignment
        fields = [
            'id',
            'incident',
            'workshop',
            'workshop_name',
            'technician',
            'client_name',
            'status',
            'distance_km',
            'estimated_arrival_minutes',
            'service_cost',
            'offered_at',
            'accepted_at',
            'arrived_at',
            'completed_at',
            'rejection_reason',
        ]
