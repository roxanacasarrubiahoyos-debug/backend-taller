"""
Alcance de notificaciones del panel web por rol y taller.

- Admin: solo alertas de administración (no ofertas/calificaciones de talleres ajenos).
- Dueño de taller: solo notificaciones vinculadas a sus talleres (workshop_id / assignment / incidente).
"""
from __future__ import annotations

from typing import Iterable

from django.db.models import Q, QuerySet

from apps.assignments.models import Assignment
from apps.notifications.models import Notification, NotificationType
from apps.workshops.models import Workshop

# Solo panel administración
ADMIN_ONLY_NOTIFICATION_TYPES = frozenset({
    NotificationType.WORKSHOP_PENDING_REVIEW,
    NotificationType.INCIDENT_CREATED,
})

# Solo dueños de taller (no deben aparecer en cuentas admin)
WORKSHOP_OWNER_ONLY_NOTIFICATION_TYPES = frozenset({
    NotificationType.NEW_REQUEST,
    NotificationType.NEW_RATING,
    NotificationType.WORKSHOP_VERIFIED,
})


def workshop_ids_for_owner(owner_profile) -> list[int]:
    if owner_profile is None:
        return []
    return list(
        Workshop.objects.filter(owner=owner_profile).values_list('id', flat=True)
    )


def workshop_owner_scope_q(workshop_ids: Iterable[int]) -> Q:
    """Notificaciones que pertenecen a uno de los talleres del dueño."""
    ws = list(workshop_ids)
    if not ws:
        return Q(pk__in=[])

    incident_ids = Assignment.objects.filter(
        workshop_id__in=ws,
    ).values_list('incident_id', flat=True).distinct()

    scoped = Q(data__workshop_id__in=ws) | (
        Q(incident_id__in=incident_ids) & ~Q(data__has_key='workshop_id')
    )

    # assignment_id en JSON (jsonb) no admite IN contra bigint sin cast; usamos contains.
    for aid in Assignment.objects.filter(workshop_id__in=ws).values_list('id', flat=True):
        scoped |= Q(data__contains={'assignment_id': aid})

    return scoped & ~Q(notification_type__in=ADMIN_ONLY_NOTIFICATION_TYPES)


def notifications_queryset_for_user(user) -> QuerySet[Notification]:
    """QuerySet base de notificaciones visibles para el usuario del panel."""
    qs = Notification.objects.filter(user=user)

    if user.role == 'admin':
        return qs.exclude(notification_type__in=WORKSHOP_OWNER_ONLY_NOTIFICATION_TYPES)

    if user.role == 'workshop_owner':
        owner = getattr(user, 'owner_profile', None)
        ws_ids = workshop_ids_for_owner(owner)
        return qs.filter(workshop_owner_scope_q(ws_ids))

    return qs.none()


def enrich_panel_notification_data(
    *,
    user,
    data: dict | None,
    incident=None,
    workshop=None,
) -> dict:
    """Asegura workshop_id en payload para filtrar y deep-links del panel taller."""
    payload = dict(data or {})

    if workshop is not None:
        payload['workshop_id'] = workshop.id
    elif payload.get('workshop_id'):
        payload['workshop_id'] = int(payload['workshop_id'])
    elif payload.get('assignment_id'):
        row = (
            Assignment.objects.filter(pk=int(payload['assignment_id']))
            .select_related('workshop')
            .first()
        )
        if row:
            payload['workshop_id'] = row.workshop_id
            workshop = row.workshop
    elif incident is not None and user.role == 'workshop_owner':
        owner = getattr(user, 'owner_profile', None)
        if owner:
            row = Assignment.objects.filter(
                incident=incident,
                workshop__owner=owner,
            ).order_by('-id').first()
            if row:
                payload['workshop_id'] = row.workshop_id
                payload.setdefault('assignment_id', row.id)

    if user.role == 'workshop_owner' and payload.get('workshop_id'):
        payload.setdefault('panel_path', '/taller/notificaciones')
    elif user.role == 'admin':
        payload.setdefault('panel_path', '/admin/notificaciones')

    return payload
