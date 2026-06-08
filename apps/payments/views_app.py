from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from apps.users.permissions import IsClient
from apps.payments.models import Payment, PaymentStatus
from apps.payments.serializers import PaymentSerializer, PaymentIntentSerializer, PaymentConfirmSerializer
from apps.payments.stripe_service import StripeService
from apps.assignments.models import Assignment, AssignmentStatus
from django.utils import timezone
from rest_framework.permissions import AllowAny
from django.views.decorators.csrf import csrf_exempt
from apps.notifications.sse_views import notify_incident_update


@api_view(['POST'])
@permission_classes([IsClient])
def create_payment_intent(request):
    """
    Crear PaymentIntent en Stripe para que el cliente pague el servicio.
    Si se proporciona payment_method_id, adjunta el método y confirma automáticamente.
    """
    serializer = PaymentIntentSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    assignment_id = serializer.validated_data['assignment_id']
    payment_method_id = request.data.get('payment_method_id', None)

    try:
        assignment = Assignment.objects.select_related('incident', 'payment').get(id=assignment_id)
    except Assignment.DoesNotExist:
        return Response({'error': 'Asignación no encontrada'}, status=status.HTTP_404_NOT_FOUND)

    # Verificar que el cliente es dueño del incidente
    if assignment.incident.client != request.user.client_profile:
        return Response({'error': 'No tienes acceso a esta asignación'}, status=status.HTTP_403_FORBIDDEN)

    # Verificar que el servicio esté completado
    if assignment.status != AssignmentStatus.COMPLETED:
        return Response({'error': 'El servicio aún no está completado'}, status=status.HTTP_400_BAD_REQUEST)

    # Verificar que exista un pago asociado
    try:
        payment = assignment.payment
    except Payment.DoesNotExist:
        return Response({'error': 'No hay un pago asociado a esta asignación'}, status=status.HTTP_400_BAD_REQUEST)

    # Si ya fue pagado
    if payment.status in [PaymentStatus.CLIENT_PAID, PaymentStatus.COMMISSION_SETTLED]:
        return Response({'error': 'Este servicio ya fue pagado'}, status=status.HTTP_400_BAD_REQUEST)

    # Obtener stripe_customer_id del cliente
    client_profile = request.user.client_profile
    stripe_customer_id = client_profile.stripe_customer_id if client_profile.stripe_customer_id else None

    # Crear PaymentIntent (con confirmación automática si hay payment_method_id)
    stripe_service = StripeService()
    result = stripe_service.create_payment_intent(
        amount_usd=float(payment.total_amount),
        customer_id=stripe_customer_id if stripe_customer_id else '',
        payment_method_id=payment_method_id,
        metadata={
            'payment_id': str(payment.id),
            'assignment_id': str(assignment.id),
            'incident_id': str(assignment.incident.id),
            'client_email': request.user.email,
        }
    )

    if 'error' in result:
        return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)

    # Guardar el payment_intent_id
    payment.stripe_payment_intent_id = result['payment_intent_id']
    payment.save()

    # Respuesta según el flujo
    response_data = {
        'payment_id': payment.id,
        'payment_intent_id': result['payment_intent_id'],
        'amount': payment.total_amount,
        'status': result.get('status'),
    }

    # Si requiere acción adicional (3D Secure), devolver client_secret
    if result.get('requires_action'):
        response_data['requires_action'] = True
        response_data['client_secret'] = result['client_secret']

    # Si no se proporcionó payment_method_id, devolver client_secret para flujo manual
    if not payment_method_id:
        response_data['client_secret'] = result['client_secret']

    return Response(response_data)


@api_view(['POST'])
@permission_classes([IsClient])
def confirm_payment(request):
    """
    Confirmar que el pago fue exitoso (webhook alternativo desde cliente).
    Normalmente se maneja con webhook de Stripe, pero esto es un respaldo.
    """
    serializer = PaymentConfirmSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    payment_intent_id = serializer.validated_data['payment_intent_id']

    try:
        payment = Payment.objects.get(stripe_payment_intent_id=payment_intent_id)
    except Payment.DoesNotExist:
        return Response({'error': 'Pago no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    # Verificar que el cliente es dueño
    if payment.assignment.incident.client != request.user.client_profile:
        return Response({'error': 'No tienes acceso a este pago'}, status=status.HTTP_403_FORBIDDEN)

    # Marcar como pagado
    if payment.status == PaymentStatus.PENDING:
        payment.status = PaymentStatus.CLIENT_PAID
        payment.paid_at = timezone.now()
        payment.save()

        # Notificar al taller
        try:
            from apps.notifications.models import Notification, NotificationType
            from apps.notifications.firebase_service import FirebaseService

            workshop = payment.assignment.workshop
            owner_user = workshop.owner.user

            Notification.objects.create(
                user=owner_user,
                title='Pago recibido',
                body=f'Cliente pagó ${payment.total_amount} por servicio #{payment.assignment.incident.id}',
                notification_type=NotificationType.PAYMENT_CONFIRMED,
                incident=payment.assignment.incident,
                data={
                    'payment_id': payment.id,
                    'amount': str(payment.total_amount),
                    'workshop_id': workshop.id,
                    'assignment_id': payment.assignment_id,
                },
            )

            if owner_user.fcm_token:
                firebase = FirebaseService()
                firebase.send_notification(
                    token=owner_user.fcm_token,
                    title='Pago recibido',
                    body=f'${payment.total_amount} recibido',
                    data={'payment_id': str(payment.id), 'type': 'payment_confirmed'}
                )

            from apps.notifications.web_panel_notify import send_web_push_only
            send_web_push_only(
                user=owner_user,
                title='Pago recibido',
                body=f'Cliente pagó ${payment.total_amount} por servicio #{payment.assignment.incident.id}',
                data={
                    'payment_id': payment.id,
                    'type': 'payment_confirmed',
                    'workshop_id': workshop.id,
                    'assignment_id': payment.assignment_id,
                },
            )
        except Exception as e:
            print(f"Error sending notification: {e}")

    return Response({
        'message': 'Pago confirmado',
        'payment_id': payment.id,
        'status': payment.status,
    })


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def stripe_webhook(request):
    """
    Webhook Stripe:
    - payment_intent.succeeded -> marca client_paid y transfiere neto al taller (Connect)
    """
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    payload = request.body

    try:
        event = StripeService.handle_webhook(payload, sig_header)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    event_type = event.get('type')
    data = event.get('data', {}).get('object', {})

    if event_type == 'checkout.session.completed':
        from apps.payments.subscription_service import handle_checkout_session_completed
        handle_checkout_session_completed(data)
        return Response({'ok': True})

    if event_type in ('customer.subscription.updated', 'customer.subscription.created'):
        from apps.payments.subscription_service import apply_stripe_subscription
        apply_stripe_subscription(data)
        return Response({'ok': True})

    if event_type == 'customer.subscription.deleted':
        from apps.payments.subscription_service import apply_stripe_subscription
        canceled = {**data, 'status': 'canceled'}
        apply_stripe_subscription(canceled)
        return Response({'ok': True})

    if event_type == 'invoice.payment_failed':
        sub_id = data.get('subscription')
        if sub_id:
            from apps.payments.models import WorkshopOwnerSubscription, WorkshopSubscriptionStatus
            WorkshopOwnerSubscription.objects.filter(
                stripe_subscription_id=sub_id
            ).update(status=WorkshopSubscriptionStatus.PAST_DUE)
        return Response({'ok': True})

    if event_type == 'payment_intent.succeeded':
        payment_intent_id = data.get('id')
        if not payment_intent_id:
            return Response({'ok': True})

        try:
            payment = Payment.objects.select_related(
                'assignment',
                'assignment__workshop',
                'assignment__workshop__owner',
                'assignment__workshop__owner__user',
            ).get(stripe_payment_intent_id=payment_intent_id)
        except Payment.DoesNotExist:
            return Response({'ok': True})

        if payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.CLIENT_PAID
            payment.paid_at = timezone.now()
            payment.stripe_charge_id = (data.get('latest_charge') or '')[:100]
            payment.save(update_fields=['status', 'paid_at', 'stripe_charge_id'])

        workshop_owner_profile = payment.assignment.workshop.owner
        stripe_account_id = workshop_owner_profile.stripe_account_id

        if stripe_account_id and payment.status in [PaymentStatus.CLIENT_PAID, PaymentStatus.PENDING]:
            transfer_result = StripeService.transfer_to_workshop(
                amount_usd=float(payment.workshop_net_amount),
                stripe_account_id=stripe_account_id,
                metadata={
                    'payment_id': str(payment.id),
                    'assignment_id': str(payment.assignment_id),
                    'incident_id': str(payment.assignment.incident_id),
                },
            )
            transfer_id = transfer_result.get('transfer_id')
            if transfer_id:
                payment.stripe_transfer_id = transfer_id
                payment.status = PaymentStatus.COMMISSION_SETTLED
                payment.settled_at = timezone.now()
                payment.save(update_fields=['stripe_transfer_id', 'status', 'settled_at'])

        try:
            from apps.notifications.models import Notification, NotificationType
            from apps.notifications.firebase_service import FirebaseService
            owner_user = workshop_owner_profile.user
            ws = payment.assignment.workshop
            Notification.objects.create(
                user=owner_user,
                title='Pago recibido',
                body=f'Pago confirmado. Neto a recibir: ${payment.workshop_net_amount}',
                notification_type=NotificationType.PAYMENT_CONFIRMED,
                incident=payment.assignment.incident,
                data={
                    'payment_id': payment.id,
                    'total_amount': str(payment.total_amount),
                    'net_amount': str(payment.workshop_net_amount),
                    'workshop_id': ws.id,
                    'assignment_id': payment.assignment_id,
                },
                push_sent=bool(owner_user.fcm_token),
            )
            if owner_user.fcm_token:
                firebase = FirebaseService()
                firebase.send_notification(
                    token=owner_user.fcm_token,
                    title='Pago recibido',
                    body=f'Recibirás ${payment.workshop_net_amount} en tu cuenta Stripe.',
                    data={'payment_id': str(payment.id), 'type': 'payment_confirmed'},
                )

            from apps.notifications.web_panel_notify import send_web_push_only
            send_web_push_only(
                user=owner_user,
                title='Pago recibido',
                body=f'Pago confirmado. Neto a recibir: ${payment.workshop_net_amount}',
                data={
                    'payment_id': payment.id,
                    'type': 'payment_confirmed',
                    'workshop_id': ws.id,
                    'assignment_id': payment.assignment_id,
                },
            )
        except Exception as e:
            print(f"Webhook notification error: {e}")

        notify_incident_update(payment.assignment.incident_id, {
            'event': 'payment_confirmed',
            'incident_id': payment.assignment.incident_id,
            'payment_status': payment.status,
            'amount': float(payment.total_amount),
        })

    return Response({'ok': True})


@api_view(['GET'])
@permission_classes([IsClient])
def payment_history(request):
    """Historial de pagos del cliente"""
    payments = Payment.objects.filter(
        assignment__incident__client=request.user.client_profile
    ).select_related('assignment', 'assignment__workshop').order_by('-created_at')

    data = []
    for payment in payments:
        data.append({
            'id': payment.id,
            'incident_id': payment.assignment.incident.id,
            'workshop_name': payment.assignment.workshop.name,
            'total_amount': payment.total_amount,
            'status': payment.get_status_display(),
            'paid_at': payment.paid_at,
            'created_at': payment.created_at,
        })

    return Response(data)


@api_view(['GET'])
@permission_classes([IsClient])
def payment_detail(request, pk):
    """Detalle de un pago"""
    try:
        payment = Payment.objects.select_related('assignment', 'assignment__workshop').get(id=pk)
    except Payment.DoesNotExist:
        return Response({'error': 'Pago no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    # Verificar acceso
    if payment.assignment.incident.client != request.user.client_profile:
        return Response({'error': 'No tienes acceso a este pago'}, status=status.HTTP_403_FORBIDDEN)

    serializer = PaymentSerializer(payment)
    return Response(serializer.data)
