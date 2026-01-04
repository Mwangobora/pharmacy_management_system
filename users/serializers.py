from rest_framework import serializers
from .models import User
from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role', 'is_active', 'is_staff', 'created_at']
        read_only_fields = ['id', 'is_active', 'is_staff', 'created_at']


class UserCreateSerializer(DjoserUserCreateSerializer):
    class Meta(DjoserUserCreateSerializer.Meta):
        model = User
        fields = ('id', 'username', 'email', 'password', 'role')
        extra_kwargs = {'password': {'write_only': True}}
