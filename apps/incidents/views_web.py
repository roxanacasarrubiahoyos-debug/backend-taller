from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from apps.incidents.models import Incident, IncidentStatus, IncidentStatusHistory
from apps.incidents.serializers import IncidentSerializer, IncidentDetailSerializer, IncidentStatusUpdateSerializer, IncidentCompleteSerializer
from apps.assignments.models import Assignment, AssignmentStatus
from apps.users.permissions import IsWorkshopOwner
from apps.workshops.models import Workshop
from django.utils import timezone
from apps.notifications.sse_views import notify_incident_update


@api_view(['GET'])
@permission_classes([IsWorkshopOwner])
def available_incidents(request):
    """Solicitudes de emergencia disponibles para el taller"""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    # Buscar assignments ofrecidas a este taller
    assignments = Assignment.objects.filter(
        workshop=workshop,
        status=AssignmentStatus.OFFERED
    ).select_related('incident', 'incident__client', 'incident__vehicle').order_by('-offered_at')

    incidents_data = []
    for assignment in assignments:
        incident = assignment.incident
        incidents_data.append({
            'assignment_id': assignment.id,
            'incident_id': incident.id,
            'client_name': incident.client.user.get_full_name(),
            'vehicle': f"{incident.vehicle.brand} {incident.vehicle.model}" if incident.vehicle else None,
            'incident_type': incident.get_incident_type_display(),
            'priority': incident.get_priority_display() if incident.priority else None,
            'description': incident.description,
            'address': incident.address_text,
            'distance_km': assignment.distance_km,
            'ai_summary': incident.ai_summary,
            'ai_confidence': incident.ai_confidence,
            'created_at': incident.created_at,
            'offered_at': assignment.offered_at,
        })

    return Response(incidents_data)


@api_view(['GET'])
@permission_classes([IsWorkshopOwner])
def incident_detail(request, pk):
    """Detalle del incidente con resumen IA"""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    # Verificar que el taller tiene acceso a este incidente
    assignment = Assignment.objects.filter(
        workshop=workshop,
        incident_id=pk
    ).first()

    if not assignment:
        return Response({'error': 'No tienes acceso a este incidente'}, status=status.HTTP_403_FORBIDDEN)

    try:
        incident = Incident.objects.get(id=pk)
    except Incident.DoesNotExist:
        return Response({'error': 'Incidente no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    serializer = IncidentDetailSerializer(incident)
    data = serializer.data
    available_technicians = list(
        workshop.technicians.filter(is_available=True).values(
            'id', 'name', 'phone', 'specialties', 'is_available'
        )
    )
    data['assignment'] = {
        'id': assignment.id,
        'status': assignment.status,
        'distance_km': assignment.distance_km,
        'technician': assignment.technician.name if assignment.technician else None,
    }
    data['available_technicians'] = available_technicians
    return Response(data)


@api_view(['POST'])
@permission_classes([IsWorkshopOwner])
def accept_incident(request, pk):
    """Aceptar incidente y asignar técnico"""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    # Buscar assignment ofrecida
    assignment = Assignment.objects.filter(
        workshop=workshop,
        incident_id=pk,
        status=AssignmentStatus.OFFERED
    ).first()

    if not assignment:
        return Response({'error': 'No se encontró la asignación o ya fue procesada'}, status=status.HTTP_404_NOT_FOUND)

    technician_id = request.data.get('technician_id')
    estimated_arrival_minutes = request.data.get('estimated_arrival_minutes')
    if not technician_id:
        return Response({'error': 'Debes seleccionar un técnico'}, status=status.HTTP_400_BAD_REQUEST)
    if estimated_arrival_minutes is None:
        return Response({'error': 'Debes enviar estimated_arrival_minutes'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        estimated_arrival_minutes = int(estimated_arrival_minutes)
        if estimated_arrival_minutes <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        return Response({'error': 'ETA inválido'}, status=status.HTTP_400_BAD_REQUEST)

    # Verificar que el técnico pertenece al taller
    technician = workshop.technicians.filter(id=technician_id, is_available=True).first()
    if not technician:
        return Response({'error': 'Técnico no encontrado o no disponible'}, status=status.HTTP_400_BAD_REQUEST)

    # Aceptar assignment
    assignment.technician = technician
    assignment.status = AssignmentStatus.ACCEPTED
    assignment.estimated_arrival_minutes = estimated_arrival_minutes
    assignment.accepted_at = timezone.now()
    assignment.save()

    # Actualizar incidente
    incident = assignment.incident
    previous_status = incident.status
    incident.status = IncidentStatus.ASSIGNED
    incident.save()

    # Crear historial
    IncidentStatusHistory.objects.create(
        incident=incident,
        previous_status=previous_status,
        new_status=IncidentStatus.ASSIGNED,
        changed_by=request.user,
        notes=f'Taller {workshop.name} aceptó el incidente. Técnico: {technician.name}. ETA: {estimated_arrival_minutes} min'
    )

    # Rechazar otros assignments ofrecidos
    Assignment.objects.filter(
        incident=incident,
        status=AssignmentStatus.OFFERED
    ).exclude(id=assignment.id).update(
        status=AssignmentStatus.REJECTED,
        rejection_reason='Otro taller aceptó primero'
    )

    # Notificar al cliente
    try:
        from apps.notifications.models import Notification, NotificationType
        from apps.notifications.firebase_service import FirebaseService

        client_user = incident.client.user
        Notification.objects.create(
            user=client_user,
            title='Taller asignado',
                body=f'¡{workshop.name} aceptó tu solicitud! {technician.name} llegará en ~{estimated_arrival_minutes} min.',
            notification_type=NotificationType.WORKSHOP_ASSIGNED,
            incident=incident,
                data={
                    'assignment_id': assignment.id,
                    'workshop_name': workshop.name,
                    'technician_name': technician.name,
                    'eta': estimated_arrival_minutes,
                }
        )

        if client_user.fcm_token:
            firebase = FirebaseService()
            firebase.send_notification(
                token=client_user.fcm_token,
                title='Taller asignado',
                body=f'{workshop.name} atenderá tu emergencia',
                data={
                    'incident_id': str(incident.id),
                    'type': 'workshop_assigned',
                    'eta': str(estimated_arrival_minutes),
                    'technician_name': technician.name,
                }
            )
    except Exception as e:
        print(f"Error sending notification: {e}")

    # Push al técnico (app móvil) — Fase 6 del flujo operativo
    try:
        tech_user = getattr(technician, 'user', None)
        if tech_user:
            from apps.notifications.models import Notification as AppNotification, NotificationType as NT
            from apps.notifications.firebase_service import FirebaseService

            addr = (incident.address_text or 'Ver ubicación en mapa').strip()
            if len(addr) > 140:
                addr = addr[:137] + '…'

            vehicle_line = ''
            v = incident.vehicle
            if v:
                parts = [p for p in (v.brand, v.model, v.color) if p]
                vehicle_line = ' '.join(parts)
                if v.plate:
                    vehicle_line = f'{vehicle_line} · {v.plate}'.strip(' ·') if vehicle_line else v.plate

            problem = incident.get_incident_type_display()
            body_tech = (
                f'{problem} en {addr}. '
                f'Cliente: {vehicle_line or "vehículo"}. ETA ~{estimated_arrival_minutes} min.'
            )

            AppNotification.objects.create(
                user=tech_user,
                title='Nueva orden asignada',
                body=body_tech,
                notification_type=NT.TECHNICIAN_ASSIGNED,
                incident=incident,
                data={
                    'incident_id': incident.id,
                    'assignment_id': assignment.id,
                    'workshop_name': workshop.name,
                    'eta': estimated_arrival_minutes,
                },
                push_sent=bool(tech_user.fcm_token),
            )
            if tech_user.fcm_token:
                FirebaseService().send_notification(
                    token=tech_user.fcm_token,
                    title='Nueva orden asignada',
                    body=body_tech,
                    data={
                        'type': 'technician_assignment',
                        'incident_id': str(incident.id),
                        'assignment_id': str(assignment.id),
                        'eta': str(estimated_arrival_minutes),
                    },
                )
    except Exception as e:
        print(f'Error notifying technician: {e}')

    notify_incident_update(incident.id, {
        'event': 'assigned',
        'incident_id': incident.id,
        'workshop': {
            'id': workshop.id,
            'name': workshop.name,
            'logo': str(workshop.logo.url) if getattr(workshop, 'logo', None) else '',
            'phone': workshop.phone,
        },
        'technician': {
            'id': technician.id,
            'name': technician.name,
        },
        'eta': estimated_arrival_minutes,
    })

    return Response({
        'message': 'Incidente aceptado exitosamente',
        'assignment_id': assignment.id,
        'incident_id': incident.id
    })


@api_view(['POST'])
@permission_classes([IsWorkshopOwner])
def reject_incident(request, pk):
    """Rechazar incidente con motivo"""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    assignment = Assignment.objects.filter(
        workshop=workshop,
        incident_id=pk,
        status=AssignmentStatus.OFFERED
    ).first()

    if not assignment:
        return Response({'error': 'No se encontró la asignación'}, status=status.HTTP_404_NOT_FOUND)

    reason = request.data.get('reason', 'No especificado')
    assignment.status = AssignmentStatus.REJECTED
    assignment.rejection_reason = reason
    assignment.save()

    return Response({'message': 'Incidente rechazado'})


@api_view(['PATCH'])
@permission_classes([IsWorkshopOwner])
def update_incident_status(request, pk):
    """Actualizar estado del servicio (en ruta, llegó, en servicio)"""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    assignment = Assignment.objects.filter(
        workshop=workshop,
        incident_id=pk,
        status__in=[AssignmentStatus.ACCEPTED, AssignmentStatus.IN_ROUTE,
                   AssignmentStatus.ARRIVED, AssignmentStatus.IN_SERVICE]
    ).first()

    if not assignment:
        return Response({'error': 'No tienes una asignación activa para este incidente'}, status=status.HTTP_404_NOT_FOUND)

    new_status = request.data.get('status')
    notes = request.data.get('notes', '')
    valid_statuses = ['in_route', 'arrived', 'in_service']

    if new_status not in valid_statuses:
        return Response({'error': 'Estado inválido'}, status=status.HTTP_400_BAD_REQUEST)

    # Actualizar assignment
    assignment.status = new_status
    if new_status == AssignmentStatus.ARRIVED and assignment.arrived_at is None:
        assignment.arrived_at = timezone.now()
    assignment.save()

    # Actualizar incidente y traza
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
        notes=notes or f'Assignment actualizado a {new_status}'
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
        print(f"Error notifying status update: {e}")

    return Response({'message': 'Estado actualizado', 'new_status': new_status})


@api_view(['POST'])
@permission_classes([IsWorkshopOwner])
def complete_incident(request, pk):
    """Cerrar servicio e ingresar costo"""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    assignment = Assignment.objects.filter(
        workshop=workshop,
        incident_id=pk,
        status__in=[AssignmentStatus.IN_SERVICE, AssignmentStatus.ARRIVED]
    ).first()

    if not assignment:
        return Response({'error': 'No tienes una asignación activa para este incidente'}, status=status.HTTP_404_NOT_FOUND)

    serializer = IncidentCompleteSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    service_cost = serializer.validated_data['service_cost']
    notes = serializer.validated_data.get('notes', '')

    # Actualizar assignment
    assignment.status = AssignmentStatus.COMPLETED
    assignment.service_cost = service_cost
    assignment.completed_at = timezone.now()
    assignment.save()

    # Actualizar incidente
    incident = assignment.incident
    previous_status = incident.status
    incident.status = IncidentStatus.COMPLETED
    incident.closed_at = timezone.now()
    incident.save()

    # Crear historial
    IncidentStatusHistory.objects.create(
        incident=incident,
        previous_status=previous_status,
        new_status=IncidentStatus.COMPLETED,
        changed_by=request.user,
        notes=f'Servicio completado. Costo: ${service_cost}. {notes}'
    )

    # Actualizar estadísticas del taller
    workshop.total_services += 1
    workshop.save()

    # Crear pago
    commission_rate = None
    try:
        from apps.payments.models import Payment, CommissionConfig, PaymentStatus
        from decimal import Decimal

        commission_config = CommissionConfig.get_applicable_for_date()
        commission_rate = commission_config.percentage if commission_config else Decimal('10.00')

        commission_amount = (service_cost * commission_rate) / Decimal('100')
        workshop_net = service_cost - commission_amount

        Payment.objects.create(
            assignment=assignment,
            commission_config=commission_config,
            total_amount=service_cost,
            commission_rate=commission_rate,
            commission_amount=commission_amount,
            workshop_net_amount=workshop_net,
            status=PaymentStatus.PENDING
        )
    except Exception as e:
        print(f"Error creating payment: {e}")

    # Notificar al cliente
    try:
        from apps.notifications.models import Notification, NotificationType
        from apps.notifications.firebase_service import FirebaseService

        client_user = incident.client.user
        Notification.objects.create(
            user=client_user,
            title='Servicio completado',
            body=f'Tu emergencia ha sido resuelta. Total: ${service_cost}',
            notification_type=NotificationType.SERVICE_COMPLETED,
            incident=incident,
            data={'service_cost': str(service_cost)}
        )

        if client_user.fcm_token:
            firebase = FirebaseService()
            firebase.send_notification(
                token=client_user.fcm_token,
                title='Servicio completado',
                body=f'Emergencia resuelta. Total: ${service_cost}',
                data={'incident_id': str(incident.id), 'type': 'service_completed', 'cost': str(service_cost)}
            )
    except Exception as e:
        print(f"Error sending notification: {e}")

    notify_incident_update(incident.id, {
        'event': 'service_completed',
        'incident_id': incident.id,
        'cost': float(service_cost),
    })

    try:
        from apps.incidents.models import IncidentCycleMetric

        def _sec_delta(start, end):
            if start and end:
                return int((end - start).total_seconds())
            return None

        IncidentCycleMetric.objects.update_or_create(
            assignment=assignment,
            defaults={
                'seconds_to_assignment': _sec_delta(incident.created_at, assignment.accepted_at),
                'seconds_to_arrival': _sec_delta(assignment.accepted_at, assignment.arrived_at),
                'seconds_total_resolution': _sec_delta(incident.created_at, assignment.completed_at),
                'service_cost': service_cost,
                'ai_confidence': incident.ai_confidence,
                'ai_predicted_type': incident.incident_type or '',
            },
        )
    except Exception as e:
        print(f"Error saving cycle metric: {e}")

    return Response({
        'message': 'Servicio completado exitosamente',
        'service_cost': service_cost,
        'commission_rate': commission_rate if commission_rate is not None else '10.00',
    })


@api_view(['GET'])
@permission_classes([IsWorkshopOwner])
def incident_history(request):
    """Historial de servicios del taller"""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    assignments = Assignment.objects.filter(
        workshop=workshop
    ).exclude(
        status=AssignmentStatus.OFFERED
    ).select_related('incident', 'technician').order_by('-offered_at')

    history_data = []
    for assignment in assignments:
        incident = assignment.incident
        rating_score = None
        rating_comment = None
        try:
            cr = assignment.client_rating
            if cr:
                rating_score = cr.score
                rating_comment = cr.comment
        except Exception:
            pass
        history_data.append({
            'assignment_id': assignment.id,
            'incident_id': incident.id,
            'assignment_status': assignment.status,
            'status': assignment.get_status_display(),
            'incident_type': incident.get_incident_type_display(),
            'client_name': incident.client.user.get_full_name(),
            'technician': assignment.technician.name if assignment.technician else None,
            'service_cost': assignment.service_cost,
            'distance_km': assignment.distance_km,
            'offered_at': assignment.offered_at,
            'accepted_at': assignment.accepted_at,
            'completed_at': assignment.completed_at,
            'rating_score': rating_score,
            'rating_comment': rating_comment,
        })

    return Response(history_data)


@api_view(['POST'])
@permission_classes([IsWorkshopOwner])
def create_service_quote(request, pk):
    """Enviar cotización de daño / tiempo de reparación al cliente (app móvil)."""
    from apps.assignments.models import ServiceQuote, ServiceQuoteStatus
    from apps.assignments.serializers import ServiceQuoteCreateSerializer, ServiceQuoteSerializer

    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    assignment = Assignment.objects.filter(workshop=workshop, incident_id=pk).exclude(
        status=AssignmentStatus.REJECTED
    ).first()
    if not assignment:
        return Response({'error': 'No tienes asignación para este incidente'}, status=status.HTTP_403_FORBIDDEN)

    ser = ServiceQuoteCreateSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    ServiceQuote.objects.filter(
        assignment=assignment,
        status=ServiceQuoteStatus.SENT,
    ).update(status=ServiceQuoteStatus.SUPERSEDED)

    quote = ServiceQuote.objects.create(
        assignment=assignment,
        amount=ser.validated_data['amount'],
        estimated_repair_minutes=ser.validated_data['estimated_repair_minutes'],
        damage_description=ser.validated_data.get('damage_description', ''),
        status=ServiceQuoteStatus.SENT,
        created_by=request.user,
    )

    try:
        client_user = assignment.incident.client.user
        from apps.notifications.models import Notification, NotificationType
        Notification.objects.create(
            user=client_user,
            title='Nueva cotización de taller',
            body=f'{workshop.name}: Bs. {quote.amount} — reparación ~{quote.estimated_repair_minutes} min.',
            notification_type=NotificationType.STATUS_UPDATED,
            incident=assignment.incident,
            data={
                'incident_id': assignment.incident_id,
                'quote_id': quote.id,
                'amount': str(quote.amount),
            },
        )
    except Exception:
        pass

    return Response(ServiceQuoteSerializer(quote).data, status=status.HTTP_201_CREATED)
