from rest_framework.permissions import DjangoModelPermissions


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
