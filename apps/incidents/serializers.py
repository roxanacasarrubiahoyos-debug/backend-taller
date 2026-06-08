from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from rest_framework import serializers
from apps.incidents.models import Incident, Evidence, IncidentStatusHistory
from apps.vehicles.models import Vehicle
from apps.vehicles.serializers import VehicleSerializer


class EvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Evidence
        fields = [
            'id', 'incident', 'evidence_type', 'file', 'transcription',
            'transcription_done', 'image_analysis', 'label', 'created_at'
        ]
        read_only_fields = ['id', 'transcription', 'transcription_done', 'image_analysis', 'label', 'created_at']


class IncidentStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(source='changed_by.get_full_name', read_only=True)

    class Meta:
        model = IncidentStatusHistory
        fields = [
            'id', 'previous_status', 'new_status', 'changed_by',
            'changed_by_name', 'notes', 'changed_at'
        ]
        read_only_fields = ['id', 'changed_at']


class IncidentSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.user.get_full_name', read_only=True)
    vehicle_info = serializers.SerializerMethodField()
    assignment = serializers.SerializerMethodField()

    class Meta:
        model = Incident
        fields = [
            'id', 'client', 'client_name', 'vehicle', 'vehicle_info', 'status',
            'priority', 'incident_type', 'description', 'latitude', 'longitude',
            'address_text', 'ai_confidence', 'created_at', 'updated_at', 'assignment',
        ]
        read_only_fields = [
            'id', 'client', 'status', 'priority', 'incident_type',
            'ai_confidence', 'created_at', 'updated_at'
        ]

    def get_vehicle_info(self, obj):
        if obj.vehicle:
            return f"{obj.vehicle.brand} {obj.vehicle.model} ({obj.vehicle.plate})"
        return None

    def get_assignment(self, obj):
        from apps.assignments.models import AssignmentStatus
        qs = obj.assignments.select_related(
            'workshop', 'technician', 'client_rating', 'payment'
        ).order_by('-completed_at', '-id')
        a = qs.filter(status=AssignmentStatus.COMPLETED).first()
        if not a:
            a = qs.exclude(status__in=[AssignmentStatus.OFFERED, AssignmentStatus.REJECTED]).first()
        if not a:
            return None
        rating = None
        try:
            cr = a.client_rating
            if cr:
                rating = {'score': cr.score, 'comment': cr.comment}
        except Exception:
            pass
        payment_info = None
        try:
            p = a.payment
            payment_info = {
                'id': p.id,
                'status': p.status,
                'total_amount': str(p.total_amount),
            }
        except Exception:
            pass
        tech = a.technician
        technician_payload = None
        if tech:
            technician_payload = {
                'id': tech.id,
                'name': tech.name,
                'phone': tech.phone or '',
                'current_latitude': tech.current_latitude,
                'current_longitude': tech.current_longitude,
                'last_location_update': (
                    tech.last_location_update.isoformat()
                    if tech.last_location_update
                    else None
                ),
            }
        return {
            'id': a.id,
            'status': a.status,
            'workshop': {'id': a.workshop_id, 'name': a.workshop.name},
            'technician': technician_payload,
            'technician_name': tech.name if tech else None,
            'estimated_arrival_minutes': a.estimated_arrival_minutes,
            'service_cost': str(a.service_cost) if a.service_cost is not None else None,
            'rating': rating,
            'payment': payment_info,
        }


class IncidentDetailSerializer(IncidentSerializer):
    evidences = EvidenceSerializer(many=True, read_only=True)
    status_history = IncidentStatusHistorySerializer(many=True, read_only=True)
    ai_summary_parsed = serializers.SerializerMethodField()

    class Meta(IncidentSerializer.Meta):
        fields = IncidentSerializer.Meta.fields + [
            'evidences', 'status_history', 'ai_transcription',
            'ai_classification_raw', 'ai_summary', 'ai_summary_parsed', 'closed_at'
        ]

    def get_ai_summary_parsed(self, obj):
        if obj.ai_summary:
            try:
                import json
                return json.loads(obj.ai_summary)
            except:
                return None
        return None


class IncidentCreateSerializer(serializers.ModelSerializer):
    # Float en entrada (clientes JSON); se cuantiza en validate() al Decimal del modelo.
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()

    class Meta:
        model = Incident
        fields = [
            'id',
            'vehicle',
            'description',
            'latitude',
            'longitude',
            'address_text',
            'client_request_id',
        ]
        read_only_fields = ['id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and getattr(request.user, 'is_authenticated', False):
            profile = getattr(request.user, 'client_profile', None)
            if profile is not None:
                self.fields['vehicle'].queryset = Vehicle.objects.filter(client=profile)

    def validate_vehicle(self, value):
        request = self.context.get('request')
        profile = getattr(request.user, 'client_profile', None) if request else None
        if profile is not None and value is not None and value.client_id != profile.id:
            raise serializers.ValidationError('Este vehículo no te pertenece')
        return value

    def validate(self, attrs):
        """
        El modelo usa DecimalField(max_digits=10, decimal_places=7). Los floats JSON del cliente
        móvil traen precisión extra y DRF rechaza el total de dígitos; cuantizamos a 7 decimales.
        """
        q = Decimal('0.0000001')
        for key in ('latitude', 'longitude'):
            if key not in attrs:
                continue
            raw = attrs[key]
            try:
                attrs[key] = Decimal(str(raw)).quantize(q, rounding=ROUND_HALF_UP)
            except (InvalidOperation, TypeError, ValueError):
                raise serializers.ValidationError({key: 'Coordenada inválida'})
        return attrs


class IncidentStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[
        ('in_progress', 'En atención'),
        ('completed', 'Completado'),
        ('cancelled', 'Cancelado')
    ])
    notes = serializers.CharField(required=False, allow_blank=True)


class IncidentCompleteSerializer(serializers.Serializer):
    service_cost = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=True, min_value=Decimal('0')
    )
    notes = serializers.CharField(required=False, allow_blank=True)
