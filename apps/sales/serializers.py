from rest_framework import serializers
from .models import Customer, Sale, SaleItem, Payment
from apps.inventory.models import Medicine
from apps.inventory.selectors import convert_to_base_units
from django.db import transaction, models
from decimal import Decimal


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for Customer model"""
    
    total_purchases = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = [
            'id', 'first_name', 'last_name', 'full_name',
            'phone', 'email', 'address', 'date_of_birth', 'gender',
            'loyalty_points', 'created_at', 'updated_at',
            'total_purchases', 'total_spent'
        ]
        read_only_fields = ['id', 'full_name', 'created_at', 'updated_at']
    
    def get_total_purchases(self, obj):
        """Return total number of purchases"""
        return obj.sales.count()
    
    def get_total_spent(self, obj):
        """Return total amount spent"""
        return float(obj.sales.aggregate(
            total=models.Sum('net_amount')
        )['total'] or 0)


class CustomerListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for customer lists"""
    
    class Meta:
        model = Customer
        fields = ['id', 'full_name', 'phone', 'email', 'loyalty_points']


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment model"""
    
    received_by_username = serializers.CharField(source='received_by.username', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'sale', 'amount', 'payment_method',
            'payment_method_display', 'payment_date', 'transaction_ref',
            'received_by', 'received_by_username', 'notes', 'created_at'
        ]
        read_only_fields = ['id', 'payment_date', 'created_at']
    
    def validate_amount(self, value):
        """Ensure amount is positive"""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value


class SaleItemSerializer(serializers.ModelSerializer):
    """Serializer for sale items"""
    
    medicine_name = serializers.CharField(source='medicine.name', read_only=True)
    medicine_display_id = serializers.CharField(source='medicine.id', read_only=True)
    profit = serializers.SerializerMethodField()
    batch_allocations = serializers.SerializerMethodField()
    
    class Meta:
        model = SaleItem
        fields = [
            'id', 'medicine', 'medicine_name', 'medicine_display_id',
            'batch_number', 'quantity', 'unit_conversion', 'sold_unit_name',
            'sold_quantity_in_unit', 'unit_price', 'selling_price_snapshot',
            'cost_price_snapshot', 'discount_percent', 'tax_percent',
            'subtotal', 'profit', 'refunded_quantity', 'batch_allocations'
        ]
        read_only_fields = ['id', 'subtotal']
    
    def get_profit(self, obj):
        if obj.profit_snapshot is not None:
            return float(obj.profit_snapshot)
        if obj.cost_price_snapshot is None:
            return 0.0
        return float((Decimal(obj.unit_price) - Decimal(obj.cost_price_snapshot)) * Decimal(obj.quantity))

    def get_batch_allocations(self, obj):
        return [
            {
                'batch_id': str(allocation.batch_id),
                'batch_number': allocation.batch.batch_number,
                'quantity': allocation.quantity,
                'cost_price_snapshot': float(allocation.cost_price_snapshot),
                'selling_price_snapshot': float(allocation.selling_price_snapshot),
                'returned_quantity': allocation.returned_quantity,
            }
            for allocation in obj.batch_allocations.select_related('batch').all()
        ]
    
    def validate_quantity(self, value):
        """Ensure quantity is positive"""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value
    
    def validate(self, data):
        """Validate stock availability"""
        medicine = data.get('medicine')
        quantity = data.get('quantity')
        
        if medicine and quantity:
            unit_name = data.get('unit_name') or medicine.base_unit or medicine.unit
            _, quantity_base_units = convert_to_base_units(
                medicine,
                int(quantity),
                unit_name,
                allow_sale=True,
            )
            if medicine.stock_quantity < quantity_base_units:
                raise serializers.ValidationError({
                    'quantity': f'Insufficient stock. Available: {medicine.stock_quantity} {medicine.base_unit}'
                })
            if medicine.selling_price is None:
                raise serializers.ValidationError({
                    'medicine': 'Selling price must be set before this medicine can be sold.'
                })
            
            # Check if medicine is expired
            from django.utils import timezone
            if medicine.expiry_date and medicine.expiry_date < timezone.now().date():
                raise serializers.ValidationError({
                    'medicine': 'This medicine has expired and cannot be sold'
                })
            
            # Check if prescription is required
            if medicine.requires_prescription:
                # Require that a prescription reference be provided in the
                # incoming data until a dedicated prescription module exists.
                # We allow callers to attach a `prescription` key (id or ref)
                # either on the item dict or via serializer context.
                prescription_attached = False
                # item-level data (if validating nested during creation)
                if isinstance(data, dict) and data.get('prescription'):
                    prescription_attached = True
                # or via serializer context (e.g. view attaches true flag)
                if self.context.get('prescription_attached'):
                    prescription_attached = True

                if not prescription_attached:
                    raise serializers.ValidationError({
                        'medicine': 'This medicine requires a valid prescription to be sold. Attach prescription reference.'
                    })
        
        return data


class SaleListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for sale lists"""
    
    customer_name = serializers.SerializerMethodField()
    served_by_username = serializers.CharField(source='served_by.username', read_only=True)
    items_count = serializers.SerializerMethodField()
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    
    class Meta:
        model = Sale
        fields = [
            'id', 'invoice_number', 'customer', 'customer_name',
            'sale_date', 'net_amount', 'payment_method', 'payment_method_display',
            'payment_status', 'payment_status_display', 'served_by_username',
            'items_count'
        ]
    
    def get_customer_name(self, obj):
        """Return customer name or Walk-in"""
        return obj.customer.full_name if obj.customer else "Walk-in"
    
    def get_items_count(self, obj):
        """Return count of items in this sale"""
        return obj.items.count()


class SaleDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for sale CRUD operations"""
    
    customer_name = serializers.SerializerMethodField()
    served_by_username = serializers.CharField(source='served_by.username', read_only=True)
    items = SaleItemSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    total_paid = serializers.SerializerMethodField()
    amount_due = serializers.SerializerMethodField()
    total_profit = serializers.SerializerMethodField()
    
    class Meta:
        model = Sale
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_customer_name(self, obj):
        return obj.customer.full_name if obj.customer else "Walk-in"
    
    def get_total_paid(self, obj):
        """Calculate total amount paid"""
        return float(obj.payments.aggregate(
            total=models.Sum('amount')
        )['total'] or 0)
    
    def get_amount_due(self, obj):
        """Calculate remaining amount due"""
        total_paid = self.get_total_paid(obj)
        return float(obj.net_amount) - total_paid
    
    def get_total_profit(self, obj):
        return float(obj.items.aggregate(total=models.Sum('profit_snapshot'))['total'] or 0)
    
    def validate_invoice_number(self, value):
        """Ensure invoice number is unique"""
        if self.instance:
            if Sale.objects.exclude(pk=self.instance.pk).filter(invoice_number=value).exists():
                raise serializers.ValidationError("Invoice number already exists")
        else:
            if Sale.objects.filter(invoice_number=value).exists():
                raise serializers.ValidationError("Invoice number already exists")
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        total = data.get('total_amount', Decimal('0'))
        tax = data.get('tax_amount', Decimal('0'))
        discount = data.get('discount_amount', Decimal('0'))
        
        expected_net = total + tax - discount
        actual_net = data.get('net_amount', Decimal('0'))
        
        if abs(expected_net - actual_net) > Decimal('0.01'):
            raise serializers.ValidationError({
                'net_amount': f'Net amount should be {expected_net} (total + tax - discount)'
            })
        
        return data


class CreateSaleSerializer(serializers.Serializer):
    """Serializer for creating sale with items and payment in one transaction"""
    
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=False,
        allow_null=True
    )
    sale_date = serializers.DateTimeField(required=False)
    tax_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=0, required=False)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=0, required=False)
    payment_method = serializers.ChoiceField(choices=Sale.PAYMENT_METHOD_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True)
    
    # Nested items
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        error_messages={'min_length': 'At least one item is required'}
    )
    
    # Payment details
    payment_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    transaction_ref = serializers.CharField(max_length=100, required=False, allow_blank=True)
    
    def validate_items(self, value):
        """Validate sale items"""
        for item in value:
            # Check required fields
            required_fields = ['medicine', 'quantity']
            for field in required_fields:
                if field not in item:
                    raise serializers.ValidationError(f"Each item must have {', '.join(required_fields)}")
            
            # Validate medicine exists and has stock
            try:
                medicine = Medicine.objects.get(pk=item['medicine'])
                unit_name = item.get('unit_name') or medicine.base_unit or medicine.unit
                _, quantity_base_units = convert_to_base_units(
                    medicine,
                    int(item['quantity']),
                    unit_name,
                    allow_sale=True,
                )
                
                # Check stock
                if medicine.stock_quantity < quantity_base_units:
                    raise serializers.ValidationError(
                        f"{medicine.name}: Insufficient stock (Available: {medicine.stock_quantity})"
                    )
                if medicine.selling_price is None:
                    raise serializers.ValidationError(
                        f"{medicine.name}: Selling price must be set before this medicine can be sold"
                    )
                
                # Check expiry
                from django.utils import timezone
                if medicine.expiry_date and medicine.expiry_date < timezone.now().date():
                    raise serializers.ValidationError(
                        f"{medicine.name}: Medicine has expired"
                    )
                
            except Medicine.DoesNotExist:
                raise serializers.ValidationError(f"Medicine with id {item['medicine']} not found")
            
            # Validate quantity
            if item['quantity'] <= 0:
                raise serializers.ValidationError("Quantity must be greater than 0")
        
        return value
    
    def validate_payment_amount(self, value):
        """Ensure payment amount is positive"""
        if value <= 0:
            raise serializers.ValidationError("Payment amount must be greater than 0")
        return value


class ProcessPaymentSerializer(serializers.Serializer):
    """Serializer for processing additional payments"""
    
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_method = serializers.ChoiceField(choices=Payment.PAYMENT_METHOD_CHOICES)
    transaction_ref = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_amount(self, value):
        """Ensure amount is positive"""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0")
        return value


class RefundSaleSerializer(serializers.Serializer):
    """Serializer for processing sale refunds"""
    
    refund_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reason = serializers.CharField(max_length=500)
    items_to_refund = serializers.ListField(
        child=serializers.DictField(),
        required=False
    )
