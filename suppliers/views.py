from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Sum, Count, F
from django.db import transaction
from django.utils import timezone

from .models import Supplier, Purchase, PurchaseItem
from .serializers import (
    SupplierSerializer, SupplierListSerializer,
    PurchaseListSerializer, PurchaseDetailSerializer,
    PurchaseItemSerializer, CreatePurchaseSerializer,
    ReceiveItemsSerializer
)
from inventory.models import StockTransaction


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
        
        # TODO: Move this to a service layer for better performance and caching
        stats = {
            'total_purchases': supplier.purchases.count(),
            'total_amount_spent': supplier.purchases.aggregate(
                total=Sum('net_amount')
            )['total'] or 0,
            'pending_payments': supplier.purchases.filter(
                payment_status__in=['pending', 'partial']
            ).aggregate(
                total=Sum('net_amount')
            )['total'] or 0,
            'active_medicines': supplier.medicines.filter(is_active=True).count(),
            'last_purchase_date': supplier.purchases.order_by('-purchase_date').first().purchase_date
                if supplier.purchases.exists() else None
        }
        
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
            # TODO: Move this entire logic to a service layer (services.py)
            with transaction.atomic():
                # Calculate totals from items
                items_data = serializer.validated_data.pop('items')
                total_amount = sum(
                    item['quantity'] * item['unit_price'] 
                    for item in items_data
                )
                
                # Create purchase
                purchase = Purchase.objects.create(
                    supplier=serializer.validated_data['supplier'],
                    invoice_number=serializer.validated_data['invoice_number'],
                    purchase_date=serializer.validated_data['purchase_date'],
                    total_amount=total_amount,
                    tax_amount=serializer.validated_data.get('tax_amount', 0),
                    discount_amount=serializer.validated_data.get('discount_amount', 0),
                    net_amount=total_amount + serializer.validated_data.get('tax_amount', 0) 
                               - serializer.validated_data.get('discount_amount', 0),
                    payment_status=serializer.validated_data.get('payment_status', 'pending'),
                    notes=serializer.validated_data.get('notes', ''),
                    created_by=request.user
                )
                
                # Create purchase items
                for item_data in items_data:
                    PurchaseItem.objects.create(
                        purchase=purchase,
                        medicine_id=item_data['medicine'],
                        quantity=item_data['quantity'],
                        unit_price=item_data['unit_price'],
                        discount_percent=item_data.get('discount_percent', 0),
                        tax_percent=item_data.get('tax_percent', 0)
                    )
                
                # Return created purchase
                response_serializer = PurchaseDetailSerializer(purchase)
                return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def receive_items(self, request, pk=None):
        """
        Mark items as received and update stock
        
        POST /purchases/{id}/receive-items/
        Body: {
            "items": [
                {"item_id": 1, "received_quantity": 100},
                {"item_id": 2, "received_quantity": 50}
            ]
        }
        """
        purchase = self.get_object()
        serializer = ReceiveItemsSerializer(data=request.data)
        
        if serializer.is_valid():
            # TODO: Move this to a service layer
            with transaction.atomic():
                for item_data in serializer.validated_data['items']:
                    try:
                        item = PurchaseItem.objects.get(
                            pk=item_data['item_id'],
                            purchase=purchase
                        )
                        
                        received_qty = item_data['received_quantity']
                        
                        # Validate received quantity
                        if received_qty > item.quantity:
                            return Response(
                                {'error': f'Received quantity ({received_qty}) exceeds ordered quantity ({item.quantity})'},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                        
                        # Update received quantity
                        item.received_quantity = received_qty
                        item.save()
                        
                        # Create stock transaction (increase stock)
                        StockTransaction.objects.create(
                            medicine=item.medicine,
                            transaction_type='purchase',
                            quantity=received_qty,
                            reference_type='purchase',
                            reference_id=purchase.id,
                            notes=f'Received from purchase {purchase.invoice_number}',
                            created_by=request.user
                        )
                        
                    except PurchaseItem.DoesNotExist:
                        return Response(
                            {'error': f'Purchase item {item_data["item_id"]} not found'},
                            status=status.HTTP_404_NOT_FOUND
                        )
                
                return Response({
                    'message': 'Items received successfully',
                    'purchase_id': purchase.id
                })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['patch'])
    def update_payment_status(self, request, pk=None):
        """
        Update payment status
        
        PATCH /purchases/{id}/update-payment-status/
        Body: {"payment_status": "paid"}
        """
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
        """
        Get purchase dashboard statistics
        
        Returns:
        - Total purchases
        - Total amount
        - Pending payments
        - Recent purchases
        """
        queryset = self.get_queryset()
        
        # TODO: Move this to a service layer and add caching
        stats = {
            'total_purchases': queryset.count(),
            'total_amount': queryset.aggregate(total=Sum('net_amount'))['total'] or 0,
            'pending_amount': queryset.filter(
                payment_status__in=['pending', 'partial']
            ).aggregate(total=Sum('net_amount'))['total'] or 0,
            'paid_amount': queryset.filter(
                payment_status='paid'
            ).aggregate(total=Sum('net_amount'))['total'] or 0,
            'recent_purchases_count': queryset.filter(
                purchase_date__gte=timezone.now().date() - timezone.timedelta(days=30)
            ).count()
        }
        
        return Response(stats)


class PurchaseItemViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for purchase items
    
    Items are created through Purchase create_with_items endpoint
    """
    
    queryset = PurchaseItem.objects.select_related('purchase', 'medicine').all()
    serializer_class = PurchaseItemSerializer
    # permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['purchase', 'medicine']
