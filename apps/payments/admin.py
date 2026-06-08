from django.contrib import admin
from .models import CommissionConfig, Payment, WorkshopSubscriptionPlan, WorkshopOwnerSubscription


@admin.register(CommissionConfig)
class CommissionConfigAdmin(admin.ModelAdmin):
    list_display = ['percentage', 'effective_from', 'is_active', 'created_by', 'created_at']
    list_filter = ['is_active', 'effective_from', 'created_at']
    search_fields = ['description']
    raw_id_fields = ['created_by']
    readonly_fields = ['created_at']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'assignment', 'total_amount', 'commission_amount', 'status', 'created_at']
    list_filter = ['status', 'currency', 'created_at']
    search_fields = ['assignment__id', 'stripe_payment_intent_id', 'stripe_transfer_id']
    raw_id_fields = ['assignment', 'commission_config']
    readonly_fields = ['created_at', 'paid_at', 'settled_at']


@admin.register(WorkshopSubscriptionPlan)
class WorkshopSubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'price_amount', 'billing_interval', 'is_active', 'is_public', 'sort_order']
    list_filter = ['is_active', 'is_public', 'billing_interval']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(WorkshopOwnerSubscription)
class WorkshopOwnerSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['owner', 'plan', 'status', 'current_period_end', 'created_at']
    list_filter = ['status']
    search_fields = ['owner__user__email', 'stripe_subscription_id']
    readonly_fields = ['created_at', 'updated_at']