from rest_framework import serializers
from .models import Supplier, Purchase, PurchaseItem
from inventory.models import Medicine
from decimal import Decimal


class SupplierSerializer(serializers.ModelSerializer):
    """Serializer for Supplier model"""
    
    total_purchases = serializers.SerializerMethodField()
    active_medicines_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'contact_person', 'phone', 'email',
            'address', 'tax_id', 'is_active', 'created_at', 'updated_at',
            'total_purchases', 'active_medicines_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_purchases(self, obj):
        """Return total number of purchases from this supplier"""
        return obj.purchases.count()
    
    def get_active_medicines_count(self, obj):
        """Return count of active medicines from this supplier"""
        return obj.medicines.filter(is_active=True).count()


class SupplierListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for supplier lists"""
    
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'phone', 'email', 'is_active']


class PurchaseItemSerializer(serializers.ModelSerializer):
    """Serializer for purchase items"""
    
    medicine_name = serializers.CharField(source='medicine.name', read_only=True)
    medicine_display_id = serializers.IntegerField(source='medicine.medicine_id', read_only=True)
    
    class Meta:
        model = PurchaseItem
        fields = [
            'id', 'medicine', 'medicine_name', 'medicine_display_id',
            'quantity', 'unit_price', 'discount_percent', 'tax_percent',
            'subtotal', 'received_quantity'
        ]
        read_only_fields = ['id', 'subtotal']
    
    def validate_quantity(self, value):
        """Ensure quantity is positive"""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value
    
    def validate_received_quantity(self, value):
        """Ensure received quantity doesn't exceed ordered quantity"""
        if value < 0:
            raise serializers.ValidationError("Received quantity cannot be negative")
        
        # Check against ordered quantity if updating
        if self.instance:
            if value > self.instance.quantity:
                raise serializers.ValidationError(
                    f"Received quantity cannot exceed ordered quantity ({self.instance.quantity})"
                )
        
        return value


class PurchaseListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for purchase lists"""
    
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    items_count = serializers.SerializerMethodField()
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    
    class Meta:
        model = Purchase
        fields = [
            'id', 'invoice_number', 'supplier_name', 
            'purchase_date', 'net_amount', 'payment_status', 
            'payment_status_display', 'items_count', 'created_by_username'
        ]
    
    def get_items_count(self, obj):
        """Return count of items in this purchase"""
        return obj.items.count()


class PurchaseDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for purchase CRUD operations"""
    
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    items = PurchaseItemSerializer(many=True, read_only=True)
    amount_paid = serializers.SerializerMethodField()
    amount_due = serializers.SerializerMethodField()
    
    class Meta:
        model = Purchase
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_amount_paid(self, obj):
        """Calculate total amount paid (TODO: Move to Payment model integration)"""
        # Placeholder - will be calculated from payments when Payment model is added
        if obj.payment_status == 'paid':
            return float(obj.net_amount)
        elif obj.payment_status == 'partial':
            return float(obj.net_amount * Decimal('0.5'))  # TODO: Get from actual payments
        return 0
    
    def get_amount_due(self, obj):
        """Calculate remaining amount due"""
        paid = self.get_amount_paid(obj)
        return float(obj.net_amount) - paid
    
    def validate_invoice_number(self, value):
        """Ensure invoice number is unique"""
        if self.instance:
            # Updating existing purchase
            if Purchase.objects.exclude(pk=self.instance.pk).filter(invoice_number=value).exists():
                raise serializers.ValidationError("Invoice number already exists")
        else:
            # Creating new purchase
            if Purchase.objects.filter(invoice_number=value).exists():
                raise serializers.ValidationError("Invoice number already exists")
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        # Ensure net_amount is calculated correctly
        total = data.get('total_amount', Decimal('0'))
        tax = data.get('tax_amount', Decimal('0'))
        discount = data.get('discount_amount', Decimal('0'))
        
        expected_net = total + tax - discount
        actual_net = data.get('net_amount', Decimal('0'))
        
        if abs(expected_net - actual_net) > Decimal('0.01'):  # Allow 1 cent difference for rounding
            raise serializers.ValidationError({
                'net_amount': f'Net amount should be {expected_net} (total + tax - discount)'
            })
        
        return data


class CreatePurchaseSerializer(serializers.Serializer):
    """Serializer for creating purchase with items in one request"""
    
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    invoice_number = serializers.CharField(max_length=50)
    purchase_date = serializers.DateField()
    tax_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_status = serializers.ChoiceField(choices=Purchase.PAYMENT_STATUS_CHOICES, default='pending')
    notes = serializers.CharField(required=False, allow_blank=True)
    
    # Nested items
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        error_messages={'min_length': 'At least one item is required'}
    )
    
    def validate_items(self, value):
        """Validate purchase items"""
        for item in value:
            # Check required fields
            if 'medicine' not in item or 'quantity' not in item or 'unit_price' not in item:
                raise serializers.ValidationError(
                    "Each item must have medicine, quantity, and unit_price"
                )
            
            # Validate medicine exists
            try:
                Medicine.objects.get(pk=item['medicine'])
            except Medicine.DoesNotExist:
                raise serializers.ValidationError(f"Medicine with id {item['medicine']} not found")
            
            # Validate quantity
            if item['quantity'] <= 0:
                raise serializers.ValidationError("Quantity must be greater than 0")
        
        return value
    
    def validate_invoice_number(self, value):
        """Ensure invoice number is unique"""
        if Purchase.objects.filter(invoice_number=value).exists():
            raise serializers.ValidationError("Invoice number already exists")
        return value


class ReceiveItemsSerializer(serializers.Serializer):
    """Serializer for receiving purchased items"""
    
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1
    )
    
    def validate_items(self, value):
        """Validate received items"""
        for item in value:
            if 'item_id' not in item or 'received_quantity' not in item:
                raise serializers.ValidationError(
                    "Each item must have item_id and received_quantity"
                )
            
            # Validate received quantity
            if item['received_quantity'] < 0:
                raise serializers.ValidationError("Received quantity cannot be negative")
        
        return value



