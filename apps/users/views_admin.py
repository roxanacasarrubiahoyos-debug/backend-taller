from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.users.models import User
from apps.users.serializers import UserSerializer
from apps.users.permissions import IsAdmin


class UserAdminViewSet(viewsets.ModelViewSet):
    """CRUD de usuarios (solo admin)"""
    queryset = User.objects.all().order_by('-created_at')
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ['role', 'is_active', 'is_verified']
    search_fields = ['username', 'email', 'first_name', 'last_name']

    @action(detail=True, methods=['patch'])
    def toggle_active(self, request, pk=None):
        """Activar/desactivar usuario"""
        user = self.get_object()
        user.is_active = not user.is_active
        user.save()
        return Response({
            'message': f'Usuario {"activado" if user.is_active else "desactivado"}',
            'is_active': user.is_active
        })

    @action(detail=False, methods=['get'])
    def push_tokens(self, request):
        """
        Listar todos los usuarios con token FCM registrado.
        Útil para debugging de notificaciones push.
        GET /api/admin-api/users/push-tokens/
        """
        users_with_tokens = User.objects.filter(
            fcm_token__isnull=False
        ).exclude(fcm_token='').order_by('-updated_at')

        data = []
        for user in users_with_tokens:
            token_type = 'unknown'
            if user.fcm_token.startswith('ExponentPushToken[') or user.fcm_token.startswith('ExpoPushToken'):
                token_type = 'expo'
            elif len(user.fcm_token) > 100:
                token_type = 'fcm_native'

            data.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.get_full_name(),
                'role': user.role,
                'token_type': token_type,
                'token_preview': user.fcm_token[:50] + '...' if len(user.fcm_token) > 50 else user.fcm_token,
                'token_full': user.fcm_token,
                'updated_at': user.updated_at,
            })

        return Response({
            'count': len(data),
            'users': data
        })

    @action(detail=False, methods=['post'])
    def test_push_broadcast(self, request):
        """
        Enviar notificación de prueba a todos los usuarios con token FCM.
        POST /api/admin-api/users/test-push-broadcast/
        Body: { "title": "...", "body": "..." }
        """
        title = request.data.get('title', 'Prueba broadcast')
        body = request.data.get('body', 'Mensaje de prueba desde administración')

        users_with_tokens = User.objects.filter(
            fcm_token__isnull=False
        ).exclude(fcm_token='')

        if not users_with_tokens.exists():
            return Response({
                'error': 'No hay usuarios con token FCM registrado'
            }, status=status.HTTP_400_BAD_REQUEST)

        from apps.notifications.firebase_service import FirebaseService
        firebase = FirebaseService()

        success_count = 0
        error_count = 0
        results = []

        for user in users_with_tokens:
            try:
                result = firebase.send_notification(
                    token=user.fcm_token,
                    title=title,
                    body=body,
                    data={
                        'type': 'admin_broadcast',
                        'user_id': str(user.id)
                    }
                )
                if result:
                    success_count += 1
                    results.append({
                        'user': user.username,
                        'status': 'success'
                    })
                else:
                    error_count += 1
                    results.append({
                        'user': user.username,
                        'status': 'error'
                    })
            except Exception as e:
                error_count += 1
                results.append({
                    'user': user.username,
                    'status': 'exception',
                    'error': str(e)
                })

        return Response({
            'message': f'Broadcast enviado a {users_with_tokens.count()} usuarios',
            'success': success_count,
            'errors': error_count,
            'details': results
        })
