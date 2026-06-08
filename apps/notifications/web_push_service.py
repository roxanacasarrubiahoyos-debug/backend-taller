"""
Web Push (VAPID) para el panel Angular — sin Firebase.
No usa ni modifica fcm_token (app móvil cliente/técnico).
"""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def vapid_public_key() -> str:
    return getattr(settings, 'WEB_PUSH_VAPID_PUBLIC_KEY', '') or ''


def vapid_configured() -> bool:
    return bool(vapid_public_key() and getattr(settings, 'WEB_PUSH_VAPID_PRIVATE_KEY', ''))


def _load_vapid_private_key():
    """Instancia Vapid01 para pywebpush (PEM en .env o base64 de `web-push generate-vapid-keys`)."""
    raw = (getattr(settings, 'WEB_PUSH_VAPID_PRIVATE_KEY', '') or '').strip()
    if not raw:
        return None
    from py_vapid import Vapid01
    if raw.startswith('-----'):
        return Vapid01.from_pem(raw.encode('utf-8'))
    return Vapid01.from_raw(raw.encode('ascii'))


def _subscription_info(sub) -> dict:
    return {
        'endpoint': sub.endpoint,
        'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
    }


def send_web_push_to_user(user, title: str, body: str, data: dict | None = None) -> int:
    """
    Envía push a todas las suscripciones web activas del usuario.
    Retorna cantidad de envíos exitosos.
    """
    if not vapid_configured():
        return 0

    from apps.notifications.web_push_models import WebPushSubscription

    role = getattr(user, 'role', None)
    if role not in ('workshop_owner', 'admin'):
        return 0

    subs = list(WebPushSubscription.objects.filter(user=user, is_active=True))
    if not subs:
        return 0

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning('pywebpush no instalado; omitiendo web push')
        return 0

    payload = json.dumps(
        {
            'title': title,
            'body': body,
            'data': data or {},
        },
        ensure_ascii=False,
    )
    claims = {'sub': settings.WEB_PUSH_VAPID_CLAIMS_EMAIL}
    vapid_key = _load_vapid_private_key()

    sent = 0
    for sub in subs:
        try:
            webpush(
                subscription_info=_subscription_info(sub),
                data=payload,
                vapid_private_key=vapid_key,
                vapid_claims=claims,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(exc, 'response', None)
            code = getattr(status, 'status_code', None) if status is not None else None
            if code in (404, 410):
                sub.is_active = False
                sub.save(update_fields=['is_active', 'updated_at'])
            logger.warning('Web push falló user=%s code=%s: %s', user.id, code, exc)
        except Exception as exc:
            logger.warning('Web push error user=%s: %s', user.id, exc)
    return sent
