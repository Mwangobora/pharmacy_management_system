from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, MedicineViewSet, StockTransactionViewSet

app_name = 'inventory'

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'medicines', MedicineViewSet, basename='medicine')
router.register(r'stock-transactions', StockTransactionViewSet, basename='stock-transaction')

urlpatterns = [
    path('', include(router.urls)),
]
