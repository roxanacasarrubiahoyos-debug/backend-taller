import json

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers
from apps.workshops.models import Workshop, Technician, WorkshopRating
from apps.workshops.geo import is_valid_coordinate_pair
from apps.users.models import Role
from decimal import Decimal

User = get_user_model()


def _split_technician_name(full_name):
    full_name = (full_name or '').strip()
    if not full_name:
        return '', ''
    parts = full_name.split(None, 1)
    return parts[0], (parts[1] if len(parts) > 1 else '')


def parse_services_list(value):
    """Multipart/form-data envía `services` como string JSON; normaliza a lista."""
    if value is None or value == '':
        return []
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except json.JSONDecodeError as e:
            raise serializers.ValidationError(
                'services debe ser un JSON válido (lista de categorías).'
            ) from e
        if not isinstance(data, list):
            raise serializers.ValidationError('services debe ser una lista.')
        return data
    if isinstance(value, list):
        return value
    raise serializers.ValidationError('Formato de services inválido.')


class TechnicianSerializer(serializers.ModelSerializer):
    has_app_access = serializers.SerializerMethodField()
    app_username = serializers.SerializerMethodField()

    class Meta:
        model = Technician
        fields = [
            'id', 'name', 'phone', 'specialties', 'is_available',
            'current_latitude', 'current_longitude', 'last_location_update', 'photo',
            'has_app_access', 'app_username',
        ]
        read_only_fields = ['id', 'has_app_access', 'app_username']

    def get_has_app_access(self, obj):
        return obj.user_id is not None

    def get_app_username(self, obj):
        if not obj.user_id:
            return None
        return getattr(obj.user, 'username', None)


class WorkshopRatingSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.user.get_full_name', read_only=True)

    class Meta:
        model = WorkshopRating
        fields = ['id', 'workshop', 'client', 'assignment', 'client_name', 'score', 'comment', 'created_at']
        read_only_fields = ['id', 'created_at']


class RateWorkshopSerializer(serializers.Serializer):
    assignment_id = serializers.IntegerField(required=True)
    score = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class WorkshopSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.user.get_full_name', read_only=True)

    class Meta:
        model = Workshop
        fields = [
            'id', 'owner', 'owner_name', 'name', 'description', 'address',
            'latitude', 'longitude', 'phone', 'email', 'logo', 'services',
            'radius_km', 'is_active', 'is_verified', 'rating_avg',
            'total_services', 'created_at'
        ]
        read_only_fields = [
            'id', 'owner', 'rating_avg', 'total_services', 'created_at', 'is_verified',
        ]

    def validate_services(self, value):
        return parse_services_list(value)

    def validate(self, attrs):
        lat = attrs.get('latitude', getattr(self.instance, 'latitude', None))
        lng = attrs.get('longitude', getattr(self.instance, 'longitude', None))
        if lat is not None and lng is not None and not is_valid_coordinate_pair(lat, lng):
            raise serializers.ValidationError(
                'latitude y longitude deben ser válidas (lat -90..90, lng -180..180).'
            )
        return attrs


class WorkshopDetailSerializer(WorkshopSerializer):
    technicians = TechnicianSerializer(many=True, read_only=True)
    recent_ratings = serializers.SerializerMethodField()

    class Meta(WorkshopSerializer.Meta):
        fields = WorkshopSerializer.Meta.fields + ['technicians', 'recent_ratings']

    def get_recent_ratings(self, obj):
        ratings = obj.ratings.order_by('-created_at')[:5]
        return WorkshopRatingSerializer(ratings, many=True).data


class WorkshopCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workshop
        fields = [
            'name', 'description', 'address', 'latitude', 'longitude',
            'phone', 'email', 'logo', 'services', 'radius_km'
        ]

    def validate_services(self, value):
        return parse_services_list(value)

    def validate(self, attrs):
        if not is_valid_coordinate_pair(attrs.get('latitude'), attrs.get('longitude')):
            raise serializers.ValidationError(
                'latitude y longitude deben ser válidas (lat -90..90, lng -180..180).'
            )
        return attrs

    def create(self, validated_data):
        # El owner viene del request.user.owner_profile
        return Workshop.objects.create(**validated_data)


class NearbyWorkshopsSerializer(serializers.ModelSerializer):
    distance = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)
    distance_km = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)
    available_technicians = serializers.IntegerField(read_only=True)

    class Meta:
        model = Workshop
        fields = [
            'id', 'name', 'description', 'address', 'latitude', 'longitude',
            'phone', 'logo', 'services', 'rating_avg', 'total_services',
            'distance', 'distance_km', 'available_technicians'
        ]


class WorkshopDashboardSerializer(serializers.Serializer):
    total_services = serializers.IntegerField()
    pending_requests = serializers.IntegerField()
    active_services = serializers.IntegerField()
    completed_this_month = serializers.IntegerField()
    rating_avg = serializers.DecimalField(max_digits=3, decimal_places=2)
    total_earnings = serializers.DecimalField(max_digits=10, decimal_places=2)
    earnings_this_month = serializers.DecimalField(max_digits=10, decimal_places=2)
    available_technicians = serializers.IntegerField()


class TechnicianCreateSerializer(serializers.ModelSerializer):
    """
    Alta de técnico. Opcionalmente crea User (role=technician) para la app móvil.
    """

    enable_app_access = serializers.BooleanField(default=False, write_only=True)
    app_username = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=150)
    app_email = serializers.EmailField(required=False, allow_blank=True, write_only=True)
    app_password = serializers.CharField(
        required=False, write_only=True, min_length=6, max_length=128, style={'input_type': 'password'}
    )
    app_password_confirm = serializers.CharField(
        required=False, write_only=True, style={'input_type': 'password'}
    )

    class Meta:
        model = Technician
        fields = [
            'name', 'phone', 'specialties', 'photo',
            'enable_app_access', 'app_username', 'app_email', 'app_password', 'app_password_confirm',
        ]

    def validate(self, attrs):
        enable = attrs.get('enable_app_access', False)
        if not enable:
            return attrs
        u = (attrs.get('app_username') or '').strip()
        e = (attrs.get('app_email') or '').strip()
        p1 = attrs.get('app_password')
        p2 = attrs.get('app_password_confirm')
        if not u:
            raise serializers.ValidationError({'app_username': 'Usuario requerido para acceso a la app'})
        if not e:
            raise serializers.ValidationError({'app_email': 'Email requerido para acceso a la app'})
        if not p1 or not p2:
            raise serializers.ValidationError({'app_password': 'Contraseña requerida'})
        if p1 != p2:
            raise serializers.ValidationError({'app_password_confirm': 'Las contraseñas no coinciden'})
        if User.objects.filter(username__iexact=u).exists():
            raise serializers.ValidationError({'app_username': 'Este nombre de usuario ya existe'})
        if User.objects.filter(email__iexact=e).exists():
            raise serializers.ValidationError({'app_email': 'Este email ya está registrado'})
        return attrs

    def create(self, validated_data):
        enable = validated_data.pop('enable_app_access', False)
        app_username = (validated_data.pop('app_username', '') or '').strip()
        app_email = (validated_data.pop('app_email', '') or '').strip()
        app_password = validated_data.pop('app_password', None)
        validated_data.pop('app_password_confirm', None)
        workshop = validated_data.pop('workshop')

        with transaction.atomic():
            tech = Technician.objects.create(workshop=workshop, **validated_data)
            if enable and app_password:
                first, last = _split_technician_name(tech.name)
                user = User.objects.create_user(
                    username=app_username,
                    email=app_email,
                    password=app_password,
                    first_name=first,
                    last_name=last,
                    phone=tech.phone or '',
                    role=Role.TECHNICIAN,
                )
                tech.user = user
                tech.save(update_fields=['user'])
        return tech


class TechnicianAppAccessSerializer(serializers.Serializer):
    """Vincular cuenta de app a un técnico existente (sin usuario)."""

    app_username = serializers.CharField(max_length=150)
    app_email = serializers.EmailField()
    app_password = serializers.CharField(min_length=6, max_length=128, write_only=True)
    app_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['app_password'] != attrs['app_password_confirm']:
            raise serializers.ValidationError({'app_password_confirm': 'Las contraseñas no coinciden'})
        u = attrs['app_username'].strip()
        e = attrs['app_email'].strip()
        if User.objects.filter(username__iexact=u).exists():
            raise serializers.ValidationError({'app_username': 'Este nombre de usuario ya existe'})
        if User.objects.filter(email__iexact=e).exists():
            raise serializers.ValidationError({'app_email': 'Este email ya está registrado'})
        attrs['app_username'] = u
        attrs['app_email'] = e
        return attrs


class TechnicianLocationUpdateSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=True)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=True)

    def validate(self, attrs):
        if not is_valid_coordinate_pair(attrs.get('latitude'), attrs.get('longitude')):
            raise serializers.ValidationError(
                'latitude y longitude deben ser válidas (lat -90..90, lng -180..180).'
            )
        return attrs


class TechnicianAvailabilitySerializer(serializers.Serializer):
    is_available = serializers.BooleanField(required=True)
