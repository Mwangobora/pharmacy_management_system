from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Sum, Count, F
from django.utils import timezone

from .models import Supplier, Purchase, PurchaseItem
from .serializers import (
    SupplierSerializer, SupplierListSerializer,
    PurchaseListSerializer, PurchaseDetailSerializer,
    PurchaseItemSerializer, CreatePurchaseSerializer,
    ReceiveItemsSerializer
)
from inventory.models import StockTransaction
from services.supplier_service import SupplierService, PurchaseService


class SupplierViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Supplier management
    
    Endpoints:
    - GET /suppliers/ - List all suppliers
    - POST /suppliers/ - Create supplier
    - GET /suppliers/{id}/ - Get supplier details
    - PUT/PATCH /suppliers/{id}/ - Update supplier
    - DELETE /suppliers/{id}/ - Soft delete supplier
    - GET /suppliers/{id}/purchases/ - Get supplier purchase history
    - GET /suppliers/{id}/medicines/ - Get medicines from supplier
    """
    
    queryset = Supplier.objects.all()
    # permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['name', 'contact_person', 'phone', 'email', 'tax_id']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        """Use different serializers for list vs detail"""
        if self.action == 'list':
            return SupplierListSerializer
        return SupplierSerializer
    
    def get_queryset(self):
        """Filter active suppliers by default"""
        queryset = super().get_queryset()
        
        is_active = self.request.query_params.get('is_active', 'true')
        if is_active.lower() == 'true':
            queryset = queryset.filter(is_active=True)
        
        return queryset
    
    def perform_destroy(self, instance):
        """Soft delete: mark as inactive"""
        instance.is_active = False
        instance.save()
    
    @action(detail=True, methods=['get'])
    def purchases(self, request, pk=None):
        """Get all purchases from this supplier"""
        supplier = self.get_object()
        purchases = supplier.purchases.all().order_by('-purchase_date')
        
        serializer = PurchaseListSerializer(purchases, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def medicines(self, request, pk=None):
        """Get all medicines supplied by this supplier"""
        from inventory.serializers import MedicineListSerializer
        
        supplier = self.get_object()
        medicines = supplier.medicines.filter(is_active=True)
        
        serializer = MedicineListSerializer(medicines, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """
        Get supplier statistics
        
        Returns:
        - Total purchases
        - Total amount spent
        - Pending payments
        - Active medicines
        """
        supplier = self.get_object()
        stats = SupplierService.get_supplier_stats(supplier)
        return Response(stats)


class PurchaseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Purchase management with advanced features
    
    Endpoints:
    - GET /purchases/ - List all purchases
    - POST /purchases/ - Create purchase
    - GET /purchases/{id}/ - Get purchase details
    - PUT/PATCH /purchases/{id}/ - Update purchase
    - DELETE /purchases/{id}/ - Delete purchase
    - POST /purchases/create-with-items/ - Create purchase with items
    - POST /purchases/{id}/receive-items/ - Mark items as received
    - PATCH /purchases/{id}/update-payment-status/ - Update payment status
    - GET /purchases/pending-payments/ - Get purchases with pending payments
    """
    
    queryset = Purchase.objects.select_related('supplier', 'created_by').prefetch_related('items').all()
    # permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['supplier', 'payment_status']
    search_fields = ['invoice_number', 'supplier__name']
    ordering_fields = ['purchase_date', 'net_amount', 'created_at']
    ordering = ['-purchase_date']
    
    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action == 'list':
            return PurchaseListSerializer
        elif self.action == 'create_with_items':
            return CreatePurchaseSerializer
        return PurchaseDetailSerializer
    
    def get_queryset(self):
        """Custom filtering by date range and payment status"""
        queryset = super().get_queryset()
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(purchase_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(purchase_date__lte=end_date)
        
        return queryset
    
    def perform_create(self, serializer):
        """Set created_by to current user"""
        serializer.save(created_by=self.request.user)
    
    @action(detail=False, methods=['post'])
    def create_with_items(self, request):
        """
        Create purchase with items in one transaction
        
        POST /purchases/create-with-items/
        Body: {
            "supplier": 1,
            "invoice_number": "INV-001",
            "purchase_date": "2025-01-15",
            "tax_amount": "1000.00",
            "discount_amount": "500.00",
            "notes": "First order",
            "items": [
                {
                    "medicine": 1,
                    "quantity": 100,
                    "unit_price": "50.00",
                    "discount_percent": "5",
                    "tax_percent": "18"
                }
            ]
        }
        """
        serializer = CreatePurchaseSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                purchase = PurchaseService.create_purchase_with_items(request.user, serializer.validated_data)
            except serializers.ValidationError as e:
                return Response({'error': e.detail}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            response_serializer = PurchaseDetailSerializer(purchase)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def receive_items(self, request, pk=None):
        purchase = self.get_object()
        serializer = ReceiveItemsSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                result = PurchaseService.receive_items(purchase, serializer.validated_data['items'], request.user)
            except serializers.ValidationError as e:
                return Response({'error': e.detail}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            return Response({
                'message': 'Items received successfully',
                **result
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['patch'])
    def update_payment_status(self, request, pk=None):
        purchase = self.get_object()
        new_status = request.data.get('payment_status')
        
        if new_status not in dict(Purchase.PAYMENT_STATUS_CHOICES).keys():
            return Response(
                {'error': 'Invalid payment status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        purchase.payment_status = new_status
        purchase.save()
        
        serializer = self.get_serializer(purchase)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def pending_payments(self, request):
        """Get all purchases with pending or partial payments"""
        purchases = self.get_queryset().filter(
            payment_status__in=['pending', 'partial']
        ).order_by('purchase_date')
        
        serializer = self.get_serializer(purchases, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        queryset = self.get_queryset()
        stats = PurchaseService.get_purchase_dashboard_stats(queryset)
        return Response(stats)
class PurchaseItemViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PurchaseItem.objects.select_related('purchase', 'medicine').all()
    serializer_class = PurchaseItemSerializer
    # permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['purchase', 'medicine']
