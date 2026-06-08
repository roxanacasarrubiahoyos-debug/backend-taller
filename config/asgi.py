"""
ASGI config for emergency vehicle platform.

HTTP (Django + SSE django-eventstream vía urls) y WebSockets (Channels).

Desarrollo: `python manage.py runasgi` o `./run_daphne.sh` — no `runserver`
(WSGI devuelve 404 en el upgrade a /ws/incident/<id>/).
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

from apps.realtime.routing import websocket_urlpatterns

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        'http': django_asgi_app,
        'websocket': URLRouter(websocket_urlpatterns),
    }
)
