from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from apps.users.permissions import IsWorkshopOwner
from apps.payments.models import Payment, PaymentStatus
from apps.payments.serializers import PaymentSerializer, EarningsSummarySerializer
from apps.workshops.models import Workshop
from decimal import Decimal


@api_view(['GET'])
@permission_classes([IsWorkshopOwner])
def earnings_summary(request):
    """Resumen de ingresos del taller con desglose de comisiones"""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    # Obtener todos los pagos del taller
    payments = Payment.objects.filter(assignment__workshop=workshop)

    total_services = payments.count()
    total_earnings_gross = sum(p.total_amount for p in payments) if payments.exists() else Decimal('0.00')
    total_commission = sum(p.commission_amount for p in payments) if payments.exists() else Decimal('0.00')
    total_earnings_net = sum(p.workshop_net_amount for p in payments) if payments.exists() else Decimal('0.00')

    pending_payments = payments.filter(status=PaymentStatus.PENDING).count()
    completed_payments = payments.filter(
        status__in=[PaymentStatus.CLIENT_PAID, PaymentStatus.COMMISSION_SETTLED]
    ).count()

    data = {
        'total_services': total_services,
        'total_earnings_gross': total_earnings_gross,
        'total_commission': total_commission,
        'total_earnings_net': total_earnings_net,
        'pending_payments': pending_payments,
        'completed_payments': completed_payments,
    }

    serializer = EarningsSummarySerializer(data)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsWorkshopOwner])
def payment_list(request):
    """Lista de pagos del taller"""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    payments = Payment.objects.filter(
        assignment__workshop=workshop
    ).select_related('assignment', 'assignment__incident').order_by('-created_at')

    serializer = PaymentSerializer(payments, many=True)
    return Response(serializer.data)
