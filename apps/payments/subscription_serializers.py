from rest_framework import serializers

from apps.payments.models import WorkshopOwnerSubscription, WorkshopSubscriptionPlan


class WorkshopSubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkshopSubscriptionPlan
        fields = [
            'id',
            'name',
            'description',
            'price_amount',
            'currency',
            'billing_interval',
            'max_technicians',
            'max_monthly_incidents',
            'features',
            'is_active',
            'is_public',
            'sort_order',
            'stripe_product_id',
            'stripe_price_id',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['stripe_product_id', 'stripe_price_id', 'created_at', 'updated_at']


class WorkshopSubscriptionPlanPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkshopSubscriptionPlan
        fields = [
            'id',
            'name',
            'description',
            'price_amount',
            'currency',
            'billing_interval',
            'max_technicians',
            'max_monthly_incidents',
            'features',
        ]


class WorkshopOwnerSubscriptionSerializer(serializers.ModelSerializer):
    plan = WorkshopSubscriptionPlanPublicSerializer(read_only=True)
    is_operational = serializers.BooleanField(read_only=True)

    class Meta:
        model = WorkshopOwnerSubscription
        fields = [
            'id',
            'status',
            'is_operational',
            'plan',
            'current_period_start',
            'current_period_end',
            'cancel_at_period_end',
            'stripe_subscription_id',
            'created_at',
            'updated_at',
        ]
