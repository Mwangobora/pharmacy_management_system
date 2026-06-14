
from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Sum, Count, F, Avg
from django.utils import timezone
from datetime import timedelta

from .models import Customer, Sale, SaleItem, Payment
from .serializers import (
    CustomerSerializer, CustomerListSerializer,
    SaleListSerializer, SaleDetailSerializer,
    SaleItemSerializer, PaymentSerializer,
    CreateSaleSerializer, ProcessPaymentSerializer,
    RefundSaleSerializer
)
from inventory.models import StockTransaction, Medicine
from django.conf import settings
from services.sales_service import SalesService
from users.permissions import HasViewPermissions, RBACPermissionMixin

class CustomerViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    permission_classes = [IsAuthenticated, HasViewPermissions]
    required_permissions = {
        'list': ['customers.customer.view'],
        'retrieve': ['customers.customer.view'],
        'create': ['customers.customer.create'],
        'update': ['customers.customer.update'],
        'partial_update': ['customers.customer.update'],
        'destroy': ['customers.customer.delete'],
        'purchase_history': ['customers.customer.view'],
        'loyalty_summary': ['customers.customer.view'],
        'add_loyalty_points': ['customers.customer.update'],
    }
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['gender']
    search_fields = ['first_name', 'last_name', 'phone', 'email']
    ordering_fields = ['last_name', 'created_at', 'loyalty_points']
    ordering = ['last_name', 'first_name']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return CustomerListSerializer
        return CustomerSerializer
    
    @action(detail=True, methods=['get'])
    def purchase_history(self, request, pk=None):
        """Get customer purchase history"""
        customer = self.get_object()
        sales = customer.sales.all().order_by('-sale_date')
        
        serializer = SaleListSerializer(sales, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def loyalty_summary(self, request, pk=None):
        """
        Get customer loyalty summary
        
        Returns loyalty points, total spent, purchase count
        """
        customer = self.get_object()
        
        summary = {
            'customer_id': customer.customer_id,
            'customer_name': customer.full_name,
            'loyalty_points': customer.loyalty_points,
            'total_purchases': customer.sales.count(),
            'total_spent': float(customer.sales.aggregate(
                total=Sum('net_amount')
            )['total'] or 0),
            'average_purchase': float(customer.sales.aggregate(
                avg=Avg('net_amount')
            )['avg'] or 0),
            'last_purchase_date': customer.sales.order_by('-sale_date').first().sale_date
                if customer.sales.exists() else None,
            'currency': getattr(settings, 'DEFAULT_CURRENCY_CODE', 'TZS')
        }
        
        return Response(summary)
    
    @action(detail=True, methods=['post'])
    def add_loyalty_points(self, request, pk=None):
        customer = self.get_object()
        points = request.data.get('points', 0)
        
        if points <= 0:
            return Response(
                {'error': 'Points must be greater than 0'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        customer.loyalty_points += points
        customer.save()
        
        return Response({
            'message': 'Loyalty points added successfully',
            'customer_id': customer.customer_id,
            'new_loyalty_points': customer.loyalty_points
        })


class SaleViewSet(RBACPermissionMixin, viewsets.ModelViewSet):
    queryset = Sale.objects.select_related(
        'customer', 'served_by'
    ).prefetch_related('items', 'payments').all()
    permission_classes = [IsAuthenticated, HasViewPermissions]
    required_permissions = {
        'list': ['sales.sale.view'],
        'retrieve': ['sales.sale.view'],
        'create': ['sales.sale.create'],
        'update': ['sales.sale.update'],
        'partial_update': ['sales.sale.update'],
        'destroy': ['sales.sale.delete'],
        'create_with_items': ['sales.sale.create'],
        'process_payment': ['sales.sale.process_payment'],
        'refund': ['sales.sale.refund'],
        'daily_summary': ['sales.sale.view_summary'],
        'top_selling': ['sales.sale.view_summary'],
    }
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['customer', 'payment_method', 'payment_status', 'served_by']
    search_fields = ['invoice_number', 'customer__first_name', 'customer__last_name']
    ordering_fields = ['sale_date', 'net_amount', 'created_at']
    ordering = ['-sale_date']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SaleListSerializer
        elif self.action == 'create_with_items':
            return CreateSaleSerializer
        return SaleDetailSerializer
    
    def get_queryset(self):
        """Filter by date range"""
        queryset = super().get_queryset()
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            queryset = queryset.filter(sale_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(sale_date__lte=end_date)
        
        return queryset
    
    def perform_create(self, serializer):
        """Set served_by to current user"""
        serializer.save(served_by=self.request.user)

    
    @action(detail=False, methods=['post'])
    def create_with_items(self, request):
        serializer = CreateSaleSerializer(data=request.data)

        if serializer.is_valid():
            try:
                sale = SalesService.create_sale(request.user, serializer.validated_data)
            except serializers.ValidationError as e:
                return Response({'error': e.detail}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            response_serializer = SaleDetailSerializer(sale)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def process_payment(self, request, pk=None):
        """Process additional payment for a sale."""
        sale = self.get_object()
        serializer = ProcessPaymentSerializer(data=request.data)

        if serializer.is_valid():
            try:
                result = SalesService.process_payment(
                    sale,
                    serializer.validated_data['amount'],
                    serializer.validated_data['payment_method'],
                    request.user,
                    transaction_ref=serializer.validated_data.get('transaction_ref', ''),
                    notes=serializer.validated_data.get('notes', '')
                )
            except serializers.ValidationError as e:
                return Response({'error': e.detail}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({'message': 'Payment processed successfully', **result})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        sale = self.get_object()
        serializer = RefundSaleSerializer(data=request.data)

        if serializer.is_valid():
            try:
                result = SalesService.process_refund(
                    sale,
                    serializer.validated_data['refund_amount'],
                    serializer.validated_data.get('items_to_refund', []),
                    request.user,
                    serializer.validated_data.get('reason', '')
                )
            except serializers.ValidationError as e:
                return Response({'error': e.detail}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({'message': 'Refund processed', **result})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def daily_summary(self, request):
    
        date_str = request.query_params.get('date')
        if date_str:
            from datetime import datetime
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            date = timezone.now().date()
        
        summary = SalesService.daily_summary(date)
        summary['currency'] = getattr(settings, 'DEFAULT_CURRENCY_CODE', 'TZS')
        return Response(summary)
    
    @action(detail=False, methods=['get'])
    def top_selling(self, request):
        days = int(request.query_params.get('days', 30))
        limit = int(request.query_params.get('limit', 10))
        
        top_medicines = SalesService.top_selling(days=days, limit=limit)
        return Response(top_medicines)


class PaymentViewSet(RBACPermissionMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.select_related('sale', 'received_by').all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated, HasViewPermissions]
    required_permissions = {
        'list': ['sales.payment.view'],
        'retrieve': ['sales.payment.view'],
    }
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['sale', 'payment_method', 'received_by']
    ordering_fields = ['payment_date', 'amount']
    ordering = ['-payment_date']
