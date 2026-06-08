"""
Server-Sent Events usando django-eventstream.
El cliente Angular se suscribe a este endpoint
y recibe actualizaciones en tiempo real.

django-eventstream 5.x: events(request, channels=[...]) vía kwargs, no argumento posicional.
"""
from django_eventstream import send_event
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes, renderer_classes
from rest_framework.permissions import IsAuthenticated
from django_eventstream.views import events as eventstream_events
from rest_framework.renderers import BaseRenderer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
from apps.incidents.models import Incident


class _SseCompatibleRenderer(BaseRenderer):
    """
    DRF negocia contenido según Accept; las respuestas streaming de django-eventstream
    no pasan por renderers JSON y el cliente (p. ej. EventSource) puede recibir 406.
    """
    media_type = '*/*'
    format = 'sse'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


@api_view(['GET'])
@renderer_classes([_SseCompatibleRenderer])
@permission_classes([IsAuthenticated])
def notifications_stream(request):
    """
    SSE endpoint para notificaciones en tiempo real.
    Canal: user-<id> del usuario autenticado (JWT en Authorization).
    """
    channel = f'user-{request.user.id}'
    return eventstream_events(request, channels=[channel])


@api_view(['GET'])
@renderer_classes([_SseCompatibleRenderer])
def incident_stream(request, incident_id: int):
    """
    SSE por incidente para clientes móviles.
    Acepta JWT por query param `token` para facilitar EventSource en React Native.
    """
    user = None

    if getattr(request, 'user', None) and request.user.is_authenticated:
        user = request.user

    if user is None:
        raw_token = request.query_params.get('token') or request.GET.get('token')
        print("RAW TOKEN EXISTS:", bool(raw_token))

        if raw_token:
            print("RAW TOKEN PREFIX:", raw_token[:30])

        if not raw_token:
            return HttpResponse('Unauthorized', status=401)
        try:
            jwt_auth = JWTAuthentication()
            validated = jwt_auth.get_validated_token(raw_token)
            user = jwt_auth.get_user(validated)
        except (InvalidToken, AuthenticationFailed) as e:
            print("SSE TOKEN ERROR:", str(e))
            return HttpResponse('Unauthorized', status=401)

    profile = getattr(user, 'client_profile', None)
    if profile is None:
        return HttpResponse('Forbidden', status=403)
    exists = Incident.objects.filter(id=incident_id, client_id=profile.pk).exists()
    if not exists:
        return HttpResponse('Forbidden', status=403)

    channel = f'incident-{incident_id}'
    return eventstream_events(request, channels=[channel])


def notify_incident_update(incident_id: int, data: dict):
    channel = f'incident-{incident_id}'
    send_event(channel, 'message', data)


def notify_user(user_id: int, data: dict):
    channel = f'user-{user_id}'
    send_event(channel, 'message', data)


def notify_workshop(workshop_id: int, data: dict):
    channel = f'workshop-{workshop_id}'
    send_event(channel, 'message', data)
