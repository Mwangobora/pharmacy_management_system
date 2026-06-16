from django.contrib.auth.models import Permission
from django.db import transaction
from django.db.models import Count, Q
from rest_framework import filters, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Role, User
from .permissions import HasViewPermissions, RBACPermissionMixin
from .rbac import log_access_event, set_user_direct_permissions, set_user_roles, sync_default_roles, sync_existing_role_assignments, sync_permissions
from .serializers import AuthMeSerializer, PermissionSerializer, RoleSerializer, UserAccessSerializer, UserSerializer


class AuthMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(AuthMeSerializer(request.user).data)

    def patch(self, request):
        serializer = AuthMeSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AuthMeSerializer(request.user).data)


class UserViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = User.objects.prefetch_related(
        'role_assignments__role__permissions__profile',
        'direct_permission_assignments__permission__profile',
        'user_permissions__profile',
        'role__permissions__profile',
    ).all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, HasViewPermissions]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'email']
    ordering_fields = ['username', 'email', 'created_at']
    ordering = ['username']
    required_permissions = {
        'list': ['access.user.view'],
        'retrieve': ['access.user.view'],
        'create': ['access.user.create'],
        'update': ['access.user.update'],
        'partial_update': ['access.user.update'],
        'destroy': ['access.user.delete'],
        'access': ['access.user.view'],
        'set_roles': ['access.user.assign_roles'],
        'set_permissions': ['access.user.assign_permissions'],
    }

    def get_permissions(self):
        if self.action == 'auth_info':
            return [AllowAny()]
        return super().get_permissions()

    @action(detail=False, methods=['get'], name='Auth Info', permission_classes=[AllowAny])
    def auth_info(self, request):
        return Response({
            'message': 'Authentication Endpoints',
            'endpoints': {
                'register': '/api/auth/register/',
                'login': '/api/auth/login/',
                'refresh_token': '/api/auth/jwt/refresh/',
                'me': '/api/auth/me/',
                'users': '/api/users/',
                'roles': '/api/auth/roles/',
                'permissions': '/api/auth/permissions/',
            }
        })

    @action(detail=True, methods=['get'], url_path='access')
    def access(self, request, pk=None):
        user = self.get_object()
        return Response(UserAccessSerializer(user).data)

    @action(detail=True, methods=['put'], url_path='roles')
    def set_roles(self, request, pk=None):
        user = self.get_object()
        role_ids = request.data.get('role_ids', [])
        roles = list(Role.objects.filter(id__in=role_ids, is_active=True))
        if len(roles) != len(set(role_ids)):
            raise serializers.ValidationError({'role_ids': 'One or more roles are invalid or inactive.'})
        set_user_roles(user, roles, actor=request.user)
        return Response(UserAccessSerializer(user).data)

    @action(detail=True, methods=['put'], url_path='permissions')
    def set_permissions(self, request, pk=None):
        user = self.get_object()
        permission_ids = request.data.get('permission_ids', [])
        permissions = list(Permission.objects.filter(id__in=permission_ids))
        if len(permissions) != len(set(permission_ids)):
            raise serializers.ValidationError({'permission_ids': 'One or more permissions are invalid.'})
        set_user_direct_permissions(user, permissions, actor=request.user)
        return Response(UserAccessSerializer(user).data)


class RoleViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = Role.objects.prefetch_related('permissions__profile').annotate(
        permission_count=Count('permissions', distinct=True),
        user_count=Count('user_role_assignments', filter=Q(user_role_assignments__is_active=True), distinct=True),
    )
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, HasViewPermissions]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'code', 'created_at', 'updated_at']
    ordering = ['name']
    required_permissions = {
        'list': ['access.role.view'],
        'retrieve': ['access.role.view'],
        'create': ['access.role.create'],
        'update': ['access.role.update'],
        'partial_update': ['access.role.update'],
        'destroy': ['access.role.delete'],
    }

    def perform_create(self, serializer):
        role = serializer.save(created_by=self.request.user, updated_by=self.request.user)
        log_access_event(actor=self.request.user, action='role.created', target_role=role, after_state=RoleSerializer(role).data)

    def perform_update(self, serializer):
        role = serializer.save(updated_by=self.request.user)
        log_access_event(actor=self.request.user, action='role.updated', target_role=role, after_state=RoleSerializer(role).data)

    def perform_destroy(self, instance):
        if instance.is_system:
            raise serializers.ValidationError({'detail': 'System roles cannot be deleted.'})
        log_access_event(actor=self.request.user, action='role.deleted', target_role=instance, before_state=RoleSerializer(instance).data)
        instance.delete()


class PermissionViewSet(RBACPermissionMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Permission.objects.select_related('profile').filter(profile__isnull=False)
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated, HasViewPermissions]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'codename', 'profile__module', 'profile__resource', 'profile__action']
    ordering_fields = ['name', 'codename', 'profile__module', 'profile__resource', 'profile__action']
    ordering = ['profile__module', 'profile__resource', 'profile__action']
    required_permissions = {
        'list': ['access.permission.view'],
        'retrieve': ['access.permission.view'],
    }


class PermissionSyncView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_superuser and not request.user.has_permission('access.role.assign_permissions'):
            return Response({'detail': 'You do not have permission to synchronize access configuration.'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            sync_permissions()
            sync_default_roles()
            sync_existing_role_assignments()

        return Response({'detail': 'Access configuration synchronized successfully.'})
