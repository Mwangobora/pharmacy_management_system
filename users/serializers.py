from rest_framework import serializers
from django.contrib.auth.models import Permission
from .models import Role, User
from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer


class PermissionSerializer(serializers.ModelSerializer):
    content_type_label = serializers.CharField(source='content_type.app_label', read_only=True)
    content_type_model = serializers.CharField(source='content_type.model', read_only=True)

    class Meta:
        model = Permission
        fields = ['id', 'name', 'codename', 'content_type', 'content_type_label', 'content_type_model']
        read_only_fields = ['id']


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Permission.objects.all(),
        required=False,
    )
    permissions_detail = PermissionSerializer(source='permissions', many=True, read_only=True)

    class Meta:
        model = Role
        fields = ['id', 'name', 'permissions', 'permissions_detail', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name', read_only=True)
    role_detail = RoleSerializer(source='role', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role', 'role_name', 'role_detail', 'is_active', 'is_staff', 'created_at']
        read_only_fields = ['id', 'is_active', 'is_staff', 'created_at']


class UserCreateSerializer(DjoserUserCreateSerializer):
    class Meta(DjoserUserCreateSerializer.Meta):
        model = User
        fields = ('id', 'username', 'email', 'password')
        extra_kwargs = {'password': {'write_only': True}}
