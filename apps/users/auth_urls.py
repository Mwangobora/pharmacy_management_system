from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import AuthMeView, PermissionSyncView, PermissionViewSet, RoleViewSet

router = DefaultRouter()
router.register(r'roles', RoleViewSet, basename='role')
router.register(r'permissions', PermissionViewSet, basename='permission')

urlpatterns = [
    path('me/', AuthMeView.as_view(), name='auth-me'),
    path('sync/', PermissionSyncView.as_view(), name='access-sync'),
]

urlpatterns += router.urls
