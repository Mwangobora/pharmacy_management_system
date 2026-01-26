from rest_framework import serializers
from django.contrib.auth.models import Permission
from .models import Role, User
from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


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
    permissions = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'role', 'role_name', 'role_detail', 'permissions', 'is_active', 'is_staff', 'created_at']
        read_only_fields = ['id', 'is_active', 'is_staff', 'created_at']

    def get_permissions(self, obj):
        """Return list of permission codenames assigned to the user's role"""
        if obj.role:
            return list(obj.role.permissions.values_list('codename', flat=True))
        return []

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class UserCreateSerializer(DjoserUserCreateSerializer):
    class Meta(DjoserUserCreateSerializer.Meta):
        model = User
        fields = ('id', 'username', 'email', 'password')
        extra_kwargs = {'password': {'write_only': True}}


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT serializer to include user info and permissions"""

    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Add user information to the response
        user_serializer = UserSerializer(self.user)
        data['user'] = user_serializer.data
        
        return data
