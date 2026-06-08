"""
API app móvil — técnico de taller (órdenes asignadas, estados en campo).
La lógica de negocio alinea Fase 6–7 del flujo operativo (en ruta, llegó, en servicio).
El cierre con costo lo gestiona el dueño desde el portal web.
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone

from apps.assignments.models import Assignment, AssignmentStatus
from apps.assignments.serializers import (
    TechnicianAssignmentListSerializer,
    TechnicianAssignmentDetailSerializer,
)
from apps.incidents.models import IncidentStatus, IncidentStatusHistory
from apps.users.permissions import IsTechnician
from apps.notifications.sse_views import notify_incident_update


def _get_technician_assignment(technician, pk):
    return (
        Assignment.objects.filter(pk=pk, technician=technician)
        .select_related(
            'incident',
            'incident__client__user',
            'incident__vehicle',
            'workshop',
            'technician',
        )
        .first()
    )


@api_view(['GET'])
@permission_classes([IsTechnician])
def list_assignments(request):
    """Servicios asignados al técnico (activos e histórico)."""
    tech = request.user.technician_profile
    qs = (
        Assignment.objects.filter(technician=tech)
        .exclude(status__in=[AssignmentStatus.OFFERED, AssignmentStatus.REJECTED])
        .select_related(
            'incident',
            'incident__vehicle',
            'incident__client__user',
            'workshop',
            'technician',
        )
        .order_by('-offered_at')
    )
    status_filter = request.query_params.get('status')
    if status_filter == 'active':
        qs = qs.filter(
            status__in=[
                AssignmentStatus.ACCEPTED,
                AssignmentStatus.IN_ROUTE,
                AssignmentStatus.ARRIVED,
                AssignmentStatus.IN_SERVICE,
            ]
        )
    elif status_filter == 'completed':
        qs = qs.filter(status=AssignmentStatus.COMPLETED)

    page = TechnicianAssignmentListSerializer(qs, many=True)
    return Response(page.data)


@api_view(['GET'])
@permission_classes([IsTechnician])
def assignment_detail(request, pk):
    tech = request.user.technician_profile
    assignment = _get_technician_assignment(tech, pk)
    if not assignment:
        return Response({'error': 'Asignación no encontrada'}, status=status.HTTP_404_NOT_FOUND)
    return Response(TechnicianAssignmentDetailSerializer(assignment).data)


@api_view(['PATCH'])
@permission_classes([IsTechnician])
def update_assignment_status(request, pk):
    """
    Actualizar estado operativo: in_route | arrived | in_service
    (misma semántica que PATCH /api/web/incidents/<id>/status/ del dueño).
    """
    tech = request.user.technician_profile
    assignment = _get_technician_assignment(tech, pk)
    if not assignment:
        return Response({'error': 'Asignación no encontrada'}, status=status.HTTP_404_NOT_FOUND)

    new_status = request.data.get('status')
    notes = request.data.get('notes', '')
    valid = ['in_route', 'arrived', 'in_service']
    if new_status not in valid:
        return Response({'error': 'Estado inválido'}, status=status.HTTP_400_BAD_REQUEST)

    if assignment.status not in [
        AssignmentStatus.ACCEPTED,
        AssignmentStatus.IN_ROUTE,
        AssignmentStatus.ARRIVED,
        AssignmentStatus.IN_SERVICE,
    ]:
        return Response(
            {'error': 'No puedes cambiar el estado de esta asignación'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    assignment.status = new_status
    if new_status == AssignmentStatus.ARRIVED and assignment.arrived_at is None:
        assignment.arrived_at = timezone.now()
    assignment.save()

    incident = assignment.incident
    previous_status = incident.status
    if new_status in ['in_route', 'arrived', 'in_service']:
        incident.status = IncidentStatus.IN_PROGRESS
        incident.save()

    IncidentStatusHistory.objects.create(
        incident=incident,
        previous_status=previous_status,
        new_status=incident.status,
        changed_by=request.user,
        notes=notes or f'Técnico: asignación → {new_status}',
    )

    event_payload = {'incident_id': incident.id, 'assignment_status': new_status}
    if new_status == 'in_route':
        event_payload['event'] = 'in_route'
    elif new_status == 'arrived':
        event_payload['event'] = 'arrived'
    elif new_status == 'in_service':
        event_payload['event'] = 'in_service'
    notify_incident_update(incident.id, event_payload)

    try:
        from apps.notifications.models import Notification, NotificationType
        from apps.notifications.firebase_service import FirebaseService

        client_user = incident.client.user
        tech_name = assignment.technician.name if assignment.technician else 'El técnico'
        eta = assignment.estimated_arrival_minutes

        if new_status == 'in_route':
            title = f'{tech_name} va en camino'
            body = (
                f'{tech_name} salió hacia tu ubicación.'
                + (f' Tiempo estimado ~{eta} min.' if eta else '')
            )
            push_type = 'technician_in_route'
        elif new_status == 'arrived':
            title = f'{tech_name} llegó'
            body = f'{tech_name} está en el lugar del incidente.'
            push_type = 'status_updated'
        else:
            title = 'Servicio en curso'
            body = f'{tech_name} está atendiendo el servicio.'
            push_type = 'status_updated'

        Notification.objects.create(
            user=client_user,
            title=title,
            body=body,
            notification_type=NotificationType.STATUS_UPDATED,
            incident=incident,
            data={
                'incident_id': incident.id,
                'assignment_status': new_status,
                'technician_name': tech_name,
            },
            push_sent=bool(client_user.fcm_token),
        )
        if client_user.fcm_token:
            firebase = FirebaseService()
            firebase.send_notification(
                token=client_user.fcm_token,
                title=title,
                body=body,
                data={
                    'incident_id': str(incident.id),
                    'type': push_type,
                    'status': new_status,
                    'technician_name': tech_name,
                    **({'eta': str(eta)} if eta is not None else {}),
                },
            )
    except Exception as e:
        print(f'Error notifying status update: {e}')

    return Response({'message': 'Estado actualizado', 'new_status': new_status})
