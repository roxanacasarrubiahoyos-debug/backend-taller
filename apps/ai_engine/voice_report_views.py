from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.ai_engine.voice_query_service import VoiceQueryService
from apps.users.permissions import IsAdmin, IsClient, IsTechnician, IsWorkshopOwner
from apps.workshops.models import Workshop


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([IsAdmin])
def admin_voice_query(request):
    """
    El admin habla (audio) o envía texto; se interpreta la solicitud y devuelve preview del reporte.
    Body multipart: audio=<file>  o  JSON: { "text": "..." }
    """
    audio = request.FILES.get('audio')
    text = request.data.get('text') if hasattr(request, 'data') else None
    if not audio and not (text and str(text).strip()):
        return Response(
            {'error': 'Envía un archivo de audio (campo audio) o texto con tu solicitud.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = VoiceQueryService().process_admin(audio_file=audio, text=text)
    if not result.get('ok'):
        return Response(
            {'error': result.get('error', 'Error procesando solicitud')},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({
        'audience': 'admin',
        'transcript': result['transcript'],
        'intent_summary': result['intent_summary'],
        'filters': result['filters'],
        'report': result['report'],
    })


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([IsWorkshopOwner])
def workshop_voice_query(request):
    """Dueño de taller pide reporte por voz; solo datos de su taller."""
    try:
        workshop = Workshop.objects.get(owner=request.user.owner_profile)
    except Workshop.DoesNotExist:
        return Response({'error': 'No tienes un taller registrado'}, status=status.HTTP_404_NOT_FOUND)

    audio = request.FILES.get('audio')
    text = request.data.get('text') if hasattr(request, 'data') else None
    if not audio and not (text and str(text).strip()):
        return Response(
            {'error': 'Envía un archivo de audio (campo audio) o texto con tu solicitud.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = VoiceQueryService().process_workshop(
        workshop=workshop,
        audio_file=audio,
        text=text,
    )
    if not result.get('ok'):
        return Response(
            {'error': result.get('error', 'Error procesando solicitud')},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({
        'audience': 'workshop_owner',
        'transcript': result['transcript'],
        'intent_summary': result['intent_summary'],
        'narrative_summary': result.get('narrative_summary'),
        'filters': result['filters'],
        'report': result['report'],
    })


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([IsClient])
def client_voice_query(request):
    """Cliente móvil: reporte por voz solo de sus solicitudes y pagos."""
    if not hasattr(request.user, 'client_profile') or request.user.client_profile is None:
        return Response({'error': 'Perfil de cliente no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    audio = request.FILES.get('audio')
    text = request.data.get('text') if hasattr(request, 'data') else None
    if not audio and not (text and str(text).strip()):
        return Response(
            {'error': 'Envía un archivo de audio (campo audio) o texto con tu solicitud.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = VoiceQueryService().process_client(
        client_profile=request.user.client_profile,
        audio_file=audio,
        text=text,
    )
    if not result.get('ok'):
        return Response(
            {'error': result.get('error', 'Error procesando solicitud')},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({
        'audience': 'client',
        'transcript': result['transcript'],
        'intent_summary': result['intent_summary'],
        'narrative_summary': result.get('narrative_summary'),
        'filters': result['filters'],
        'report': result['report'],
    })


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([IsTechnician])
def technician_voice_query(request):
    """Técnico móvil: reporte por voz solo de sus órdenes asignadas."""
    tech = request.user.technician_profile

    audio = request.FILES.get('audio')
    text = request.data.get('text') if hasattr(request, 'data') else None
    if not audio and not (text and str(text).strip()):
        return Response(
            {'error': 'Envía un archivo de audio (campo audio) o texto con tu solicitud.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = VoiceQueryService().process_technician(
        technician=tech,
        audio_file=audio,
        text=text,
    )
    if not result.get('ok'):
        return Response(
            {'error': result.get('error', 'Error procesando solicitud')},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({
        'audience': 'technician',
        'transcript': result['transcript'],
        'intent_summary': result['intent_summary'],
        'narrative_summary': result.get('narrative_summary'),
        'filters': result['filters'],
        'report': result['report'],
    })
