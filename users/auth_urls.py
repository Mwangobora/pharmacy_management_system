from rest_framework.routers import DefaultRouter
from .views import PermissionViewSet, RoleViewSet

router = DefaultRouter()
router.register(r'roles', RoleViewSet, basename='role')
router.register(r'permissions', PermissionViewSet, basename='permission')

urlpatterns = router.urls
