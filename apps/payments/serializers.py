from rest_framework import serializers
from apps.payments.models import Payment, CommissionConfig
from decimal import Decimal


class CommissionConfigSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = CommissionConfig
        fields = [
            'id', 'percentage', 'description', 'effective_from',
            'created_by', 'created_by_name', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at']


class PaymentSerializer(serializers.ModelSerializer):
    workshop_name = serializers.CharField(source='assignment.workshop.name', read_only=True)
    client_name = serializers.CharField(source='assignment.incident.client.user.get_full_name', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id', 'assignment', 'workshop_name', 'client_name',
            'total_amount', 'commission_rate', 'commission_amount',
            'workshop_net_amount', 'status', 'currency',
            'paid_at', 'settled_at', 'created_at'
        ]
        read_only_fields = [
            'id', 'commission_rate', 'commission_amount',
            'workshop_net_amount', 'status', 'paid_at', 'settled_at', 'created_at'
        ]


class PaymentIntentSerializer(serializers.Serializer):
    assignment_id = serializers.IntegerField(required=True)
    payment_method_id = serializers.CharField(required=False, allow_blank=True)


class PaymentConfirmSerializer(serializers.Serializer):
    payment_intent_id = serializers.CharField(required=True)


class EarningsSummarySerializer(serializers.Serializer):
    total_services = serializers.IntegerField()
    total_earnings_gross = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_commission = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_earnings_net = serializers.DecimalField(max_digits=10, decimal_places=2)
    pending_payments = serializers.IntegerField()
    completed_payments = serializers.IntegerField()


class MetricsSerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    total_clients = serializers.IntegerField()
    total_workshops = serializers.IntegerField()
    total_incidents = serializers.IntegerField()
    incidents_this_month = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_commission_earned = serializers.DecimalField(max_digits=12, decimal_places=2)
    active_incidents = serializers.IntegerField()
    completed_incidents = serializers.IntegerField()
    resolution_rate_pct = serializers.FloatField()
    avg_assignment_seconds = serializers.FloatField(allow_null=True)
    commission_this_month = serializers.DecimalField(max_digits=12, decimal_places=2)
    platform_rating_avg = serializers.FloatField(allow_null=True)
    ia_sample_predicted_type = serializers.CharField(allow_blank=True)
    ia_sample_confidence = serializers.FloatField(allow_null=True)
