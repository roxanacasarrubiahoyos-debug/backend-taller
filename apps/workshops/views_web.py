from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from apps.workshops.models import Workshop, Technician
from apps.workshops.serializers import (
    WorkshopSerializer, WorkshopDetailSerializer, WorkshopCreateSerializer,
    WorkshopDashboardSerializer, TechnicianSerializer, TechnicianCreateSerializer,
    TechnicianAvailabilitySerializer, TechnicianLocationUpdateSerializer,
    TechnicianAppAccessSerializer,
    _split_technician_name,
)
from apps.users.models import Role
from django.contrib.auth import get_user_model

User = get_user_model()
from apps.users.permissions import IsWorkshopOwner
from apps.assignments.models import Assignment, AssignmentStatus
from apps.payments.models import Payment, PaymentStatus
from django.utils import timezone
from django.db import transaction
from datetime import datetime, timedelta
from decimal import Decimal


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsWorkshopOwner])
def workshop_detail(request):
    """Obtener y actualizar datos del taller del dueño autenticado"""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = WorkshopDetailSerializer(workshop)
        return Response(serializer.data)

    elif request.method in ['PUT', 'PATCH']:
        serializer = WorkshopSerializer(workshop, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(WorkshopDetailSerializer(workshop).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsWorkshopOwner])
def workshop_create(request):
    """Crear taller (solo si no tiene uno)"""
    if Workshop.objects.filter(owner=request.user.owner_profile).exists():
        return Response({'error': 'Ya tienes un taller registrado'}, status=status.HTTP_400_BAD_REQUEST)

    serializer = WorkshopCreateSerializer(data=request.data)
    if serializer.is_valid():
        workshop = serializer.save(owner=request.user.owner_profile)

        try:
            from apps.notifications.models import NotificationType
            from apps.notifications.web_panel_notify import notify_web_panel_admins

            notify_web_panel_admins(
                title='Taller pendiente de verificación',
                body=f'"{workshop.name}" registró su perfil y espera revisión.',
                notification_type=NotificationType.WORKSHOP_PENDING_REVIEW,
                data={'workshop_id': workshop.id, 'type': 'workshop_pending_review'},
                sse_payload={
                    'event': 'workshop_pending_review',
                    'workshop_id': workshop.id,
                    'workshop_name': workshop.name,
                    'title': 'Taller pendiente de verificación',
                    'body': f'"{workshop.name}" registró su perfil y espera revisión.',
                },
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception('notify admins workshop create: %s', exc)

        return Response(WorkshopDetailSerializer(workshop).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsWorkshopOwner])
def workshop_dashboard(request):
    """Métricas del taller: servicios, ingresos, calificación"""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    # Estadísticas de assignments
    total_services = Assignment.objects.filter(
        workshop=workshop,
        status=AssignmentStatus.COMPLETED
    ).count()

    pending_requests = Assignment.objects.filter(
        workshop=workshop,
        status=AssignmentStatus.OFFERED
    ).count()

    active_services = Assignment.objects.filter(
        workshop=workshop,
        status__in=[AssignmentStatus.ACCEPTED, AssignmentStatus.IN_ROUTE,
                   AssignmentStatus.ARRIVED, AssignmentStatus.IN_SERVICE]
    ).count()

    # Servicios completados este mes
    start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    completed_this_month = Assignment.objects.filter(
        workshop=workshop,
        status=AssignmentStatus.COMPLETED,
        completed_at__gte=start_of_month
    ).count()

    # Ingresos totales (suma de workshop_net_amount)
    payments = Payment.objects.filter(
        assignment__workshop=workshop,
        status__in=[PaymentStatus.CLIENT_PAID, PaymentStatus.COMMISSION_SETTLED]
    )
    total_earnings = sum(p.workshop_net_amount for p in payments) if payments.exists() else Decimal('0.00')

    month_payments = Payment.objects.filter(
        assignment__workshop=workshop,
        status__in=[PaymentStatus.CLIENT_PAID, PaymentStatus.COMMISSION_SETTLED],
        paid_at__gte=start_of_month,
    )
    earnings_this_month = (
        sum(p.workshop_net_amount for p in month_payments) if month_payments.exists() else Decimal('0.00')
    )

    # Técnicos disponibles
    available_technicians = workshop.technicians.filter(is_available=True).count()

    data = {
        'total_services': total_services,
        'pending_requests': pending_requests,
        'active_services': active_services,
        'completed_this_month': completed_this_month,
        'rating_avg': workshop.rating_avg,
        'total_earnings': total_earnings,
        'earnings_this_month': earnings_this_month,
        'available_technicians': available_technicians,
    }

    serializer = WorkshopDashboardSerializer(data)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsWorkshopOwner])
def workshop_earnings(request):
    """Resumen de ingresos y comisiones del taller"""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    payments = Payment.objects.filter(
        assignment__workshop=workshop,
        status__in=[PaymentStatus.CLIENT_PAID, PaymentStatus.COMMISSION_SETTLED]
    ).select_related('assignment').order_by('-created_at')

    total_gross = sum(p.total_amount for p in payments) if payments.exists() else Decimal('0.00')
    total_commission = sum(p.commission_amount for p in payments) if payments.exists() else Decimal('0.00')
    total_net = sum(p.workshop_net_amount for p in payments) if payments.exists() else Decimal('0.00')

    # Últimos pagos
    recent_payments = payments[:10]
    payments_data = []
    for payment in recent_payments:
        payments_data.append({
            'id': payment.id,
            'incident_id': payment.assignment.incident.id,
            'total_amount': payment.total_amount,
            'commission_amount': payment.commission_amount,
            'net_amount': payment.workshop_net_amount,
            'commission_rate': payment.commission_rate,
            'status': payment.status,
            'paid_at': payment.paid_at,
            'created_at': payment.created_at,
        })

    return Response({
        'summary': {
            'total_gross': total_gross,
            'total_commission': total_commission,
            'total_net': total_net,
            'total_payments': payments.count(),
        },
        'recent_payments': payments_data,
    })


class TechnicianViewSet(viewsets.ModelViewSet):
    """CRUD de técnicos del taller"""
    serializer_class = TechnicianSerializer
    permission_classes = [IsWorkshopOwner]

    def get_queryset(self):
        try:
            workshop = Workshop.objects.get(owner=self.request.user.owner_profile)
            return Technician.objects.filter(workshop=workshop).select_related('user').order_by('-id')
        except Workshop.DoesNotExist:
            return Technician.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return TechnicianCreateSerializer
        return TechnicianSerializer

    def perform_create(self, serializer):
        workshop = Workshop.objects.get(owner=self.request.user.owner_profile)
        serializer.save(workshop=workshop)

    @action(detail=True, methods=['patch'])
    def availability(self, request, pk=None):
        """Cambiar disponibilidad del técnico"""
        technician = self.get_object()
        serializer = TechnicianAvailabilitySerializer(data=request.data)
        if serializer.is_valid():
            technician.is_available = serializer.validated_data['is_available']
            technician.save()
            return Response(TechnicianSerializer(technician).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['patch'])
    def location(self, request, pk=None):
        """Actualizar ubicación del técnico"""
        technician = self.get_object()
        serializer = TechnicianLocationUpdateSerializer(data=request.data)
        if serializer.is_valid():
            technician.current_latitude = serializer.validated_data['latitude']
            technician.current_longitude = serializer.validated_data['longitude']
            technician.last_location_update = timezone.now()
            technician.save()
            return Response(TechnicianSerializer(technician).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='app-access')
    def app_access(self, request, pk=None):
        """Crear usuario técnico (app móvil) y vincularlo a un técnico existente."""
        technician = self.get_object()
        if technician.user_id:
            return Response(
                {'error': 'Este técnico ya tiene cuenta para la app'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = TechnicianAppAccessSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        d = ser.validated_data
        first, last = _split_technician_name(technician.name)
        if not first:
            first = d['app_username'][:30]
        with transaction.atomic():
            user = User.objects.create_user(
                username=d['app_username'],
                email=d['app_email'],
                password=d['app_password'],
                first_name=first,
                last_name=last,
                phone=technician.phone or '',
                role=Role.TECHNICIAN,
            )
            technician.user = user
            technician.save(update_fields=['user'])
        return Response(TechnicianSerializer(technician).data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsWorkshopOwner])
def create_stripe_connect_account(request):
    """Crear cuenta Stripe Connect para el taller"""
    try:
        owner_profile = request.user.owner_profile

        # Verificar si ya tiene cuenta
        if owner_profile.stripe_account_id:
            return Response({
                'error': 'Ya tienes una cuenta Stripe Connect',
                'account_id': owner_profile.stripe_account_id
            }, status=status.HTTP_400_BAD_REQUEST)

        # Crear cuenta en Stripe
        from apps.payments.stripe_service import StripeService
        result = StripeService.create_connected_account(
            email=request.user.email,
            country='US'  # Ajustar según el país del taller
        )

        if 'error' in result:
            return Response({'error': result['error']}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Guardar account_id
        owner_profile.stripe_account_id = result['account_id']
        owner_profile.save()

        return Response({
            'message': 'Cuenta Stripe Connect creada exitosamente',
            'account_id': result['account_id']
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsWorkshopOwner])
def create_stripe_onboarding_link(request):
    """Generar enlace de onboarding de Stripe Connect"""
    try:
        owner_profile = request.user.owner_profile

        # Si no tiene cuenta, crearla primero
        if not owner_profile.stripe_account_id:
            from apps.payments.stripe_service import StripeService
            result = StripeService.create_connected_account(
                email=request.user.email,
                country='US'
            )

            if 'error' in result:
                return Response({'error': result['error']}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            owner_profile.stripe_account_id = result['account_id']
            owner_profile.save()

        # Generar enlace de onboarding
        from apps.payments.stripe_service import StripeService
        from django.conf import settings

        base_url = request.build_absolute_uri('/')[:-1]  # Quitar la última /
        refresh_url = f"{base_url}/workshop-owner/profile?stripe_refresh=1"
        return_url = f"{base_url}/workshop-owner/profile?stripe_success=1"

        result = StripeService.create_stripe_account_link(
            account_id=owner_profile.stripe_account_id,
            refresh_url=refresh_url,
            return_url=return_url
        )

        if 'error' in result:
            return Response({'error': result['error']}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'url': result['url'],
            'account_id': owner_profile.stripe_account_id
        })
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsWorkshopOwner])
def stripe_connect_status(request):
    """Verificar estado de la cuenta Stripe Connect"""
    try:
        owner_profile = request.user.owner_profile

        if not owner_profile.stripe_account_id:
            return Response({
                'connected': False,
                'account_id': None,
                'details_submitted': False,
                'charges_enabled': False
            })

        # Verificar estado en Stripe
        import stripe
        from django.conf import settings

        stripe.api_key = settings.STRIPE_SECRET_KEY

        try:
            account = stripe.Account.retrieve(owner_profile.stripe_account_id)

            return Response({
                'connected': True,
                'account_id': owner_profile.stripe_account_id,
                'details_submitted': account.details_submitted,
                'charges_enabled': account.charges_enabled,
                'payouts_enabled': account.payouts_enabled if hasattr(account, 'payouts_enabled') else False
            })
        except stripe.error.StripeError as e:
            return Response({
                'connected': False,
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
