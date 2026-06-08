from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """
    Permite acceso solo a usuarios con rol admin.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


class IsWorkshopOwner(BasePermission):
    """
    Permite acceso solo a usuarios con rol workshop_owner.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'workshop_owner'


class IsClient(BasePermission):
    """
    Permite acceso solo a usuarios con rol client.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'client'


class IsTechnician(BasePermission):
    """Usuario con rol técnico (app móvil de campo)."""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == 'technician'
            and hasattr(request.user, 'technician_profile')
            and request.user.technician_profile is not None
        )


class IsAdminOrWorkshopOwner(BasePermission):
    """
    Permite acceso a admins o dueños de taller.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['admin', 'workshop_owner']
