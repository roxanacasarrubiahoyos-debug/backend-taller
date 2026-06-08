import openai
from django.conf import settings
import json


class SummaryService:
    """
    Genera una ficha estructurada del incidente usando GPT-4o-mini.
    """

    def __init__(self):
        if settings.OPENAI_API_KEY:
            self.client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        else:
            self.client = None

    def generate_summary(self, incident_data: dict) -> str:
        """
        incident_data: {
            'transcription': str,
            'classification': str,
            'confidence': float,
            'description': str,
            'vehicle': {'brand', 'model', 'year'},
            'address': str,
        }

        Retorna JSON string con el resumen estructurado.
        """
        if not self.client:
            return json.dumps({
                'tipo_incidente': incident_data.get('classification', 'uncertain'),
                'prioridad': 'media',
                'resumen_breve': 'API key no configurada',
                'servicios_requeridos': ['general'],
                'notas_tecnicas': 'OpenAI API key not configured',
                'requiere_grua': False
            })

        prompt = f"""
Eres un asistente de emergencias vehiculares. Genera una ficha técnica estructurada
y concisa del siguiente incidente:

- Descripción del usuario: {incident_data.get('description', 'No proporcionada')}
- Transcripción de audio: {incident_data.get('transcription', 'No disponible')}
- Clasificación IA: {incident_data.get('classification')} (confianza: {incident_data.get('confidence', 0):.0%})
- Vehículo: {incident_data.get('vehicle', {}).get('brand')} {incident_data.get('vehicle', {}).get('model')} {incident_data.get('vehicle', {}).get('year')}
- Ubicación: {incident_data.get('address', 'No especificada')}

Genera la ficha en formato JSON con:
- tipo_incidente (string: battery|tire|accident|engine|locksmith|overheating|other)
- prioridad (string: baja|media|alta|crítica)
- resumen_breve (string, máximo 200 caracteres)
- servicios_requeridos (array de strings)
- notas_tecnicas (string)
- requiere_grua (boolean)

Responde SOLO el JSON, sin explicaciones adicionales.
"""

        try:
            response = self.client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=500,
                temperature=0.2,
            )
            content = response.choices[0].message.content.strip()

            # Intentar parsear para validar que es JSON válido
            try:
                json.loads(content)
                return content
            except json.JSONDecodeError:
                # Si no es JSON válido, extraer JSON del texto
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    return json_match.group(0)
                else:
                    raise ValueError("No JSON found in response")

        except Exception as e:
            # Retornar un JSON fallback en caso de error
            return json.dumps({
                'tipo_incidente': incident_data.get('classification', 'uncertain'),
                'prioridad': 'media',
                'resumen_breve': f'Error generando resumen: {str(e)[:100]}',
                'servicios_requeridos': [incident_data.get('classification', 'general')],
                'notas_tecnicas': str(e),
                'requiere_grua': False
            })
