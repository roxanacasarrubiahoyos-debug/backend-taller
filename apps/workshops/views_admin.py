from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.workshops.models import Workshop
from apps.workshops.serializers import WorkshopSerializer, WorkshopDetailSerializer
from apps.users.permissions import IsAdmin


class WorkshopAdminViewSet(viewsets.ModelViewSet):
    """CRUD de talleres (solo admin)"""
    queryset = Workshop.objects.all().order_by('-created_at')
    serializer_class = WorkshopSerializer
    permission_classes = [IsAdmin]
    filterset_fields = ['is_active', 'is_verified']
    search_fields = ['name', 'address', 'phone', 'email']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return WorkshopDetailSerializer
        return WorkshopSerializer

    @action(detail=True, methods=['patch'])
    def verify(self, request, pk=None):
        """Verificar/aprobar taller"""
        workshop = self.get_object()
        is_verified = request.data.get('is_verified', True)
        workshop.is_verified = is_verified
        workshop.save()

        if is_verified:
            try:
                from apps.notifications.models import NotificationType
                from apps.notifications.web_panel_notify import deliver_to_web_panel_user

                owner_user = workshop.owner.user
                deliver_to_web_panel_user(
                    user=owner_user,
                    title='Taller verificado',
                    body=f'Tu taller "{workshop.name}" fue verificado. Ya podés recibir solicitudes.',
                    notification_type=NotificationType.WORKSHOP_VERIFIED,
                    data={'workshop_id': workshop.id, 'type': 'workshop_verified'},
                    sse_payload={
                        'event': 'workshop_verified',
                        'workshop_id': workshop.id,
                    },
                )
            except Exception:
                pass

        return Response({
            'message': f'Taller {"verificado" if is_verified else "marcado como no verificado"}',
            'is_verified': workshop.is_verified
        })

    @action(detail=True, methods=['patch'])
    def toggle_active(self, request, pk=None):
        """Activar/desactivar taller"""
        workshop = self.get_object()
        workshop.is_active = not workshop.is_active
        workshop.save()
        return Response({
            'message': f'Taller {"activado" if workshop.is_active else "desactivado"}',
            'is_active': workshop.is_active
        })
