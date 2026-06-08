"""
Servidor de desarrollo ASGI (Daphne): HTTP + WebSockets de Channels.

`python manage.py runserver` usa WSGI y NO conoce las rutas `websocket_urlpatterns`;
el handshake a /ws/incident/<id>/ devuelve 404. Usa este comando en su lugar.
"""

import subprocess
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        'Arranca Daphne (ASGI) para API HTTP y WebSockets (/ws/incident/…). '
        'Sustituye a runserver cuando necesites tracking en tiempo real.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'addrport',
            nargs='?',
            default='0.0.0.0:8080',
            help='Host:puerto (por defecto 0.0.0.0:8080)',
        )

    def handle(self, *args, **options):
        addrport = options['addrport']
        if ':' in addrport:
            host, port = addrport.rsplit(':', 1)
        else:
            host, port = '0.0.0.0', addrport

        cmd = [
            sys.executable,
            '-m',
            'daphne',
            '-b',
            host,
            '-p',
            port,
            'config.asgi:application',
        ]
        self.stdout.write(self.style.SUCCESS(f'ASGI (Daphne) {host}:{port} — HTTP + WebSockets'))
        self.stdout.write('  (runserver WSGI no sirve para /ws/…; ver apps.realtime.routing)\n')
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            raise SystemExit(e.returncode) from e
