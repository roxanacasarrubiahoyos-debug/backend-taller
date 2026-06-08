"""
Entrega de notificaciones del panel web (admin / workshop_owner) en segundo plano vía django-q.
"""
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _panel_path_for_user(user) -> str:
    if getattr(user, 'role', None) == 'admin':
        return '/admin/notificaciones'
    return '/taller/notificaciones'


def deliver_web_panel_user_task(
    user_id: int,
    title: str,
    body: str,
    notification_type: str,
    incident_id: int | None = None,
    data: dict | None = None,
    sse_payload: dict | None = None,
) -> dict:
    """Tarea django-q: persiste en BD, SSE y Web Push."""
    from apps.users.models import User
    from apps.incidents.models import Incident
    from apps.notifications.web_panel_notify import deliver_to_web_panel_user_sync

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return {'ok': False, 'error': 'user_not_found'}

    incident = None
    if incident_id:
        incident = Incident.objects.filter(pk=incident_id).first()

    payload = dict(data or {})
    payload.setdefault('panel_path', _panel_path_for_user(user))

    deliver_to_web_panel_user_sync(
        user=user,
        title=title,
        body=body,
        notification_type=notification_type,
        incident=incident,
        data=payload,
        sse_payload=sse_payload,
    )
    return {'ok': True, 'user_id': user_id}


def deliver_web_push_only_task(
    user_id: int,
    title: str,
    body: str,
    data: dict | None = None,
) -> dict:
    from apps.users.models import User
    from apps.notifications.web_panel_notify import send_web_push_only_sync

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return {'ok': False, 'error': 'user_not_found'}

    payload = dict(data or {})
    payload.setdefault('panel_path', _panel_path_for_user(user))
    sent = send_web_push_only_sync(user=user, title=title, body=body, data=payload)
    return {'ok': True, 'push_sent': sent}


def notify_web_panel_admins_task(
    title: str,
    body: str,
    notification_type: str,
    incident_id: int | None = None,
    data: dict | None = None,
    sse_payload: dict | None = None,
) -> dict:
    from apps.users.models import Role, User

    ids = list(User.objects.filter(role=Role.ADMIN, is_active=True).values_list('id', flat=True))
    for uid in ids:
        deliver_web_panel_user_task(
            uid,
            title,
            body,
            notification_type,
            incident_id,
            data,
            sse_payload,
        )
    return {'ok': True, 'admins': len(ids)}


def enqueue_deliver_to_web_panel_user(
    *,
    user,
    title: str,
    body: str,
    notification_type: str,
    incident=None,
    data: dict | None = None,
    sse_payload: dict | None = None,
) -> None:
    from apps.notifications.web_panel_notify import WEB_PANEL_ROLES

    if user.role not in WEB_PANEL_ROLES:
        return

    incident_id = incident.id if incident is not None else None
    task_kwargs = dict(
        user_id=user.id,
        title=title,
        body=body,
        notification_type=notification_type,
        incident_id=incident_id,
        data=data,
        sse_payload=sse_payload,
    )

    if _use_async_worker():
        from django_q.tasks import async_task

        async_task(
            'apps.notifications.web_panel_tasks.deliver_web_panel_user_task',
            **task_kwargs,
        )
    else:
        deliver_web_panel_user_task(**task_kwargs)


def enqueue_notify_web_panel_admins(
    *,
    title: str,
    body: str,
    notification_type: str,
    incident=None,
    data: dict | None = None,
    sse_payload: dict | None = None,
) -> None:
    incident_id = incident.id if incident is not None else None
    if _use_async_worker():
        from django_q.tasks import async_task

        async_task(
            'apps.notifications.web_panel_tasks.notify_web_panel_admins_task',
            title=title,
            body=body,
            notification_type=notification_type,
            incident_id=incident_id,
            data=data,
            sse_payload=sse_payload,
        )
    else:
        notify_web_panel_admins_task(
            title=title,
            body=body,
            notification_type=notification_type,
            incident_id=incident_id,
            data=data,
            sse_payload=sse_payload,
        )


def enqueue_web_push_only(*, user, title: str, body: str, data: dict | None = None) -> None:
    from apps.notifications.web_panel_notify import WEB_PANEL_ROLES

    if user.role not in WEB_PANEL_ROLES:
        return

    if _use_async_worker():
        from django_q.tasks import async_task

        async_task(
            'apps.notifications.web_panel_tasks.deliver_web_push_only_task',
            user_id=user.id,
            title=title,
            body=body,
            data=data,
        )
    else:
        deliver_web_push_only_task(
            user_id=user.id,
            title=title,
            body=body,
            data=data,
        )


def _use_async_worker() -> bool:
    return getattr(settings, 'WEB_PANEL_NOTIFY_ASYNC', True)
