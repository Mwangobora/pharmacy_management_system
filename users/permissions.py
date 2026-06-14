from rest_framework.permissions import BasePermission


class RBACPermissionMixin:
    required_permissions = {}
    permission_mode = 'all'

    def get_required_permissions(self):
        if isinstance(self.required_permissions, dict):
            return self.required_permissions.get(getattr(self, 'action', ''), [])
        return self.required_permissions or []

    def get_permission_mode(self):
        return getattr(self, 'permission_mode', 'all')


class HasViewPermissions(BasePermission):
    message = 'You do not have permission to perform this action.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        required_permissions = list(view.get_required_permissions()) if hasattr(view, 'get_required_permissions') else []
        if not required_permissions:
            return True

        effective_permissions = set(user.get_effective_permissions())
        if getattr(view, 'get_permission_mode', lambda: 'all')() == 'any':
            return any(permission in effective_permissions for permission in required_permissions)
        return all(permission in effective_permissions for permission in required_permissions)


class HasPermission(BasePermission):
    def __init__(self, permission):
        self.permission = permission

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or user.has_permission(self.permission)))


class HasAnyPermission(BasePermission):
    def __init__(self, permissions):
        self.permissions = permissions

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        effective_permissions = set(user.get_effective_permissions())
        return any(permission in effective_permissions for permission in self.permissions)


class HasAllPermissions(BasePermission):
    def __init__(self, permissions):
        self.permissions = permissions

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        effective_permissions = set(user.get_effective_permissions())
        return all(permission in effective_permissions for permission in self.permissions)
