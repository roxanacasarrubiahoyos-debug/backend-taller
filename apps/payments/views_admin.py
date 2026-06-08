from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from apps.users.permissions import IsAdmin
from apps.payments.models import Payment, CommissionConfig, PaymentStatus
from apps.payments.serializers import (
    PaymentSerializer, CommissionConfigSerializer, MetricsSerializer
)
from apps.users.models import User, Role
from apps.workshops.models import Workshop, WorkshopRating
from apps.incidents.models import Incident, IncidentStatus, IncidentCycleMetric
from django.utils import timezone
from decimal import Decimal
from django.db.models import Avg


class CommissionConfigViewSet(viewsets.ModelViewSet):
    """Gestión de configuración de comisiones (solo admin)"""
    queryset = CommissionConfig.objects.all().order_by('-effective_from')
    serializer_class = CommissionConfigSerializer
    permission_classes = [IsAdmin]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Comisión aplicable hoy (última vigente por effective_from, ver flujo_operativo_emergencias Fase 1)."""
        config = CommissionConfig.get_applicable_for_date()

        if config:
            serializer = CommissionConfigSerializer(config)
            return Response(serializer.data)
        return Response({'error': 'No hay configuración de comisión activa'}, status=status.HTTP_404_NOT_FOUND)


class PaymentAdminViewSet(viewsets.ReadOnlyModelViewSet):
    """Visualización de todos los pagos (solo admin)"""
    queryset = Payment.objects.all().order_by('-created_at')
    serializer_class = PaymentSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ['status']


@api_view(['GET'])
@permission_classes([IsAdmin])
def platform_metrics(request):
    """Métricas globales de la plataforma"""

    # Usuarios
    total_users = User.objects.count()
    total_clients = User.objects.filter(role=Role.CLIENT).count()
    total_workshops = Workshop.objects.count()

    # Incidentes
    total_incidents = Incident.objects.count()
    start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    incidents_this_month = Incident.objects.filter(created_at__gte=start_of_month).count()
    active_incidents = Incident.objects.filter(
        status__in=[IncidentStatus.PENDING, IncidentStatus.ANALYZING,
                   IncidentStatus.WAITING_WORKSHOP, IncidentStatus.ASSIGNED,
                   IncidentStatus.IN_PROGRESS]
    ).count()
    completed_incidents = Incident.objects.filter(status=IncidentStatus.COMPLETED).count()

    # Ingresos
    payments = Payment.objects.filter(
        status__in=[PaymentStatus.CLIENT_PAID, PaymentStatus.COMMISSION_SETTLED]
    )
    total_revenue = sum(p.total_amount for p in payments) if payments.exists() else Decimal('0.00')
    total_commission_earned = sum(p.commission_amount for p in payments) if payments.exists() else Decimal('0.00')

    payments_month = Payment.objects.filter(
        status__in=[PaymentStatus.CLIENT_PAID, PaymentStatus.COMMISSION_SETTLED],
        paid_at__gte=start_of_month,
    )
    commission_this_month = (
        sum(p.commission_amount for p in payments_month) if payments_month.exists() else Decimal('0.00')
    )

    resolution_rate_pct = round(
        (completed_incidents / total_incidents * 100.0) if total_incidents else 0.0,
        1,
    )

    avg_assign = IncidentCycleMetric.objects.aggregate(a=Avg('seconds_to_assignment'))['a']
    avg_assignment_seconds = float(avg_assign) if avg_assign is not None else None

    pr_avg = WorkshopRating.objects.aggregate(a=Avg('score'))['a']
    platform_rating_avg = round(float(pr_avg), 2) if pr_avg is not None else None

    ia_sample_predicted_type = ''
    ia_sample_confidence = None
    last_metric = (
        IncidentCycleMetric.objects.exclude(ai_predicted_type='')
        .order_by('-created_at')
        .first()
    )
    if last_metric:
        ia_sample_predicted_type = last_metric.ai_predicted_type or ''
        ia_sample_confidence = last_metric.ai_confidence

    data = {
        'total_users': total_users,
        'total_clients': total_clients,
        'total_workshops': total_workshops,
        'total_incidents': total_incidents,
        'incidents_this_month': incidents_this_month,
        'total_revenue': total_revenue,
        'total_commission_earned': total_commission_earned,
        'active_incidents': active_incidents,
        'completed_incidents': completed_incidents,
        'resolution_rate_pct': resolution_rate_pct,
        'avg_assignment_seconds': avg_assignment_seconds,
        'commission_this_month': commission_this_month,
        'platform_rating_avg': platform_rating_avg,
        'ia_sample_predicted_type': ia_sample_predicted_type,
        'ia_sample_confidence': ia_sample_confidence,
    }

    serializer = MetricsSerializer(data)
    return Response(serializer.data)
