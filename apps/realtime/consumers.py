from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.assignments.models import Assignment, AssignmentStatus
from apps.users.models import Role

# Radio para avisar al cliente una sola vez (metros). Ajustable vía settings si hace falta.
NEARBY_CLIENT_RADIUS_M = 450


def _is_valid_technician_gps(latitude, longitude):
    """Rechaza null island y valores fuera de rango (evita guardar 0,0 y romper mapas)."""
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return False
    if abs(lat) < 1e-6 and abs(lng) < 1e-6:
        return False
    return True


@database_sync_to_async
def get_user_from_jwt(token):
    if not token:
        return None
    try:
        access = AccessToken(token)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        return User.objects.select_related(
            'client_profile', 'technician_profile__workshop'
        ).get(pk=access['user_id'])
    except (TokenError, InvalidToken, User.DoesNotExist, KeyError):
        return None


@database_sync_to_async
def incident_access_allowed(user, incident_id):
    from apps.incidents.models import Incident

    try:
        incident = Incident.objects.get(pk=incident_id)
    except Incident.DoesNotExist:
        return False

    if user.role == Role.CLIENT:
        profile = getattr(user, 'client_profile', None)
        if profile is not None:
            return incident.client_id == profile.pk

    if user.role == Role.TECHNICIAN:
        tech_profile = getattr(user, 'technician_profile', None)
        if tech_profile is not None:
            return Assignment.objects.filter(
                incident_id=incident_id,
                technician_id=tech_profile.pk,
                status__in=[
                    AssignmentStatus.ACCEPTED,
                    AssignmentStatus.IN_ROUTE,
                    AssignmentStatus.ARRIVED,
                    AssignmentStatus.IN_SERVICE,
                ],
            ).exists()

    return False


@database_sync_to_async
def save_technician_location(user, latitude, longitude):
    from decimal import Decimal

    tech = getattr(user, 'technician_profile', None)
    if not tech:
        return False
    q = Decimal('0.0000001')
    tech.current_latitude = Decimal(str(latitude)).quantize(q)
    tech.current_longitude = Decimal(str(longitude)).quantize(q)
    tech.last_location_update = timezone.now()
    tech.save(update_fields=['current_latitude', 'current_longitude', 'last_location_update'])
    return True


def _haversine_m(lat1, lon1, lat2, lon2):
    from math import atan2, cos, radians, sin, sqrt

    r = 6371000.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))


@database_sync_to_async
def maybe_notify_client_technician_nearby(incident_id, technician_pk, tech_lat, tech_lng):
    """
    Si el técnico está en ruta y entra en el radio del incidente, una sola push al cliente.
    """
    from django.db import transaction

    from apps.incidents.models import Incident

    try:
        incident = Incident.objects.get(pk=incident_id)
    except Incident.DoesNotExist:
        return

    try:
        tech_lat_f = float(tech_lat)
        tech_lng_f = float(tech_lng)
        cli_lat = float(incident.latitude)
        cli_lng = float(incident.longitude)
    except (TypeError, ValueError):
        return

    dist = _haversine_m(tech_lat_f, tech_lng_f, cli_lat, cli_lng)
    if dist > NEARBY_CLIENT_RADIUS_M:
        return

    with transaction.atomic():
        assignment = (
            Assignment.objects.select_for_update()
            .filter(
                incident_id=incident_id,
                technician_id=technician_pk,
                status=AssignmentStatus.IN_ROUTE,
                client_nearby_notified_at__isnull=True,
            )
            .first()
        )
        if not assignment:
            return
        assignment.client_nearby_notified_at = timezone.now()
        assignment.save(update_fields=['client_nearby_notified_at'])

    try:
        from apps.notifications.models import Notification, NotificationType
        from apps.notifications.firebase_service import FirebaseService

        client_user = incident.client.user
        tech_name = assignment.technician.name if assignment.technician else 'El técnico'
        title = 'Tu técnico está cerca'
        body = f'{tech_name} está a unos {int(round(dist))} m de tu ubicación.'

        Notification.objects.create(
            user=client_user,
            title=title,
            body=body,
            notification_type=NotificationType.TECHNICIAN_NEARBY,
            incident=incident,
            data={'incident_id': incident.id, 'distance_m': int(round(dist))},
            push_sent=bool(client_user.fcm_token),
        )
        if client_user.fcm_token:
            FirebaseService().send_notification(
                token=client_user.fcm_token,
                title=title,
                body=body,
                data={
                    'type': 'technician_nearby',
                    'incident_id': str(incident.id),
                    'distance_m': str(int(round(dist))),
                },
            )
    except Exception as e:
        print(f'Error sending technician nearby push: {e}')


class IncidentTrackingConsumer(AsyncJsonWebsocketConsumer):
    """
    Canal bidireccional por incidente:
    - Cliente: recibe ubicación del técnico en tiempo real.
    - Técnico asignado: envía {type: "location", latitude, longitude}.
    """

    async def connect(self):
        self.incident_id = int(self.scope['url_route']['kwargs']['incident_id'])
        query = parse_qs(self.scope.get('query_string', b'').decode())
        token = (query.get('token') or [None])[0]

        self.user = await get_user_from_jwt(token)
        if not self.user:
            await self.close(code=4001)
            return

        allowed = await incident_access_allowed(self.user, self.incident_id)
        if not allowed:
            await self.close(code=4003)
            return

        self.group_name = f'incident_{self.incident_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(
            {
                'type': 'connected',
                'incident_id': self.incident_id,
                'role': self.user.role,
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if self.user.role != Role.TECHNICIAN:
            return

        msg_type = content.get('type')
        if msg_type != 'location':
            return

        lat = content.get('latitude')
        lng = content.get('longitude')
        if lat is None or lng is None:
            return
        if not _is_valid_technician_gps(lat, lng):
            return

        ok = await save_technician_location(self.user, lat, lng)
        if not ok:
            return

        tech_profile = getattr(self.user, 'technician_profile', None)
        if tech_profile:
            await maybe_notify_client_technician_nearby(
                self.incident_id, tech_profile.pk, lat, lng
            )

        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'tracking_broadcast',
                'latitude': float(lat),
                'longitude': float(lng),
                'ts': timezone.now().isoformat(),
            },
        )

    async def tracking_broadcast(self, event):
        await self.send_json(
            {
                'type': 'technician_location',
                'latitude': event['latitude'],
                'longitude': event['longitude'],
                'ts': event.get('ts'),
            }
        )
