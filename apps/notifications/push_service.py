"""
Envío de notificaciones push: tokens nativos FCM/APNs (Firebase Admin) y tokens Expo
(ExponentPushToken[...]) vía API HTTP de Expo. La app móvil suele registrar el token Expo.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.conf import settings

def _is_expo_push_token(token: str) -> bool:
    if not token or not isinstance(token, str):
        return False
    t = token.strip()
    return t.startswith('ExponentPushToken[') or t.startswith('ExpoPushToken')


def send_device_push(token: str, title: str, body: str, data: dict | None = None) -> str | None:
    """
    Entrega una notificación al dispositivo. Usa Expo Push API o Firebase según el formato del token.
    """
    if not token:
        return None
    data = data or {}
    if _is_expo_push_token(token):
        return _send_expo_push(token, title, body, data)
    from apps.notifications.firebase_service import FirebaseService

    fb = FirebaseService()
    return fb._send_fcm_direct(token, title, body, data)


def _send_expo_push(token: str, title: str, body: str, data: dict) -> str | None:
    """https://docs.expo.dev/push-notifications/sending-notifications/"""
    payload = {
        'to': token,
        'title': title,
        'body': body,
        'data': {str(k): str(v) for k, v in data.items()},
        'sound': 'default',
        'priority': 'high',
        'channelId': 'default',
    }
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    if getattr(settings, 'EXPO_ACCESS_TOKEN', ''):
        headers['Authorization'] = f'Bearer {settings.EXPO_ACCESS_TOKEN}'

    req = urllib.request.Request(
        'https://exp.host/--/api/v2/push/send',
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode('utf-8')
            parsed = json.loads(raw)
        data_block = parsed.get('data')
        if isinstance(data_block, list) and data_block:
            status = data_block[0].get('status')
            if status == 'error':
                print(f"Expo push error: {data_block[0]}")
                return None
        return raw[:200] if raw else 'ok'
    except urllib.error.HTTPError as e:
        print(f"Expo push HTTPError: {e.code} {e.read()!r}")
        return None
    except Exception as e:
        print(f"Expo push failed: {e}")
        return None


def send_device_push_many(tokens: list, title: str, body: str, data: dict | None = None) -> None:
    """
    Envía a varios tokens (uno a uno; Expo y FCM tienen formatos distintos).
    """
    for t in tokens:
        if t:
            send_device_push(t, title, body, data)
