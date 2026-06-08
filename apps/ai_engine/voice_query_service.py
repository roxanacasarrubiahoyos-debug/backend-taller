"""
Consulta de reportes por voz: validación STT + fechas en español + GPT (filtros) + datos.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta

import openai
from django.conf import settings
from django.http import QueryDict
from django.utils import timezone

from apps.ai_engine.report_metrics import (
    build_client_reports_payload,
    build_technician_reports_payload,
    build_workshop_reports_payload,
)
from apps.ai_engine.transcript_utils import (
    extract_date_range,
    extract_rule_hints,
    normalize_text,
    validate_transcript,
)
from apps.ai_engine.whisper_service import WhisperService
from apps.incidents.models import IncidentStatus, IncidentType
from apps.payments.models import PaymentStatus
from apps.payments.reports_views import build_reports_payload
from apps.workshops.models import Workshop

logger = logging.getLogger(__name__)


class _FilterRequest:
    def __init__(self, params: dict):
        qd = QueryDict(mutable=True)
        for key, value in params.items():
            if value is not None and value != '':
                qd[key] = str(value)
        self.query_params = qd


class VoiceQueryService:
    def __init__(self):
        if settings.OPENAI_API_KEY:
            self.client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        else:
            self.client = None
        self.whisper = WhisperService()

    def process_admin(self, *, audio_file=None, text: str | None = None) -> dict:
        transcript, err = self._transcript_validated(audio_file, text)
        if err:
            return {'ok': False, 'error': err}

        workshops = list(
            Workshop.objects.filter(is_active=True).order_by('name').values('id', 'name')[:80]
        )
        parsed = self._parse_filters(transcript, audience='admin', workshops=workshops)
        if not parsed.get('ok'):
            return parsed

        filters = parsed['filters']
        req = _FilterRequest(filters)
        report = build_reports_payload(req)
        report = self._enrich_admin_report(report, filters, workshops)

        return {
            'ok': True,
            'audience': 'admin',
            'transcript': transcript,
            'intent_summary': parsed['intent_summary'],
            'filters': filters,
            'report': report,
        }

    def process_workshop(self, *, workshop: Workshop, audio_file=None, text: str | None = None) -> dict:
        transcript, err = self._transcript_validated(audio_file, text)
        if err:
            return {'ok': False, 'error': err}

        parsed = self._parse_filters(
            transcript,
            audience='workshop_owner',
            workshop_name=workshop.name,
        )
        if not parsed.get('ok'):
            return parsed

        filters = parsed['filters']
        req = _FilterRequest(filters)
        report = build_workshop_reports_payload(req, workshop)
        narrative = (report.get('summary') or {}).get('narrative') or parsed['intent_summary']

        return {
            'ok': True,
            'audience': 'workshop_owner',
            'transcript': transcript,
            'intent_summary': parsed['intent_summary'],
            'narrative_summary': narrative,
            'filters': filters,
            'report': report,
        }

    def process_client(self, *, client_profile, audio_file=None, text: str | None = None) -> dict:
        transcript, err = self._transcript_validated(audio_file, text)
        if err:
            return {'ok': False, 'error': err}

        parsed = self._parse_filters(transcript, audience='client')
        if not parsed.get('ok'):
            return parsed

        filters = parsed['filters']
        req = _FilterRequest(filters)
        report = build_client_reports_payload(req, client_profile)
        narrative = (report.get('summary') or {}).get('narrative') or parsed['intent_summary']

        return {
            'ok': True,
            'audience': 'client',
            'transcript': transcript,
            'intent_summary': parsed['intent_summary'],
            'narrative_summary': narrative,
            'filters': filters,
            'report': report,
        }

    def process_technician(
        self, *, technician, audio_file=None, text: str | None = None
    ) -> dict:
        transcript, err = self._transcript_validated(audio_file, text)
        if err:
            return {'ok': False, 'error': err}

        workshop_name = technician.workshop.name if technician.workshop_id else 'Taller'
        parsed = self._parse_filters(
            transcript,
            audience='technician',
            workshop_name=workshop_name,
        )
        if not parsed.get('ok'):
            return parsed

        filters = parsed['filters']
        req = _FilterRequest(filters)
        report = build_technician_reports_payload(req, technician)
        narrative = (report.get('summary') or {}).get('narrative') or parsed['intent_summary']

        return {
            'ok': True,
            'audience': 'technician',
            'transcript': transcript,
            'intent_summary': parsed['intent_summary'],
            'narrative_summary': narrative,
            'filters': filters,
            'report': report,
        }

    def _transcript_validated(self, audio_file, text: str | None) -> tuple[str, str | None]:
        if text and str(text).strip():
            transcript = normalize_text(str(text))
        elif audio_file:
            result = self.whisper.transcribe_upload(audio_file)
            if not result.get('success'):
                return '', result.get('error') or 'No se pudo transcribir el audio.'
            transcript = normalize_text(result.get('transcription', ''))
        else:
            return '', 'Envía audio o texto con tu solicitud.'

        ok, msg = validate_transcript(transcript)
        if not ok:
            return '', msg
        return transcript, None

    def _parse_filters(
        self,
        transcript: str,
        *,
        audience: str,
        workshops: list | None = None,
        workshop_name: str | None = None,
    ) -> dict:
        today = timezone.localdate()
        rule_hints = extract_rule_hints(transcript, audience=audience)
        d_from, d_to, date_hint = extract_date_range(transcript, today)

        gpt = self._gpt_parse(
            transcript,
            audience=audience,
            workshops=workshops,
            workshop_name=workshop_name,
            rule_hints=rule_hints,
            date_hint=date_hint,
        )
        if not gpt.get('ok'):
            return gpt

        data = gpt['data']
        filters = self._normalize_filters(data, audience=audience, rule_hints=rule_hints)

        # Fechas: prioridad extracción directa del texto del usuario
        if d_from and d_to:
            filters['date_from'] = d_from.isoformat()
            filters['date_to'] = d_to.isoformat()
            filters['dates_source'] = 'speech'
        else:
            filters['dates_source'] = data.get('dates_source') or 'inferred'

        intent = normalize_text(data.get('intent_summary') or '')
        if not intent or not self._intent_matches_transcript(intent, transcript):
            intent = self._fallback_intent(transcript, filters, date_hint, audience)

        return {'ok': True, 'filters': filters, 'intent_summary': intent}

    def _gpt_parse(
        self,
        transcript: str,
        *,
        audience: str,
        workshops: list | None,
        workshop_name: str | None,
        rule_hints: dict,
        date_hint: str,
    ) -> dict:
        if not self.client:
            return {'ok': False, 'error': 'OPENAI_API_KEY no configurada en el servidor.'}

        today = timezone.localdate().isoformat()
        status_opts = [c[0] for c in IncidentStatus.choices]
        type_opts = [c[0] for c in IncidentType.choices]
        pay_opts = [c[0] for c in PaymentStatus.choices]

        ws_block = ''
        if audience == 'admin' and workshops:
            ws_block = 'Talleres (id → nombre):\n' + '\n'.join(
                f"- {w['id']}: {w['name']}" for w in workshops
            )
        elif audience == 'workshop_owner':
            ws_block = f'Solo el taller "{workshop_name}". Ignora otros talleres.'
        elif audience == 'client':
            ws_block = 'Solo las solicitudes/emergencias del cliente autenticado. Nunca datos de otros usuarios.'
        elif audience == 'technician':
            ws_block = (
                f'Solo las órdenes asignadas al técnico en «{workshop_name}». '
                'Sin pagos ni datos de otros técnicos.'
            )

        if audience == 'client':
            focus_opts = 'general|completed|payments|active|cancelled'
            assign_rule = 'assignment_status: siempre null (cliente)'
        elif audience == 'technician':
            focus_opts = 'general|completed|active'
            assign_rule = 'assignment_status: accepted|in_route|arrived|in_service|completed o null'
        elif audience == 'workshop_owner':
            focus_opts = 'general|completed|payments|active|offered|technicians|ratings'
            assign_rule = 'assignment_status: offered|completed|rejected|... o null'
        else:
            focus_opts = 'general|completed|payments|new_workshops|active|offered|technicians|ratings'
            assign_rule = 'assignment_status: null'

        hints_json = json.dumps(rule_hints, ensure_ascii=False)

        prompt = f"""
Fecha de hoy: {today}.
Transcripción EXACTA del usuario (no la modifiques ni inventes otra petición):
\"\"\"{transcript}\"\"\"

Pistas automáticas ya detectadas en su frase: {hints_json}
Pista de fechas detectada en texto: "{date_hint or 'ninguna'}"

{ws_block}

Devuelve SOLO JSON:
{{
  "date_from": "YYYY-MM-DD o null si el usuario NO indicó período",
  "date_to": "YYYY-MM-DD o null si el usuario NO indicó período",
  "dates_source": "speech" si el usuario dijo fechas/período, "inferred" solo si mencionó algo vago sin fechas, "none" si no habló de tiempo,
  "workshop_id": número o null,
  "incident_status": uno de {status_opts} o null,
  "incident_type": uno de {type_opts} o null,
  "payment_status": uno de {pay_opts} o null,
  "assignment_status": {assign_rule},
  "report_focus": "{focus_opts}",
  "intent_summary": "resumen en español citando palabras del usuario (máx 140 caracteres)"
}}

REGLAS CRÍTICAS:
1. intent_summary DEBE reflejar lo que DIJO el usuario, usando sus palabras (completados, ingresos, talleres, etc.).
2. NO inventes "último mes" ni ningún período si el usuario no lo mencionó y dates_source es "none".
3. Si menciona "completados/finalizados" → incident_status completed (admin/cliente) o assignment_status completed (taller/técnico).
4. Si menciona "talleres registrados/nuevos" → report_focus new_workshops (solo admin).
5. Si menciona ingresos/pagos/gastos → report_focus payments (cliente/taller).
6. workshop_id solo si nombra un taller concreto de la lista (solo admin).
7. Calcula fechas SOLO si el usuario las menciona (esta semana, marzo, últimos 15 días, etc.).
"""

        try:
            response = self.client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {
                        'role': 'system',
                        'content': (
                            'Interpretas pedidos de reportes en español. '
                            'Nunca sustituyas la petición del usuario por un reporte genérico. '
                            'Responde únicamente JSON válido.'
                        ),
                    },
                    {'role': 'user', 'content': prompt},
                ],
                max_tokens=450,
                temperature=0,
            )
            raw = (response.choices[0].message.content or '').strip()
            data = self._extract_json(raw)
            return {'ok': True, 'data': data}
        except Exception as exc:
            logger.exception('voice query parse: %s', exc)
            return {'ok': False, 'error': f'No se interpretó la solicitud: {exc}'}

    def _normalize_filters(self, data: dict, *, audience: str, rule_hints: dict) -> dict:
        today = timezone.localdate()

        date_from = data.get('date_from')
        date_to = data.get('date_to')
        dates_source = data.get('dates_source') or 'none'

        if dates_source == 'none' or (not date_from and not date_to):
            # Sin período mencionado: mes en curso (no inventar "último mes")
            date_from = today.replace(day=1).isoformat()
            date_to = today.isoformat()
            dates_source = 'default_month'
        else:
            if not date_to:
                date_to = today.isoformat()
            if not date_from:
                date_from = (today - timedelta(days=30)).isoformat()

        try:
            date.fromisoformat(str(date_from)[:10])
            date.fromisoformat(str(date_to)[:10])
        except ValueError:
            date_from = today.replace(day=1).isoformat()
            date_to = today.isoformat()

        filters = {
            'date_from': str(date_from)[:10],
            'date_to': str(date_to)[:10],
            'dates_source': dates_source,
            'incident_status': data.get('incident_status') or rule_hints.get('incident_status') or '',
            'incident_type': data.get('incident_type') or rule_hints.get('incident_type') or '',
            'payment_status': data.get('payment_status') or '',
            'assignment_status': data.get('assignment_status') or rule_hints.get('assignment_status') or '',
            'report_focus': data.get('report_focus') or rule_hints.get('report_focus') or 'general',
        }
        if audience == 'client':
            filters.pop('assignment_status', None)
            if filters['report_focus'] == 'completed':
                filters['incident_status'] = 'completed'
        elif audience == 'technician':
            if filters['report_focus'] == 'completed' and not filters.get('assignment_status'):
                filters['assignment_status'] = 'completed'
            elif filters['report_focus'] == 'active' and not filters.get('assignment_status'):
                filters.pop('assignment_status', None)
        elif filters['report_focus'] == 'offered' and dates_source in ('none', 'default_month'):
            filters['assignment_status'] = 'offered'

        if audience == 'admin':
            ws = data.get('workshop_id')
            if ws is not None and str(ws).isdigit():
                filters['workshop_id'] = str(int(ws))
            else:
                filters['workshop_id'] = ''
        else:
            filters.pop('workshop_id', None)

        return filters

    def _intent_matches_transcript(self, intent: str, transcript: str) -> bool:
        """Evita resúmenes genéricos que no relacionan con lo dicho."""
        generic_bad = (
            'solicitar reporte de incidentes del ultimo mes',
            'reporte de incidentes del ultimo mes',
            'reporte solicitado por voz',
        )
        intent_l = normalize_text(intent).lower()
        if any(b in intent_l for b in generic_bad):
            return False
        # Al menos una palabra significativa del transcript en el intent
        words = [w for w in re.findall(r'\w{4,}', transcript.lower()) if w not in ('reporte', 'quiero', 'dame', 'muestra', 'mostrar')]
        if not words:
            return True
        return any(w in intent_l for w in words[:8])

    def _fallback_intent(
        self, transcript: str, filters: dict, date_hint: str, audience: str
    ) -> str:
        parts = [f'Pediste: «{transcript[:120]}»']
        if date_hint:
            parts.append(f'Período: {date_hint}')
        elif filters.get('dates_source') == 'default_month':
            parts.append('Período: mes en curso (no especificaste fechas)')
        focus = filters.get('report_focus', 'general')
        if focus != 'general':
            parts.append(f'Enfoque: {focus}')
        return ' · '.join(parts)

    def _enrich_admin_report(self, report: dict, filters: dict, workshops: list) -> dict:
        """Tabla extra cuando piden talleres registrados."""
        if filters.get('report_focus') != 'new_workshops':
            return report

        from django.utils.dateparse import parse_date

        d0 = parse_date(filters['date_from'])
        d1 = parse_date(filters['date_to'])
        if not d0 or not d1:
            return report

        rows = list(
            Workshop.objects.filter(
                created_at__date__gte=d0,
                created_at__date__lte=d1,
            )
            .order_by('-created_at')[:50]
            .values('id', 'name', 'is_verified', 'is_active', 'created_at', 'rating_avg')
        )
        for row in rows:
            ca = row.get('created_at')
            row['created_at'] = ca.isoformat() if ca else None
            row['rating_avg'] = float(row['rating_avg'] or 0)

        report.setdefault('tables', {})['new_workshops'] = rows
        return report

    def _extract_json(self, raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise
