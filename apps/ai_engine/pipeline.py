"""
Orquesta el procesamiento asíncrono de un incidente recién creado.
Se ejecuta via django-q2 en background.
"""
import re
import unicodedata
from collections import defaultdict

from apps.ai_engine.whisper_service import WhisperService
from apps.ai_engine.classifier_service import IncidentClassifier
from apps.ai_engine.summary_service import SummaryService
from apps.incidents.models import Incident, Evidence, EvidenceType, IncidentType, IncidentPriority, IncidentStatus
from apps.notifications.sse_views import notify_incident_update


# Mapeo de tipo de incidente a prioridad
PRIORITY_MAP = {
    'accident': IncidentPriority.HIGH,
    'engine': IncidentPriority.HIGH,
    'overheating': IncidentPriority.HIGH,
    'battery': IncidentPriority.MEDIUM,
    'tire': IncidentPriority.MEDIUM,
    'locksmith': IncidentPriority.LOW,
    'other': IncidentPriority.LOW,
    'uncertain': IncidentPriority.MEDIUM,
}


KEYWORDS_BY_TYPE = {
    'battery': ['bateria', 'batería', 'descargad', 'no enciende', 'no prende', 'arrancar'],
    'tire': ['llanta', 'pinchad', 'neumatic', 'neumático', 'ponchad', 'reventad'],
    'engine': ['motor', 'humo', 'aceite', 'correa', 'temperatura', 'calienta', 'sobrecalent'],
    'accident': ['choque', 'accident', 'colision', 'colisión', 'golpe', 'impacto'],
    'locksmith': ['llave', 'cerradura', 'cerrajer', 'bloquead', 'puerta'],
    'overheating': ['sobrecalent', 'radiador', 'temperatura alta', 'agua hirviendo'],
}


def _normalize_text(value: str) -> str:
    text = (value or '').lower().strip()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', text)


def _infer_type_from_text(description: str, transcriptions: list[str]) -> tuple[str, float]:
    text = _normalize_text(' '.join([description or '', *transcriptions]))
    if not text:
        return 'uncertain', 0.0

    score = defaultdict(float)
    for incident_type, keywords in KEYWORDS_BY_TYPE.items():
        for kw in keywords:
            kw_n = _normalize_text(kw)
            if kw_n in text:
                score[incident_type] += 1.0

    if not score:
        return 'uncertain', 0.0

    best = max(score, key=score.get)
    # Confidence heurística en rango 0..1, saturando con múltiples coincidencias.
    conf = min(0.9, 0.35 + 0.12 * score[best])
    return best, conf


def _decide_incident_type(best_image: dict, text_type: str, text_conf: float) -> tuple[str, float]:
    """
    Fusión simple y robusta:
    - si imagen tiene confianza alta, prioriza imagen
    - si imagen está débil/placeholder, usa texto-audio
    - si no hay señal fuerte, devuelve uncertain
    """
    image_label = str(best_image.get('label') or 'uncertain')
    image_conf = float(best_image.get('confidence') or 0.0)
    image_source = str(best_image.get('source') or 'model')

    # Placeholder no debe sesgar la clasificación.
    if image_source == 'placeholder' and text_conf > 0:
        return text_type, text_conf

    if image_conf >= 0.6 and image_label != 'uncertain':
        return image_label, image_conf

    if text_conf >= 0.45 and text_type != 'uncertain':
        return text_type, text_conf

    if image_conf >= 0.35 and image_label != 'uncertain':
        return image_label, image_conf

    return 'uncertain', max(image_conf, text_conf, 0.0)


def process_incident_pipeline(incident_id: int):
    """
    Función principal ejecutada por django-q2.

    Proceso:
    1. Marca incidente como 'analyzing'
    2. Procesa evidencias de audio (Whisper)
    3. Procesa evidencias de imagen (TensorFlow)
    4. Determina tipo y prioridad
    5. Genera resumen con GPT
    6. Actualiza incidente
    7. Dispara motor de asignación
    """
    try:
        incident = Incident.objects.get(id=incident_id)
    except Incident.DoesNotExist:
        print(f"Incident {incident_id} not found")
        return

    # Cambiar estado a analyzing
    incident.status = IncidentStatus.ANALYZING
    incident.save(update_fields=['status'])
    notify_incident_update(incident.id, {
        'event': 'status_change',
        'incident_id': incident.id,
        'status': IncidentStatus.ANALYZING,
    })

    # Inicializar servicios IA
    whisper = WhisperService()
    classifier = IncidentClassifier()
    summary_svc = SummaryService()

    transcriptions = []
    best_classification = {'label': 'uncertain', 'confidence': 0.0}

    # Procesar evidencias
    for evidence in incident.evidences.all():
        if evidence.evidence_type == EvidenceType.AUDIO and not evidence.transcription_done:
            result = whisper.transcribe(evidence.file.path)
            if result['success']:
                evidence.transcription = result['transcription']
                evidence.transcription_done = True
                evidence.save()
                transcriptions.append(result['transcription'])

        elif evidence.evidence_type == EvidenceType.IMAGE:
            result = classifier.predict(evidence.file.path)
            evidence.image_analysis = result
            evidence.label = result.get('label', '')
            evidence.save()
            if result.get('confidence', 0) > best_classification['confidence']:
                best_classification = result

    # Determinar tipo con fusión coherente: imagen + descripción + audio.
    text_type, text_conf = _infer_type_from_text(incident.description, transcriptions)
    incident_type, final_conf = _decide_incident_type(best_classification, text_type, text_conf)

    # Validar que el tipo esté en las opciones válidas
    valid_types = [choice[0] for choice in IncidentType.choices]
    if incident_type not in valid_types:
        incident_type = IncidentType.OTHER

    # Preparar datos del vehículo para el resumen
    vehicle_info = {}
    if incident.vehicle:
        vehicle_info = {
            'brand': incident.vehicle.brand,
            'model': incident.vehicle.model,
            'year': incident.vehicle.year
        }

    # Generar resumen GPT
    summary_json = summary_svc.generate_summary({
        'transcription': ' '.join(transcriptions),
        'classification': incident_type,
        'confidence': best_classification.get('confidence', 0),
        'description': incident.description,
        'vehicle': vehicle_info,
        'address': incident.address_text,
    })

    # Actualizar incidente con resultados
    incident.incident_type = incident_type
    incident.ai_transcription = ' '.join(transcriptions)
    incident.ai_classification_raw = {
        **best_classification,
        'fusion': {
            'text_type': text_type,
            'text_confidence': text_conf,
            'final_type': incident_type,
            'final_confidence': final_conf,
        },
    }
    incident.ai_summary = summary_json
    incident.ai_confidence = final_conf
    incident.priority = PRIORITY_MAP.get(incident_type, IncidentPriority.MEDIUM)
    incident.status = IncidentStatus.WAITING_WORKSHOP
    incident.save()
    notify_incident_update(incident.id, {
        'event': 'status_change',
        'incident_id': incident.id,
        'status': IncidentStatus.WAITING_WORKSHOP,
        'incident_type': incident.incident_type,
        'priority': incident.priority,
    })

    # Disparar motor de asignación
    try:
        from apps.assignments.engine import AssignmentEngine
        candidates = AssignmentEngine.find_and_notify_workshops(incident)
    except Exception as e:
        print(f"Error in assignment engine: {e}")
        candidates = []

    notify_incident_update(incident.id, {
        'event': 'ai_complete',
        'incident_id': incident.id,
        'type': incident.incident_type,
        'priority': incident.priority,
        'confidence': incident.ai_confidence,
        'candidates_count': len(candidates),
    })

    try:
        from apps.notifications.models import NotificationType
        from apps.notifications.web_panel_notify import notify_web_panel_admins

        notify_web_panel_admins(
            title='Nuevo incidente en plataforma',
            body=(
                f'Incidente #{incident.id} ({incident.get_incident_type_display()}) '
                f'listo para asignación — {len(candidates)} taller(es) notificados.'
            ),
            notification_type=NotificationType.INCIDENT_CREATED,
            incident=incident,
            data={'incident_id': incident.id, 'type': 'incident_created'},
            sse_payload={
                'event': 'admin_new_incident',
                'incident_id': incident.id,
                'candidates_count': len(candidates),
            },
        )
    except Exception as e:
        print(f"Web panel admin notify failed: {e}")

    print(f"Incident {incident_id} processed successfully")
    return {
        'incident_id': incident.id,
        'type': incident.incident_type,
        'priority': incident.priority,
        'confidence': incident.ai_confidence,
        'candidates_count': len(candidates),
    }
