"""
Validación de transcripciones y extracción de fechas/intención en español.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

# Frases que Whisper inventa con silencio o audio vacío
WHISPER_HALLUCINATION_MARKERS = (
    'amara.org',
    'subtitulos realizados por la comunidad',
    'subtítulos realizados por la comunidad',
    'thanks for watching',
    'thank you for watching',
    'sous-titres',
    'subtitle',
    'subscribe to',
    'copyright',
    'mbc news',
    'www.',
    'http://',
    'https://',
)

MONTHS_ES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10,
    'noviembre': 11, 'diciembre': 12,
}


def normalize_text(text: str) -> str:
    t = (text or '').strip()
    t = re.sub(r'\s+', ' ', t)
    return t


def strip_accents(s: str) -> str:
    nf = unicodedata.normalize('NFD', s)
    return ''.join(c for c in nf if unicodedata.category(c) != 'Mn')


def validate_transcript(text: str) -> tuple[bool, str]:
    """False + mensaje si la transcripción no es confiable."""
    t = normalize_text(text)
    if len(t) < 10:
        return False, 'No se captó tu voz. Habla una frase completa (mínimo unos segundos) o escribe el pedido.'

    lower = strip_accents(t.lower())
    for marker in WHISPER_HALLUCINATION_MARKERS:
        if marker in lower:
            return False, (
                'No se entendió tu voz (audio vacío o ruido). '
                'Vuelve a intentar: habla claro, 2–5 segundos, o escribe tu pedido abajo.'
            )

    # Muy pocos tokens en español útiles
    words = [w for w in re.findall(r'[a-záéíóúñ]{3,}', lower, re.I) if w not in ('reporte', 'quiero', 'dame')]
    if len(words) < 2:
        return False, 'La frase fue demasiado corta. Menciona qué reporte necesitas y el período.'

    return True, ''


def extract_date_range(transcript: str, today: date) -> tuple[date | None, date | None, str]:
    """
    Extrae rango de fechas del texto. Retorna (from, to, hint) donde hint describe lo detectado.
    """
    raw = normalize_text(transcript)
    t = strip_accents(raw.lower())

    # Rango explícito ISO
    iso_range = re.search(
        r'(\d{4}-\d{2}-\d{2})\s*(?:a|al|hasta|-|y)\s*(\d{4}-\d{2}-\d{2})',
        t,
    )
    if iso_range:
        try:
            d1 = date.fromisoformat(iso_range.group(1))
            d2 = date.fromisoformat(iso_range.group(2))
            return min(d1, d2), max(d1, d2), 'rango ISO'

        except ValueError:
            pass

    if re.search(r'\bhoy\b', t):
        return today, today, 'hoy'

    if re.search(r'\bayer\b', t):
        y = today - timedelta(days=1)
        return y, y, 'ayer'

    m_days = re.search(r'ultim[oa]s?\s+(\d{1,3})\s+d[ií]as', t)
    if m_days:
        n = int(m_days.group(1))
        n = min(max(n, 1), 365)
        return today - timedelta(days=n), today, f'últimos {n} días'

    if re.search(r'ultim[oa]?\s+mes|mes\s+pasado|del\s+mes\s+pasado', t):
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return first_prev, last_prev, 'mes pasado'

    if re.search(r'este\s+mes|mes\s+actual|en\s+el\s+mes', t):
        return today.replace(day=1), today, 'este mes'

    if re.search(r'esta\s+semana|semana\s+actual', t):
        start = today - timedelta(days=today.weekday())
        return start, today, 'esta semana'

    if re.search(r'ultima\s+semana|semana\s+pasada', t):
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
        return start, end, 'semana pasada'

    # "en marzo", "marzo 2026", "de abril a mayo"
    for month_name, month_num in MONTHS_ES.items():
        if month_name not in t:
            continue
        year_m = re.search(rf'{month_name}\s+(20\d{{2}})', t)
        year = int(year_m.group(1)) if year_m else today.year
        d_from = date(year, month_num, 1)
        if month_num == 12:
            d_to = date(year, 12, 31)
        else:
            d_to = date(year, month_num + 1, 1) - timedelta(days=1)
        return d_from, d_to, f'mes {month_name} {year}'

    return None, None, ''


def extract_rule_hints(transcript: str, *, audience: str) -> dict:
    """Pistas determinísticas a partir de palabras del usuario."""
    t = strip_accents(normalize_text(transcript).lower())
    hints: dict = {}

    if any(w in t for w in ('completado', 'completados', 'finalizado', 'terminado', 'cerrado')):
        if audience in ('admin', 'client'):
            hints['incident_status'] = 'completed'
        else:
            hints['assignment_status'] = 'completed'
        hints['report_focus'] = 'completed'

    if any(w in t for w in ('cancelado', 'cancelados', 'anulado')):
        hints['incident_status'] = 'cancelled'
        hints['report_focus'] = 'cancelled'

    if any(w in t for w in ('activo', 'activos', 'en curso', 'en proceso', 'abierto')):
        hints['report_focus'] = 'active'

    if any(
        w in t
        for w in (
            'ingreso', 'ingresos', 'ganancia', 'ganancias', 'pago', 'pagos', 'facturacion',
            'gasto', 'gastos', 'cuanto pague', 'cuanto pagu', 'cuanto gast',
        )
    ):
        hints['report_focus'] = 'payments'

    if audience == 'admin' and any(
        w in t for w in ('taller registrado', 'talleres registrados', 'talleres nuevos', 'nuevo taller', 'altas de taller')
    ):
        hints['report_focus'] = 'new_workshops'

    if any(w in t for w in ('bateria', 'batería')):
        hints['incident_type'] = 'battery'
    elif 'llanta' in t or 'neumatico' in t or 'neumático' in t:
        hints['incident_type'] = 'tire'
    elif 'motor' in t:
        hints['incident_type'] = 'engine'
    elif any(w in t for w in ('grua', 'grúa', 'remolque')):
        hints['incident_type'] = 'towing'

    if any(
        w in t
        for w in (
            'listado', 'listar', 'todos los estados', 'todos los incidente',
            'todas las asignaciones', 'resumen completo', 'mis incidentes',
            'mis solicitudes', 'mis emergencias', 'mis ordenes', 'mis órdenes',
            'todos mis', 'en todos',
        )
    ):
        hints['report_focus'] = 'general'

    if any(
        w in t
        for w in (
            'oferta', 'ofertas', 'ofertada', 'sin responder',
            'disponible', 'disponibles', 'esperando respuesta',
            'cuantos incidente dispon', 'cuántos incidente dispon',
        )
    ):
        hints['assignment_status'] = 'offered'
        hints['report_focus'] = 'offered'

    if any(w in t for w in ('tecnico', 'técnico', 'tecnicos', 'técnicos', 'equipo')):
        hints['report_focus'] = 'technicians'

    if any(w in t for w in ('calificacion', 'calificación', 'rating', 'estrellas')):
        hints['report_focus'] = 'ratings'

    return hints
