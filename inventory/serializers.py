from rest_framework import serializers
from .models import Category, Medicine, StockTransaction
from decimal import Decimal
from django.utils import timezone
from uuid import uuid4


class CategorySerializer(serializers.ModelSerializer):
    """Serializer for Category model"""
    
    medicine_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'description', 'code', 'display_order',
            'is_active', 'created_at', 'medicine_count'
        ]
        read_only_fields = ['id', 'created_at', 'medicine_count']
    
    def get_medicine_count(self, obj):
        """Return count of active medicines in this category"""
        return obj.medicines.filter(is_active=True).count()


class MedicineListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for medicine lists"""
    
    category_name = serializers.CharField(source='category.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    stock_status = serializers.SerializerMethodField()
    expiry_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Medicine
        fields = [
            'id', 'name', 'generic_name', 'category_name', 'supplier_name',
            'batch_number', 'expiry_date', 'purchase_price', 'selling_price', 'stock_quantity',
            'unit', 'stock_status', 'expiry_status', 'requires_prescription'
        ]
    
    def get_stock_status(self, obj):
        """Return stock status: low, ok, overstock"""
        if obj.stock_quantity <= obj.min_stock_level:
            return 'low'
        elif obj.stock_quantity >= obj.max_stock_level:
            return 'overstock'
        return 'ok'
    
    def get_expiry_status(self, obj):
        """Return expiry status: expired, expiring_soon, ok"""
        from django.utils import timezone
        from datetime import timedelta
        
        today = timezone.now().date()
        
        if obj.expiry_date < today:
            return 'expired'
        elif obj.expiry_date <= today + timedelta(days=30):
            return 'expiring_soon'
        return 'ok'


class MedicineDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for medicine CRUD operations"""
    
    category_name = serializers.CharField(source='category.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    profit_per_unit = serializers.SerializerMethodField()
    markup_percentage = serializers.SerializerMethodField()
    days_to_expiry = serializers.SerializerMethodField()
    
    class Meta:
        model = Medicine
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'generic_name': {'required': False, 'allow_blank': True, 'allow_null': True},
            'batch_number': {'required': False, 'allow_blank': True},
            'manufacture_date': {'required': False},
            'purchase_price': {'required': False},
            'selling_price': {'required': False},
            'stock_quantity': {'required': False},
            'min_stock_level': {'required': False},
            'max_stock_level': {'required': False},
            'unit': {'required': False},
            'storage_location': {'required': False, 'allow_blank': True, 'allow_null': True},
            'barcode': {'required': False, 'allow_blank': True, 'allow_null': True},
            'requires_prescription': {'required': False},
            'is_active': {'required': False},
        }
    
    def get_profit_per_unit(self, obj):
        """Calculate profit per unit"""
        return float(obj.selling_price - obj.purchase_price)
    
    def get_markup_percentage(self, obj):
        """Calculate markup percentage"""
        if obj.purchase_price > 0:
            return float(((obj.selling_price - obj.purchase_price) / obj.purchase_price) * 100)
        return 0
    
    def get_days_to_expiry(self, obj):
        """Calculate days until expiry"""
        from django.utils import timezone
        delta = obj.expiry_date - timezone.now().date()
        return delta.days
    
    def validate_expiry_date(self, value):
        """Ensure expiry date is in the future"""
        if value < timezone.now().date():
            raise serializers.ValidationError("Cannot add expired medicine")
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        # Normalize optional string fields
        if data.get('barcode') == '':
            data['barcode'] = None
        if data.get('storage_location') == '':
            data['storage_location'] = None

        # Ensure selling price > purchase price
        purchase_price = data.get('purchase_price')
        selling_price = data.get('selling_price')
        
        if purchase_price and selling_price:
            if selling_price <= purchase_price:
                raise serializers.ValidationError({
                    'selling_price': 'Selling price must be greater than purchase price'
                })
        
        # Ensure manufacture date < expiry date
        manufacture_date = data.get('manufacture_date')
        expiry_date = data.get('expiry_date')
        
        if manufacture_date and expiry_date:
            if manufacture_date >= expiry_date:
                raise serializers.ValidationError({
                    'expiry_date': 'Expiry date must be after manufacture date'
                })
        
        return data

    def create(self, validated_data):
        """
        Keep medicine creation UX lightweight by filling non-essential fields
        with backend defaults when omitted by the user.
        """
        if not validated_data.get('batch_number'):
            validated_data['batch_number'] = f"AUTO-{timezone.now().strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"

        if not validated_data.get('manufacture_date'):
            validated_data['manufacture_date'] = timezone.now().date()

        purchase_price = validated_data.get('purchase_price')
        selling_price = validated_data.get('selling_price')

        if purchase_price is None and selling_price is None:
            validated_data['purchase_price'] = Decimal('0.01')
            validated_data['selling_price'] = Decimal('0.02')
        elif purchase_price is None and selling_price is not None:
            validated_data['purchase_price'] = max(Decimal('0.01'), selling_price * Decimal('0.8'))
        elif purchase_price is not None and selling_price is None:
            validated_data['selling_price'] = max(purchase_price + Decimal('0.01'), purchase_price * Decimal('1.2'))

        validated_data.setdefault('stock_quantity', 0)
        validated_data.setdefault('min_stock_level', 10)
        validated_data.setdefault('max_stock_level', 1000)
        validated_data.setdefault('unit', 'pieces')
        validated_data.setdefault('requires_prescription', False)
        validated_data.setdefault('is_active', True)

        return super().create(validated_data)


class StockTransactionSerializer(serializers.ModelSerializer):
    """Serializer for stock transactions"""
    
    medicine_name = serializers.CharField(source='medicine.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    
    class Meta:
        model = StockTransaction
        fields = [
            'id', 'medicine', 'medicine_name', 'transaction_type',
            'transaction_type_display', 'quantity', 'previous_quantity',
            'new_quantity', 'reference_type', 'reference_id', 'notes',
            'created_by', 'created_by_username', 'transaction_date'
        ]
        read_only_fields = [
            'id', 'previous_quantity', 'new_quantity', 'transaction_date',
            'medicine_name', 'created_by_username', 'transaction_type_display'
        ]


class StockAdjustmentSerializer(serializers.Serializer):
    """Serializer for manual stock adjustments"""
    
    medicine_id = serializers.IntegerField()
    adjustment_type = serializers.ChoiceField(choices=['increase', 'decrease'])
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500)
    
    def validate_medicine_id(self, value):
        """Ensure medicine exists"""
        if not Medicine.objects.filter(id=value).exists():
            raise serializers.ValidationError("Medicine not found")
        return value
