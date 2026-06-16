from django.contrib.auth.models import Permission
from django.db import transaction
from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Role, User
from .rbac import set_user_direct_permissions, set_user_roles


class PermissionSerializer(serializers.ModelSerializer):
    module = serializers.CharField(source='profile.module', read_only=True)
    resource = serializers.CharField(source='profile.resource', read_only=True)
    action = serializers.CharField(source='profile.action', read_only=True)
    description = serializers.CharField(source='profile.description', read_only=True)
    is_active = serializers.BooleanField(source='profile.is_active', read_only=True)
    is_system = serializers.BooleanField(source='profile.is_system', read_only=True)

    class Meta:
        model = Permission
        fields = [
            'id',
            'name',
            'codename',
            'module',
            'resource',
            'action',
            'description',
            'is_active',
            'is_system',
        ]
        read_only_fields = fields


class RoleSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name', 'code']


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.PrimaryKeyRelatedField(many=True, queryset=Permission.objects.all(), required=False)
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


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='primary_role.name', read_only=True)
    role_detail = RoleSerializer(source='primary_role', read_only=True)
    roles = serializers.PrimaryKeyRelatedField(many=True, queryset=Role.objects.filter(is_active=True), required=False)
    roles_detail = serializers.SerializerMethodField()
    direct_permissions = serializers.PrimaryKeyRelatedField(many=True, queryset=Permission.objects.all(), required=False)
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
        permissions = Permission.objects.filter(roles__user_role_assignments__user=obj, roles__user_role_assignments__is_active=True).distinct()
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
