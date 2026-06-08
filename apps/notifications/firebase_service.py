import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
import os


class FirebaseService:
    """
    Servicio de notificaciones push con Firebase Cloud Messaging.
    """
    _initialized = False

    def __init__(self):
        if not FirebaseService._initialized and settings.FIREBASE_CREDENTIALS_PATH:
            if os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
                try:
                    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                    firebase_admin.initialize_app(cred)
                    FirebaseService._initialized = True
                except Exception as e:
                    print(f"Error initializing Firebase: {e}")
            else:
                print(f"Firebase credentials file not found: {settings.FIREBASE_CREDENTIALS_PATH}")

    def send_notification(self, token: str, title: str, body: str, data: dict = None):
        """
        Entrega push al dispositivo (Expo Push API o FCM según el token).
        """
        from apps.notifications.push_service import send_device_push
        return send_device_push(token, title, body, data)

    def _send_fcm_direct(self, token: str, title: str, body: str, data: dict = None):
        """Solo FCM nativo (sin pasar por Expo). Usado internamente por push_service."""
        if not token:
            return None
        if not FirebaseService._initialized:
            print("Firebase not initialized - notification not sent")
            return None
        try:
            data_str = {k: str(v) for k, v in (data or {}).items()}
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=data_str,
                token=token,
            )
            response = messaging.send(message)
            print(f"Successfully sent FCM message: {response}")
            return response
        except Exception as e:
            print(f"Error sending Firebase notification: {e}")
            return None

    def send_multicast(self, tokens: list, title: str, body: str, data: dict = None):
        """
        Envía una notificación a múltiples dispositivos.

        Args:
            tokens: Lista de FCM tokens
            title: Título de la notificación
            body: Cuerpo del mensaje
            data: Datos adicionales (dict)

        Returns:
            BatchResponse object
        """
        if not tokens:
            return None

        from apps.notifications.push_service import send_device_push
        ok = 0
        for t in tokens:
            if t and send_device_push(t, title, body, data):
                ok += 1
        print(f"Multicast push: {ok}/{len(tokens)}")
        return ok
