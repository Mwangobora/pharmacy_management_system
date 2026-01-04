"""
URL configuration for sales module.

Includes endpoints for:
- Customers (list, create, retrieve, update, delete, purchase history, loyalty)
- Sales (list, create, retrieve, daily summary, top selling medicines)
- Payments (read-only history)
"""
from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, SaleViewSet, PaymentViewSet

# Router for the sales module
router = DefaultRouter()
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'sales', SaleViewSet, basename='sale')
router.register(r'payments', PaymentViewSet, basename='payment')

urlpatterns = router.urls
