"""
URL configuration for pharmacy project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView
from djoser.views import UserViewSet as DjoserUserViewSet
from inventory.views import CategoryViewSet, MedicineViewSet, StockTransactionViewSet
from suppliers.views import SupplierViewSet, PurchaseViewSet, PurchaseItemViewSet
from sales.views import CustomerViewSet as SalesCustomerViewSet, SaleViewSet, PaymentViewSet

# Create a single root router
router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'medicines', MedicineViewSet, basename='medicine')
router.register(r'stock-transactions', StockTransactionViewSet, basename='stock-transaction')
router.register(r'suppliers', SupplierViewSet, basename='supplier')
router.register(r'purchases', PurchaseViewSet, basename='purchase')
router.register(r'purchase-items', PurchaseItemViewSet, basename='purchase-item')
router.register(r'customers', SalesCustomerViewSet, basename='customer')
router.register(r'sales', SaleViewSet, basename='sale')
router.register(r'payments', PaymentViewSet, basename='payment')

urlpatterns = [
    path('', RedirectView.as_view(url='api/', permanent=False)),
    path('admin/', admin.site.urls),
    path('api/auth/register/', DjoserUserViewSet.as_view({'post': 'create'}), name='register'),
    path('api/auth/login/', TokenObtainPairView.as_view(), name='login'),
    path('api/', include(router.urls)),
    path('api/users/', include('users.urls')),
    path('api/auth/', include('users.auth_urls')),
    # Authentication endpoints (Djoser + JWT)
    path('api/auth/', include('djoser.urls')),
    path('api/auth/', include('djoser.urls.jwt')),
] 

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
