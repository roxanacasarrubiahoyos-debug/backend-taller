"""
Entrega de notificaciones al panel web (taller + admin).
BD + SSE + Web Push (VAPID). Encolado en segundo plano con django-q cuando está activo.
"""
import logging

from apps.notifications.models import Notification
from apps.notifications.sse_views import notify_user
from apps.notifications.web_push_service import send_web_push_to_user
from apps.notifications.workshop_scope import enrich_panel_notification_data
from apps.users.models import Role, User

logger = logging.getLogger(__name__)

WEB_PANEL_ROLES = ('workshop_owner', 'admin')


def deliver_to_web_panel_user_sync(
    *,
    user,
    title: str,
    body: str,
    notification_type: str,
    incident=None,
    data: dict | None = None,
    sse_payload: dict | None = None,
) -> None:
    """Entrega inmediata (usada por la tarea en background o fallback síncrono)."""
    if user.role not in WEB_PANEL_ROLES:
        return

    payload = enrich_panel_notification_data(
        user=user,
        data=data,
        incident=incident,
    )

    Notification.objects.create(
        user=user,
        title=title,
        body=body,
        notification_type=notification_type,
        incident=incident,
        data=payload,
        push_sent=False,
    )
    stream_data = {
        'event': notification_type,
        'type': payload.get('type', notification_type),
        'title': title,
        'body': body,
        **payload,
    }
    if sse_payload:
        stream_data.update(sse_payload)
        stream_data.setdefault('title', title)
        stream_data.setdefault('body', body)
    notify_user(user.id, stream_data)
    sent = send_web_push_to_user(user, title, body, payload)
    if sent:
        last = Notification.objects.filter(user=user).order_by('-created_at').first()
        if last:
            last.push_sent = True
            last.save(update_fields=['push_sent'])


def send_web_push_only_sync(*, user, title: str, body: str, data: dict | None = None) -> int:
    if user.role not in WEB_PANEL_ROLES:
        return 0
    payload = dict(data or {})
    payload.setdefault(
        'panel_path',
        '/admin/notificaciones' if user.role == 'admin' else '/taller/notificaciones',
    )
    return send_web_push_to_user(user, title, body, payload)


def deliver_to_web_panel_user(
    *,
    user,
    title: str,
    body: str,
    notification_type: str,
    incident=None,
    data: dict | None = None,
    sse_payload: dict | None = None,
) -> None:
    """Encola entrega completa al panel web (segundo plano)."""
    from apps.notifications.web_panel_tasks import enqueue_deliver_to_web_panel_user

    enqueue_deliver_to_web_panel_user(
        user=user,
        title=title,
        body=body,
        notification_type=notification_type,
        incident=incident,
        data=data,
        sse_payload=sse_payload,
    )


def send_web_push_only(*, user, title: str, body: str, data: dict | None = None) -> int:
    """Encola solo Web Push (el caller ya creó BD/SSE en flujos móvil)."""
    from apps.notifications.web_panel_tasks import enqueue_web_push_only

    enqueue_web_push_only(user=user, title=title, body=body, data=data)
    return 0


def notify_web_panel_admins(
    *,
    title: str,
    body: str,
    notification_type: str,
    incident=None,
    data: dict | None = None,
    sse_payload: dict | None = None,
) -> None:
    from apps.notifications.web_panel_tasks import enqueue_notify_web_panel_admins

    enqueue_notify_web_panel_admins(
        title=title,
        body=body,
        notification_type=notification_type,
        incident=incident,
        data=data,
        sse_payload=sse_payload,
    )
