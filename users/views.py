from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import User
from .serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user management.
    Includes auth endpoints for register, login, logout, password reset.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    
    def get_permissions(self):
        """
        Allow anonymous access to auth info and list endpoints.
        Require authentication for other operations.
        """
        if self.action in ['auth_info', 'list']:
            return [AllowAny()]
        return [IsAuthenticated()]
    
    @action(detail=False, methods=['get'], name='Auth Info', permission_classes=[AllowAny])
    def auth_info(self, request):
        """List all available auth endpoints"""
        return Response({
            'message': 'Authentication Endpoints',
            'endpoints': {
                'register': '/api/auth/users/',
                'login': '/api/auth/jwt/create/',
                'logout': '/api/auth/logout/',
                'refresh_token': '/api/auth/jwt/refresh/',
                'reset_password': '/api/auth/users/reset_password/',
                'reset_password_confirm': '/api/auth/users/reset_password_confirm/',
                'current_user': '/api/auth/users/me/',
            }
        })
