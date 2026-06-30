from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import PermissionProfile, Role, User
from .rbac import (
    build_permission_codename,
    bump_authorization_versions,
    get_access_content_type,
    set_role_permissions,
    set_user_direct_permissions,
    set_user_roles,
    users_for_permission,
)


class PermissionSerializer(serializers.ModelSerializer):
    codename = serializers.CharField(required=False, allow_blank=False)
    module = serializers.CharField(source='profile.module', required=False)
    resource = serializers.CharField(source='profile.resource', required=False)
    action = serializers.CharField(source='profile.action', required=False)
    description = serializers.CharField(source='profile.description', required=False, allow_blank=True)
    is_active = serializers.BooleanField(source='profile.is_active', required=False)
    is_system = serializers.BooleanField(source='profile.is_system', required=False)
    is_assignable = serializers.BooleanField(source='profile.is_assignable', required=False)
    content_type = serializers.IntegerField(source='content_type_id', required=False)

    class Meta:
        model = Permission
        fields = [
            'id',
            'name',
            'codename',
            'content_type',
            'module',
            'resource',
            'action',
            'description',
            'is_active',
            'is_system',
            'is_assignable',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        profile_data = attrs.get('profile', {})
        instance = getattr(self, 'instance', None)

        module = profile_data.get('module', getattr(getattr(instance, 'profile', None), 'module', None))
        resource = profile_data.get('resource', getattr(getattr(instance, 'profile', None), 'resource', None))
        action = profile_data.get('action', getattr(getattr(instance, 'profile', None), 'action', None))
        codename = attrs.get('codename') or getattr(instance, 'codename', None)
        content_type_id = attrs.get('content_type_id') or getattr(instance, 'content_type_id', None)

        if not codename:
            if not all([module, resource, action]):
                raise serializers.ValidationError({
                    'codename': 'Provide a codename or module, resource, and action so one can be generated.'
                })
            attrs['codename'] = build_permission_codename(module, resource, action)
            codename = attrs['codename']

        if not all([module, resource, action]):
            raise serializers.ValidationError({
                'module': 'Module, resource, and action are required for every permission definition.'
            })

        if content_type_id:
            try:
                ContentType.objects.get(id=content_type_id)
            except ContentType.DoesNotExist as exc:
                raise serializers.ValidationError({'content_type': 'The selected content type does not exist.'}) from exc

        queryset = Permission.objects.filter(
            content_type_id=content_type_id or get_access_content_type().id,
            codename=codename,
        )
        if instance:
            queryset = queryset.exclude(pk=instance.pk)
        if queryset.exists():
            raise serializers.ValidationError({'codename': 'A permission with this codename already exists for the selected content type.'})

        return attrs

    def create(self, validated_data):
        profile_data = validated_data.pop('profile', {})
        content_type_id = validated_data.pop('content_type_id', None)
        content_type = get_access_content_type(content_type_id)

        with transaction.atomic():
            permission = Permission.objects.create(content_type=content_type, **validated_data)
            PermissionProfile.objects.create(
                permission=permission,
                module=profile_data['module'],
                resource=profile_data['resource'],
                action=profile_data['action'],
                description=profile_data.get('description', ''),
                is_active=profile_data.get('is_active', True),
                is_system=profile_data.get('is_system', False),
                is_assignable=profile_data.get('is_assignable', True),
            )
        return permission

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {})
        content_type_id = validated_data.pop('content_type_id', None)
        affected_users_before = users_for_permission(instance)

        with transaction.atomic():
            if content_type_id:
                instance.content_type = get_access_content_type(content_type_id)
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            profile, _ = PermissionProfile.objects.get_or_create(permission=instance)
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()

            bump_authorization_versions(affected_users_before | users_for_permission(instance))

        return instance


class RoleSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name', 'code']


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Permission.objects.filter(profile__isnull=False, profile__is_assignable=True),
        required=False,
    )
    permissions_detail = PermissionSerializer(source='permissions', many=True, read_only=True)
    permission_count = serializers.SerializerMethodField()
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            'id',
            'name',
            'code',
            'description',
            'permissions',
            'permissions_detail',
            'permission_count',
            'user_count',
            'is_active',
            'is_system',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'is_system', 'created_at', 'updated_at', 'permission_count', 'user_count']

    def get_permission_count(self, obj):
        return obj.permissions.count()

    def get_user_count(self, obj):
        return obj.user_role_assignments.filter(is_active=True).count()

    def create(self, validated_data):
        permissions = validated_data.pop('permissions', [])
        role = Role.objects.create(**validated_data)
        if permissions:
            set_role_permissions(
                role,
                permissions,
                actor=self.context.get('request').user if self.context.get('request') else None,
                log_action=False,
            )
        return role

    def update(self, instance, validated_data):
        permissions = validated_data.pop('permissions', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if permissions is not None:
            set_role_permissions(
                instance,
                permissions,
                actor=self.context.get('request').user if self.context.get('request') else None,
                log_action=False,
            )
        return instance


class RolePermissionAssignmentSerializer(serializers.Serializer):
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
    )
    permission_codenames = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )

    def validate(self, attrs):
        permission_ids = attrs.get('permission_ids', [])
        permission_codenames = attrs.get('permission_codenames', [])
        if not permission_ids and not permission_codenames:
            attrs['permissions'] = []
            return attrs

        permissions = list(Permission.objects.filter(profile__isnull=False, profile__is_assignable=True).filter(
            Q(id__in=permission_ids) | Q(codename__in=permission_codenames)
        ).distinct())
        found_ids = {permission.id for permission in permissions}
        found_codenames = {permission.codename for permission in permissions}
        if set(permission_ids) - found_ids or set(permission_codenames) - found_codenames:
            raise serializers.ValidationError({
                'detail': 'One or more permissions are invalid or cannot be assigned.'
            })

        attrs['permissions'] = permissions
        return attrs


class UserRoleAssignmentSerializer(serializers.Serializer):
    role_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
    )
    role_codes = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )

    def validate(self, attrs):
        role_ids = attrs.get('role_ids', [])
        role_codes = attrs.get('role_codes', [])
        if not role_ids and not role_codes:
            attrs['roles'] = []
            return attrs

        roles = list(Role.objects.filter(is_active=True).filter(
            Q(id__in=role_ids) | Q(code__in=role_codes)
        ).distinct())
        found_ids = {role.id for role in roles}
        found_codes = {role.code for role in roles}
        if set(role_ids) - found_ids or set(role_codes) - found_codes:
            raise serializers.ValidationError({
                'detail': 'One or more roles are invalid or inactive.'
            })

        attrs['roles'] = roles
        return attrs


class UserPermissionAssignmentSerializer(serializers.Serializer):
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
    )
    permission_codenames = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )

    def validate(self, attrs):
        permission_ids = attrs.get('permission_ids', [])
        permission_codenames = attrs.get('permission_codenames', [])
        if not permission_ids and not permission_codenames:
            attrs['permissions'] = []
            return attrs

        permissions = list(Permission.objects.filter(profile__isnull=False, profile__is_assignable=True, profile__is_active=True).filter(
            Q(id__in=permission_ids) | Q(codename__in=permission_codenames)
        ).distinct())
        found_ids = {permission.id for permission in permissions}
        found_codenames = {permission.codename for permission in permissions}
        if set(permission_ids) - found_ids or set(permission_codenames) - found_codenames:
            raise serializers.ValidationError({
                'detail': 'One or more permissions are invalid, inactive, or cannot be assigned.'
            })

        attrs['permissions'] = permissions
        return attrs


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='primary_role.name', read_only=True)
    role_detail = RoleSerializer(source='primary_role', read_only=True)
    roles = serializers.PrimaryKeyRelatedField(many=True, queryset=Role.objects.filter(is_active=True), required=False)
    roles_detail = serializers.SerializerMethodField()
    direct_permissions = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Permission.objects.filter(profile__isnull=False, profile__is_assignable=True, profile__is_active=True),
        required=False,
    )
    direct_permissions_detail = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'password',
            'role',
            'role_name',
            'role_detail',
            'roles',
            'roles_detail',
            'direct_permissions',
            'direct_permissions_detail',
            'permissions',
            'authorization_version',
            'is_active',
            'is_staff',
            'created_at',
        ]
        read_only_fields = ['id', 'role_name', 'role_detail', 'authorization_version', 'is_staff', 'created_at']

    def get_roles_detail(self, obj):
        return RoleSummarySerializer(obj.get_active_roles(), many=True).data

    def get_direct_permissions_detail(self, obj):
        return PermissionSerializer(obj.get_active_direct_permissions(), many=True).data

    def get_permissions(self, obj):
        return obj.get_effective_permissions()

    def validate_roles(self, value):
        inactive_roles = [role.name for role in value if not role.is_active]
        if inactive_roles:
            raise serializers.ValidationError(f'Inactive roles cannot be assigned: {", ".join(inactive_roles)}')
        return value

    def validate(self, attrs):
        if attrs.get('password') == '':
            attrs.pop('password')
        return attrs

    def create(self, validated_data):
        roles = validated_data.pop('roles', [])
        direct_permissions = validated_data.pop('direct_permissions', [])
        password = validated_data.pop('password', None)

        with transaction.atomic():
            user = User(**validated_data)
            if password:
                user.set_password(password)
            else:
                user.set_unusable_password()
            user.save()
            set_user_roles(user, roles)
            set_user_direct_permissions(user, direct_permissions)
        return user

    def update(self, instance, validated_data):
        roles = validated_data.pop('roles', None)
        direct_permissions = validated_data.pop('direct_permissions', None)
        password = validated_data.pop('password', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()

        if roles is not None:
            set_user_roles(instance, roles, actor=self.context.get('request').user if self.context.get('request') else None)
        if direct_permissions is not None:
            set_user_direct_permissions(instance, direct_permissions, actor=self.context.get('request').user if self.context.get('request') else None)
        return instance


class UserAccessSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    inherited_permissions = serializers.SerializerMethodField()
    direct_permissions = serializers.SerializerMethodField()
    effective_permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'roles', 'inherited_permissions', 'direct_permissions', 'effective_permissions', 'authorization_version']

    def get_roles(self, obj):
        return RoleSerializer(obj.get_active_roles(), many=True).data

    def get_inherited_permissions(self, obj):
        permissions = Permission.objects.filter(
            roles__user_role_assignments__user=obj,
            roles__user_role_assignments__is_active=True,
        ).filter(
            Q(profile__isnull=True) | Q(profile__is_active=True)
        ).distinct()
        return PermissionSerializer(permissions, many=True).data

    def get_direct_permissions(self, obj):
        return PermissionSerializer(obj.get_active_direct_permissions(), many=True).data

    def get_effective_permissions(self, obj):
        return obj.get_effective_permissions()


class AuthMeSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'full_name',
            'is_active',
            'roles',
            'permissions',
            'authorization_version',
            'is_staff',
            'created_at',
        ]
        read_only_fields = ['id', 'roles', 'permissions', 'authorization_version', 'is_staff', 'created_at']

    def get_full_name(self, obj):
        return obj.username

    def get_roles(self, obj):
        return RoleSummarySerializer(obj.get_active_roles(), many=True).data

    def get_permissions(self, obj):
        return obj.get_effective_permissions()


class UserCreateSerializer(DjoserUserCreateSerializer):
    class Meta(DjoserUserCreateSerializer.Meta):
        model = User
        fields = ('id', 'username', 'email', 'password')
        extra_kwargs = {'password': {'write_only': True}}


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = AuthMeSerializer(self.user).data
        return data
