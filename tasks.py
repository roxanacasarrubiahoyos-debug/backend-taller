"""
Tareas asíncronas usando django-q2.
Se ejecutan en background sin necesidad de Redis (usa ORM).
"""
from django_q.tasks import async_task


def enqueue_incident_pipeline(incident_id: int):
    """
    Encola el procesamiento IA del incidente para ejecución asíncrona.

    Args:
        incident_id: ID del incidente a procesar
    """
    async_task(
        'apps.ai_engine.pipeline.process_incident_pipeline',
        incident_id,
        hook='tasks.on_pipeline_complete',
    )


def on_pipeline_complete(task):
    """
    Callback que se ejecuta cuando termina el pipeline IA.

    Args:
        task: Objeto Task de django-q con resultados
    """
    from apps.notifications.sse_views import notify_incident_update

    if task.success:
        # Notificar vía SSE que el análisis terminó
        try:
            # El task.args[0] contiene el incident_id
            incident_id = task.args[0] if task.args else None
            if incident_id:
                payload = task.result if isinstance(task.result, dict) else {}
                notify_incident_update(incident_id, {
                    'event': 'ai_complete',
                    'status': 'success',
                    'incident_id': incident_id,
                    'type': payload.get('type'),
                    'priority': payload.get('priority'),
                    'confidence': payload.get('confidence'),
                    'candidates_count': payload.get('candidates_count'),
                })
        except Exception as e:
            print(f"Error in pipeline complete callback: {e}")
    else:
        print(f"Pipeline task failed: {task.result}")
