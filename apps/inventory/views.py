from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import F, Sum, Count, Max
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

from .models import Category, Medicine, StockTransaction
from .serializers import (
    CategorySerializer, MedicineListSerializer, MedicineDetailSerializer,
    StockTransactionSerializer, StockAdjustmentSerializer
)
from .services import InventoryService
from apps.users.permissions import HasViewPermissions, RBACPermissionMixin


class CategoryViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    """
    ViewSet for Category management
    
    list: Get all categories
    retrieve: Get single category
    create: Create new category
    update: Update category
    destroy: Delete category (soft delete via is_active)
    """
    
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, HasViewPermissions]
    required_permissions = {
        'list': ['inventory.category.view'],
        'retrieve': ['inventory.category.view'],
        'create': ['inventory.category.create'],
        'update': ['inventory.category.update'],
        'partial_update': ['inventory.category.update'],
        'destroy': ['inventory.category.delete'],
        'bulk': ['inventory.category.create'],
        'medicines': ['inventory.medicine.view'],
    }
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'display_order', 'created_at']
    ordering = ['display_order', 'name']
    
    def get_queryset(self):
        """Filter active categories by default"""
        queryset = super().get_queryset()
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active', 'true')
        if is_active.lower() == 'true':
            queryset = queryset.filter(is_active=True)
        
        return queryset
    
    def perform_destroy(self, instance):
        """Soft delete: mark as inactive instead of deleting"""
        instance.is_active = False
        instance.save()

    @action(detail=False, methods=['post'])
    def bulk(self, request):
        """Bulk create categories"""
        if not isinstance(request.data, list):
            raise serializers.ValidationError('Expected a list of category objects.')

        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        created = []
        max_code = Category.objects.filter(code__regex=r'^CAT\d+$').aggregate(
            max_code=Max('code')
        )['max_code']
        next_num = int(max_code.replace('CAT', '')) + 1 if max_code else 1

        with transaction.atomic():
            for item in serializer.validated_data:
                if not item.get('code'):
                    item['code'] = f"CAT{next_num:03d}"
                    next_num += 1
                category = Category(**item)
                category.save()
                created.append(category)

        output = self.get_serializer(created, many=True)
        return Response(output.data, status=status.HTTP_201_CREATED)

    
    @action(detail=True, methods=['get'])
    def medicines(self, request, pk=None):
        """Get all medicines in this category"""
        category = self.get_object()
        medicines = category.medicines.filter(is_active=True)
        serializer = MedicineListSerializer(medicines, many=True)
        return Response(serializer.data)


class MedicineViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    """
    ViewSet for Medicine management with advanced filtering
    
    Endpoints:
    - GET /medicines/ - List all medicines
    - POST /medicines/ - Create medicine
    - GET /medicines/{id}/ - Get medicine details
    - PUT/PATCH /medicines/{id}/ - Update medicine
    - DELETE /medicines/{id}/ - Soft delete medicine
    - GET /medicines/low_stock/ - Get low stock medicines
    - GET /medicines/expiring_soon/ - Get expiring medicines
    - GET /medicines/expired/ - Get expired medicines
    - POST /medicines/{id}/adjust_stock/ - Manual stock adjustment
    """
    
    queryset = Medicine.objects.select_related('category', 'supplier').all()
    permission_classes = [IsAuthenticated, HasViewPermissions]
    required_permissions = {
        'list': ['inventory.medicine.view'],
        'retrieve': ['inventory.medicine.view'],
        'create': ['inventory.medicine.create'],
        'update': ['inventory.medicine.update'],
        'partial_update': ['inventory.medicine.update'],
        'destroy': ['inventory.medicine.delete'],
        'low_stock': ['inventory.medicine.view'],
        'expiring_soon': ['inventory.medicine.view'],
        'expired': ['inventory.medicine.view'],
        'adjust_stock': ['inventory.medicine.adjust_stock'],
        'dashboard_stats': ['inventory.medicine.view'],
    }
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'supplier', 'requires_prescription', 'is_active']
    search_fields = ['name', 'generic_name', 'batch_number', 'barcode']
    ordering_fields = ['name', 'stock_quantity', 'expiry_date', 'created_at']
    ordering = ['name']
    
    def get_serializer_class(self):
        """Use different serializers for list vs detail"""
        if self.action == 'list':
            return MedicineListSerializer
        return MedicineDetailSerializer
    
    def get_queryset(self):
        """
        Custom filtering based on query parameters
        
        Query params:
        - is_active: true/false
        - stock_status: low/ok/overstock
        - expiry_status: expired/expiring_soon/ok
        - category: category_id
        - supplier: supplier_id
        """
        queryset = super().get_queryset()
        
        # Filter active medicines
        is_active = self.request.query_params.get('is_active', 'true')
        if is_active.lower() == 'true':
            queryset = queryset.filter(is_active=True)
        
        # Filter by stock status
        stock_status = self.request.query_params.get('stock_status')
        if stock_status == 'low':
            queryset = queryset.filter(stock_quantity__lte=F('min_stock_level'))
        elif stock_status == 'overstock':
            queryset = queryset.filter(stock_quantity__gte=F('max_stock_level'))
        
        # Filter by expiry status
        expiry_status = self.request.query_params.get('expiry_status')
        today = timezone.now().date()
        
        if expiry_status == 'expired':
            queryset = queryset.filter(expiry_date__lt=today)
        elif expiry_status == 'expiring_soon':
            thirty_days = today + timedelta(days=30)
            queryset = queryset.filter(expiry_date__gte=today, expiry_date__lte=thirty_days)
        
        return queryset
    
    def perform_destroy(self, instance):
        """Soft delete: mark as inactive"""
        instance.is_active = False
        instance.save()
    
    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get medicines with low stock levels"""
        medicines = self.get_queryset().filter(
            stock_quantity__lte=F('min_stock_level'),
            is_active=True
        ).order_by('stock_quantity')
        
        serializer = self.get_serializer(medicines, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def expiring_soon(self, request):
        """Get medicines expiring within 30 days"""
        days = int(request.query_params.get('days', 30))
        today = timezone.now().date()
        cutoff = today + timedelta(days=days)
        
        medicines = self.get_queryset().filter(
            expiry_date__gte=today,
            expiry_date__lte=cutoff,
            stock_quantity__gt=0
        ).order_by('expiry_date')
        
        serializer = self.get_serializer(medicines, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def expired(self, request):
        """Get expired medicines"""
        today = timezone.now().date()
        medicines = self.get_queryset().filter(
            expiry_date__lt=today,
            stock_quantity__gt=0
        ).order_by('expiry_date')
        
        serializer = self.get_serializer(medicines, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def adjust_stock(self, request, pk=None):
        """
        Manual stock adjustment
        
        POST /medicines/{id}/adjust_stock/
        Body: {
            "adjustment_type": "increase" | "decrease",
            "quantity": 10,
            "reason": "Physical count correction"
        }
        """
        medicine = self.get_object()
        serializer = StockAdjustmentSerializer(data=request.data)
        
        if serializer.is_valid():
            adjustment_type = serializer.validated_data['adjustment_type']
            quantity = serializer.validated_data['quantity']
            reason = serializer.validated_data['reason']
            
            try:
                result = InventoryService.adjust_stock(
                    medicine, quantity, adjustment_type, request.user, reason
                )
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            return Response({
                'message': 'Stock adjusted successfully',
                'new_stock': medicine.stock_quantity
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """
        Get dashboard statistics
        
        Returns:
        - Total medicines
        - Low stock count
        - Expiring soon count
        - Expired count
        - Total stock value
        """
        stats = InventoryService.get_dashboard_stats(is_active_only=True)
        stats['currency'] = getattr(settings, 'DEFAULT_CURRENCY_CODE', 'TZS')
        return Response(stats)


class StockTransactionViewSet(RBACPermissionMixin, viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for stock transaction history
    
    list: Get all transactions
    retrieve: Get single transaction
    
    Note: Stock transactions are created automatically by the system
    or through medicine.adjust_stock() endpoint
    """
    permission_classes = [IsAuthenticated, HasViewPermissions]
    required_permissions = {
        'list': ['inventory.stock_transaction.view'],
        'retrieve': ['inventory.stock_transaction.view'],
    }
    
    queryset = StockTransaction.objects.select_related(
        'medicine', 'created_by'
    ).all()
    serializer_class = StockTransactionSerializer
    # permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['medicine', 'transaction_type', 'created_by']
    ordering_fields = ['transaction_date']
    ordering = ['-transaction_date']
    
    def get_queryset(self):
        """Filter by date range if provided"""
        queryset = super().get_queryset()
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(transaction_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(transaction_date__lte=end_date)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get transaction summary by type
        
        Returns count and total quantity for each transaction type
        """
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        summary = InventoryService.get_transaction_summary(start_date, end_date)
        return Response(summary)
