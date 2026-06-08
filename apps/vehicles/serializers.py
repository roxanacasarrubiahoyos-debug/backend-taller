from rest_framework import serializers
from apps.vehicles.models import Vehicle


class VehicleSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.user.get_full_name', read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            'id', 'client', 'client_name', 'brand', 'model', 'year', 'plate',
            'color', 'vehicle_type', 'vin', 'is_active', 'photo', 'created_at'
        ]
        read_only_fields = ['id', 'client', 'created_at']


class VehicleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            'brand', 'model', 'year', 'plate', 'color',
            'vehicle_type', 'vin', 'photo'
        ]

    def validate_plate(self, value):
        # Verificar que la placa sea única
        if Vehicle.objects.filter(plate=value).exists():
            raise serializers.ValidationError("Esta placa ya está registrada")
        return value.upper()


class VehicleUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ['brand', 'model', 'year', 'color', 'photo', 'is_active']
