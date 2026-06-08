from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from apps.users.permissions import IsClient
from apps.assignments.models import Assignment
from apps.assignments.serializers import AssignmentDetailSerializer


@api_view(['GET'])
@permission_classes([IsClient])
def assignment_detail(request, pk):
    """Detalle de una asignación (para el cliente)"""
    try:
        assignment = Assignment.objects.select_related(
            'workshop', 'technician', 'incident', 'client_rating', 'payment'
        ).get(id=pk)
    except Assignment.DoesNotExist:
        return Response({'error': 'Asignación no encontrada'}, status=status.HTTP_404_NOT_FOUND)

    # Verificar que el cliente es dueño del incidente
    if assignment.incident.client != request.user.client_profile:
        return Response({'error': 'No tienes acceso a esta asignación'}, status=status.HTTP_403_FORBIDDEN)

    serializer = AssignmentDetailSerializer(assignment)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsClient])
def active_assignment(request, incident_id):
    """Obtener asignación activa de un incidente"""
    assignment = Assignment.objects.filter(
        incident_id=incident_id,
        status__in=['accepted', 'in_route', 'arrived', 'in_service']
    ).select_related('workshop', 'technician').first()

    if not assignment:
        return Response({'error': 'No hay asignación activa'}, status=status.HTTP_404_NOT_FOUND)

    # Verificar acceso
    if assignment.incident.client != request.user.client_profile:
        return Response({'error': 'No tienes acceso a esta asignación'}, status=status.HTTP_403_FORBIDDEN)

    serializer = AssignmentDetailSerializer(assignment)
    return Response(serializer.data)
