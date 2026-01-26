from rest_framework.permissions import DjangoModelPermissions, BasePermission


class AdminOrModelPermissions(DjangoModelPermissions):
    """
    Admin users have full access. Other users must have model permissions
    assigned by an admin (add/change/delete/view).
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_admin', False):
            return True
        return super().has_permission(request, view)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if getattr(user, 'is_admin', False):
            return True
        return super().has_object_permission(request, view, obj)


class HasPermission(BasePermission):
    """
    Custom permission to check if user has specific permission through their role.
    Usage in view: permission_classes = [HasPermission]
    Set required_permission attribute on view or action.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        
        # Admins always have permission
        if getattr(user, 'is_admin', False):
            return True
        
        # Get required permission from view
        required_permission = getattr(view, 'required_permission', None)
        if not required_permission:
            # If no specific permission is required, allow access
            return True
        
        # Check if user's role has the required permission
        if user.role:
            user_permissions = user.role.permissions.values_list('codename', flat=True)
            return required_permission in user_permissions
        
        return False
