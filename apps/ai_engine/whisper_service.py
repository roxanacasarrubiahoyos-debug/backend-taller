import os
import tempfile

import openai
from django.conf import settings

from apps.ai_engine.transcript_utils import validate_transcript

MIN_AUDIO_BYTES = 1500
MIN_AUDIO_SECONDS = 0.6

WHISPER_PROMPT = (
    'Reporte de emergencias vehiculares en Bolivia. '
    'El usuario pide datos: incidentes, ingresos, talleres, pagos, período, fechas.'
)


class WhisperService:
    """
    Transcribe audio a texto usando OpenAI Whisper API.
    Compatible con: mp3, mp4, mpeg, mpga, m4a, wav, webm.
    Máximo 25 MB por archivo.
    """

    def __init__(self):
        if settings.OPENAI_API_KEY:
            self.client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        else:
            self.client = None

    def transcribe(self, audio_file_path: str, language: str = 'es') -> dict:
        """
        Retorna: {'transcription': str, 'duration': float, 'success': bool}
        """
        if not self.client:
            return {
                'transcription': '',
                'success': False,
                'error': 'OpenAI API key not configured'
            }

        try:
            with open(audio_file_path, 'rb') as audio_file:
                response = self.client.audio.transcriptions.create(
                    model='whisper-1',
                    file=audio_file,
                    language=language,
                    prompt=WHISPER_PROMPT,
                    response_format='verbose_json',
                )
            text = (response.text or '').strip()
            duration = float(getattr(response, 'duration', 0) or 0)
            ok, err = validate_transcript(text)
            if duration and duration < MIN_AUDIO_SECONDS:
                return {
                    'transcription': '',
                    'success': False,
                    'error': 'Grabación muy corta. Habla al menos 2 segundos.',
                }
            if not ok:
                return {'transcription': '', 'success': False, 'error': err}
            return {
                'transcription': text,
                'duration': duration,
                'success': True,
                'segments': getattr(response, 'segments', []),
            }
        except Exception as e:
            return {
                'transcription': '',
                'success': False,
                'error': str(e)
            }

    def transcribe_upload(self, uploaded_file, language: str = 'es') -> dict:
        """Transcribe un archivo subido (multipart) guardándolo temporalmente."""
        if not uploaded_file:
            return {'transcription': '', 'success': False, 'error': 'Sin archivo de audio'}

        name = getattr(uploaded_file, 'name', '') or 'audio.webm'
        suffix = os.path.splitext(name)[1] or '.webm'

        try:
            size = 0
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                for chunk in uploaded_file.chunks():
                    tmp.write(chunk)
                    size += len(chunk)
                tmp_path = tmp.name
            if size < MIN_AUDIO_BYTES:
                return {
                    'transcription': '',
                    'success': False,
                    'error': 'Audio vacío o muy bajo. Habla más fuerte y al menos 2 segundos.',
                }
            return self.transcribe(tmp_path, language=language)
        except Exception as e:
            return {'transcription': '', 'success': False, 'error': str(e)}
        finally:
            try:
                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass
