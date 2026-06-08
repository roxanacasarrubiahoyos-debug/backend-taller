#!/usr/bin/env bash
# ASGI (Daphne): HTTP + WebSockets. NO uses `runserver` para la app móvil: el handshake
# a /ws/incident/… devuelve 404 con WSGI.
# Uso: ./run_daphne.sh   o   python manage.py runasgi 0.0.0.0:8080
set -euo pipefail
cd "$(dirname "$0")"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings}"
PORT="${PORT:-8080}"
exec python manage.py runasgi "0.0.0.0:${PORT}"
