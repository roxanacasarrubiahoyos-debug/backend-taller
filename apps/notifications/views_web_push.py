from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.notifications.web_push_models import WebPushSubscription
from apps.notifications.web_push_service import vapid_configured, vapid_public_key
from apps.users.permissions import IsAdminOrWorkshopOwner


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminOrWorkshopOwner])
def vapid_public_key_view(request):
    """Clave pública VAPID para suscribir el navegador (sin Firebase)."""
    if not vapid_configured():
        return Response(
            {'error': 'Web Push no configurado en el servidor (VAPID).'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({'public_key': vapid_public_key()})


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdminOrWorkshopOwner])
def subscribe(request):
    """
    Registrar suscripción Web Push del panel.
    Body: { endpoint, keys: { p256dh, auth } }
    """
    endpoint = request.data.get('endpoint')
    keys = request.data.get('keys') or {}
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')
    if not endpoint or not p256dh or not auth:
        return Response(
            {'error': 'endpoint y keys.p256dh / keys.auth son obligatorios'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ua = (request.META.get('HTTP_USER_AGENT') or '')[:255]
    sub, created = WebPushSubscription.objects.update_or_create(
        user=request.user,
        endpoint=endpoint,
        defaults={
            'p256dh': p256dh,
            'auth': auth,
            'user_agent': ua,
            'is_active': True,
        },
    )
    return Response(
        {
            'message': 'Suscripción web registrada',
            'id': sub.id,
            'created': created,
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdminOrWorkshopOwner])
def unsubscribe(request):
    endpoint = request.data.get('endpoint')
    if endpoint:
        WebPushSubscription.objects.filter(user=request.user, endpoint=endpoint).update(is_active=False)
    else:
        WebPushSubscription.objects.filter(user=request.user).update(is_active=False)
    return Response({'message': 'Suscripción web desactivada'})
