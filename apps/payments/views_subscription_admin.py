from rest_framework import viewsets, status
from rest_framework.response import Response

from apps.payments.models import WorkshopSubscriptionPlan
from apps.payments.subscription_serializers import WorkshopSubscriptionPlanSerializer
from apps.payments.subscription_service import sync_plan_to_stripe
from apps.users.permissions import IsAdmin


class WorkshopSubscriptionPlanViewSet(viewsets.ModelViewSet):
    queryset = WorkshopSubscriptionPlan.objects.all().order_by('sort_order', 'price_amount')
    serializer_class = WorkshopSubscriptionPlanSerializer
    permission_classes = [IsAdmin]

    def perform_create(self, serializer):
        plan = serializer.save()
        sync_plan_to_stripe(plan)

    def perform_update(self, serializer):
        plan = serializer.save()
        sync_plan_to_stripe(plan)

    def destroy(self, request, *args, **kwargs):
        plan = self.get_object()
        plan.is_active = False
        plan.is_public = False
        plan.save(update_fields=['is_active', 'is_public', 'updated_at'])
        sync_plan_to_stripe(plan)
        return Response(status=status.HTTP_204_NO_CONTENT)
