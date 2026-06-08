from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apps.workshops.models import Workshop, WorkshopRating
from apps.workshops.serializers import (
    WorkshopDetailSerializer, NearbyWorkshopsSerializer,
    WorkshopRatingSerializer, RateWorkshopSerializer,
)
from apps.notifications.models import Notification, NotificationType
from apps.notifications.sse_views import notify_user

from apps.assignments.models import Assignment, AssignmentStatus
from apps.workshops.eligibility import workshop_visible_in_nearby
from apps.workshops.geo import coordinate_pair, distance_km
from django.db.models import Avg
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def nearby_workshops(request):
    """Buscar talleres cercanos"""
    # Compatibilidad con clientes que envían lat/lng o latitude/longitude
    lat = request.query_params.get('latitude') or request.query_params.get('lat')
    lng = request.query_params.get('longitude') or request.query_params.get('lng')
    radius = request.query_params.get('radius', 15)  # km

    if not lat or not lng:
        return Response({'error': 'Se requieren latitude y longitude'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        radius = float(radius)
    except ValueError:
        return Response({'error': 'Radio inválido'}, status=status.HTTP_400_BAD_REQUEST)

    user_location = coordinate_pair(lat, lng)
    if user_location is None:
        return Response(
            {
                'error': (
                    'Coordenadas fuera de rango. '
                    'Latitud entre -90 y 90; longitud entre -180 y 180.'
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    workshops = (
        Workshop.objects.filter(
            is_active=True,
            is_verified=True,
            latitude__gte=-90,
            latitude__lte=90,
            longitude__gte=-180,
            longitude__lte=180,
        )
        .prefetch_related('technicians', 'owner', 'owner__subscription')
    )

    nearby = []
    for workshop in workshops:
        if not workshop_visible_in_nearby(workshop):
            continue
        dist_km = distance_km(user_location, (workshop.latitude, workshop.longitude))
        if dist_km is None:
            logger.warning(
                'nearby_workshops: omitiendo taller id=%s con coordenadas inválidas (%s, %s)',
                workshop.id,
                workshop.latitude,
                workshop.longitude,
            )
            continue

        # Radio de búsqueda del cliente (p. ej. 20 km); el radio del taller aplica al motor de asignación.
        if dist_km <= radius:
            workshop.distance = Decimal(str(round(dist_km, 2)))
            workshop.distance_km = workshop.distance
            workshop.available_technicians = workshop.technicians.filter(is_available=True).count()
            nearby.append(workshop)

    # Ordenar por distancia
    nearby.sort(key=lambda x: x.distance)

    serializer = NearbyWorkshopsSerializer(nearby[:20], many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def workshop_detail(request, pk):
    """Detalle de un taller"""
    try:
        workshop = Workshop.objects.get(pk=pk, is_active=True, is_verified=True)
    except Workshop.DoesNotExist:
        return Response({'error': 'Taller no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    serializer = WorkshopDetailSerializer(workshop)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rate_workshop(request, pk):
    """Calificar un servicio concreto (assignment completado). Recalcula rating_avg del taller."""
    try:
        workshop = Workshop.objects.get(pk=pk)
    except Workshop.DoesNotExist:
        return Response({'error': 'Taller no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    if not hasattr(request.user, 'client_profile'):
        return Response({'error': 'Solo los clientes pueden calificar'}, status=status.HTTP_403_FORBIDDEN)

    ser = RateWorkshopSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    assignment_id = ser.validated_data['assignment_id']
    try:
        assignment = Assignment.objects.select_related('incident', 'workshop').get(id=assignment_id)
    except Assignment.DoesNotExist:
        return Response({'error': 'Asignación no encontrada'}, status=status.HTTP_404_NOT_FOUND)

    if assignment.workshop_id != int(pk):
        return Response({'error': 'La asignación no pertenece a este taller'}, status=status.HTTP_400_BAD_REQUEST)
    if assignment.incident.client_id != request.user.client_profile.id:
        return Response({'error': 'No puedes calificar este servicio'}, status=status.HTTP_403_FORBIDDEN)
    if assignment.status != AssignmentStatus.COMPLETED:
        return Response({'error': 'El servicio aún no está completado'}, status=status.HTTP_400_BAD_REQUEST)
    if WorkshopRating.objects.filter(assignment=assignment).exists():
        return Response({'error': 'Ya enviaste una calificación para este servicio'}, status=status.HTTP_400_BAD_REQUEST)

    rating = WorkshopRating.objects.create(
        workshop=workshop,
        client=request.user.client_profile,
        assignment=assignment,
        score=ser.validated_data['score'],
        comment=ser.validated_data.get('comment') or '',
    )

    agg = workshop.ratings.aggregate(avg=Avg('score'))['avg']
    if agg is not None:
        workshop.rating_avg = round(float(agg), 2)
        workshop.total_services = workshop.ratings.count()
        workshop.save(update_fields=['rating_avg', 'total_services'])

    owner_user = workshop.owner.user
    client_name = request.user.get_full_name() or request.user.username
    score_val = ser.validated_data['score']
    avg_str = f'{workshop.rating_avg:.2f}'.rstrip('0').rstrip('.')
    title = 'Nueva calificación'
    body = (
        f'{client_name} te calificó con {score_val}★. '
        f'Promedio del taller: {avg_str}★'
    )

    try:
        Notification.objects.create(
            user=owner_user,
            title=title,
            body=body,
            notification_type=NotificationType.NEW_RATING,
            incident=assignment.incident,
            data={
                'type': 'new_rating',
                'rating_id': rating.id,
                'score': score_val,
                'rating_avg': float(workshop.rating_avg),
                'assignment_id': assignment.id,
                'incident_id': assignment.incident_id,
                'workshop_id': workshop.id,
            },
            push_sent=bool(owner_user.fcm_token),
        )

        if owner_user.fcm_token:
            from apps.notifications.firebase_service import FirebaseService

            firebase = FirebaseService()
            firebase.send_notification(
                token=owner_user.fcm_token,
                title=title,
                body=body,
                data={
                    'type': 'new_rating',
                    'workshop_id': str(workshop.id),
                    'incident_id': str(assignment.incident_id),
                    'score': str(score_val),
                    'rating_avg': str(workshop.rating_avg),
                },
            )

        notify_user(owner_user.id, {
            'event': 'new_rating',
            'workshop_id': workshop.id,
            'rating_id': rating.id,
            'score': score_val,
            'rating_avg': float(workshop.rating_avg),
            'incident_id': assignment.incident_id,
        })

        from apps.notifications.web_panel_notify import send_web_push_only
        send_web_push_only(
            user=owner_user,
            title=title,
            body=body,
            data={
                'type': 'new_rating',
                'workshop_id': workshop.id,
                'incident_id': assignment.incident_id,
            },
        )
    except Exception as e:
        logging.getLogger(__name__).exception('notify workshop rating: %s', e)

    out = WorkshopRatingSerializer(rating)
    return Response(out.data, status=status.HTTP_201_CREATED)
