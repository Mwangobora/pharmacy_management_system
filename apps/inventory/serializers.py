from rest_framework import serializers
from django.db import transaction
from .models import (
    Category,
    Medicine,
    MedicineBatch,
    MedicineUnitConversion,
    StockTransaction,
)
from decimal import Decimal
from django.utils import timezone


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
    days_to_expiry = serializers.SerializerMethodField()
    batches = serializers.SerializerMethodField()
    unit_conversions = serializers.SerializerMethodField()
    unit_review_required = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Medicine
        fields = [
            'id', 'name', 'generic_name', 'category', 'category_name', 'supplier', 'supplier_name',
            'manufacture_date',
            'batch_number', 'expiry_date', 'purchase_price', 'selling_price', 'stock_quantity',
            'min_stock_level', 'max_stock_level', 'unit', 'base_unit', 'storage_location',
            'barcode', 'requires_prescription', 'is_active', 'created_at', 'updated_at',
            'unit_review_required', 'stock_status', 'expiry_status', 'days_to_expiry', 'batches', 'unit_conversions',
        ]

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated and not request.user.has_permission('inventory.medicine.view_cost_price'):
            fields.pop('purchase_price', None)
        return fields
    
    def get_stock_status(self, obj):
        """Return stock status: low, ok, overstock"""
        if obj.stock_quantity <= obj.min_stock_level:
            return 'low'
        elif obj.stock_quantity >= obj.max_stock_level:
            return 'overstock'
        return 'ok'
    
    def get_expiry_status(self, obj):
        """Return expiry status: expired, expiring_soon, ok"""
        from datetime import timedelta
        
        today = timezone.now().date()
        
        if not obj.expiry_date:
            return 'unknown'
        if obj.expiry_date < today:
            return 'expired'
        elif obj.expiry_date <= today + timedelta(days=30):
            return 'expiring_soon'
        return 'ok'

    def get_days_to_expiry(self, obj):
        if not obj.expiry_date:
            return None
        return (obj.expiry_date - timezone.now().date()).days

    def get_batches(self, obj):
        return MedicineBatchSerializer(
            obj.batches.order_by('expiry_date', 'received_at'),
            many=True,
        ).data

    def get_unit_conversions(self, obj):
        return MedicineUnitConversionSerializer(
            obj.unit_conversions.order_by('sort_order', 'unit_name'),
            many=True,
        ).data


class MedicineDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for medicine CRUD operations"""
    
    category_name = serializers.CharField(source='category.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    profit_per_unit = serializers.SerializerMethodField()
    markup_percentage = serializers.SerializerMethodField()
    days_to_expiry = serializers.SerializerMethodField()
    batches = serializers.SerializerMethodField()
    unit_conversions = serializers.SerializerMethodField()
    dosage_form = serializers.ChoiceField(
        choices=[
            ('tablet', 'Tablet'),
            ('capsule', 'Capsule'),
            ('syrup', 'Syrup'),
            ('suspension', 'Suspension'),
            ('injection', 'Injection'),
            ('ampoule', 'Ampoule'),
            ('cream', 'Cream'),
            ('ointment', 'Ointment'),
            ('sachet_powder', 'Sachet Powder'),
        ],
        required=False,
        write_only=True,
    )
    
    class Meta:
        model = Medicine
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'generic_name': {'required': False, 'allow_blank': True, 'allow_null': True},
            'batch_number': {'read_only': True},
            'manufacture_date': {'read_only': True},
            'expiry_date': {'read_only': True},
            'purchase_price': {'read_only': True},
            'selling_price': {'required': True},
            'stock_quantity': {'read_only': True},
            'min_stock_level': {'required': False},
            'max_stock_level': {'required': False},
            'unit': {'read_only': True},
            'base_unit': {'required': True},
            'storage_location': {'required': False, 'allow_blank': True, 'allow_null': True},
            'barcode': {'required': False, 'allow_blank': True, 'allow_null': True},
            'requires_prescription': {'required': False},
            'is_active': {'required': False},
            'unit_review_required': {'read_only': True},
        }

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request and request.user.is_authenticated and not request.user.has_permission('inventory.medicine.view_cost_price'):
            fields.pop('purchase_price', None)
            fields.pop('profit_per_unit', None)
            fields.pop('markup_percentage', None)
        fields['unit_conversions'] = MedicineUnitConversionSerializer(
            many=True,
            required=False,
        )
        return fields
    
    def get_profit_per_unit(self, obj):
        """Calculate profit per unit"""
        if obj.selling_price is None or obj.purchase_price is None:
            return None
        return float(obj.selling_price - obj.purchase_price)
    
    def get_markup_percentage(self, obj):
        """Calculate markup percentage"""
        if obj.purchase_price and obj.purchase_price > 0 and obj.selling_price is not None:
            return float(((obj.selling_price - obj.purchase_price) / obj.purchase_price) * 100)
        return 0
    
    def get_days_to_expiry(self, obj):
        """Calculate days until expiry"""
        if not obj.expiry_date:
            return None
        delta = obj.expiry_date - timezone.now().date()
        return delta.days

    def get_batches(self, obj):
        return MedicineBatchSerializer(
            obj.batches.order_by('expiry_date', 'received_at'),
            many=True,
        ).data

    def get_unit_conversions(self, obj):
        return MedicineUnitConversionSerializer(
            obj.unit_conversions.order_by('sort_order', 'unit_name'),
            many=True,
        ).data
    
    def validate(self, data):
        """Cross-field validation"""
        # Normalize optional string fields
        if data.get('barcode') == '':
            data['barcode'] = None
        if data.get('storage_location') == '':
            data['storage_location'] = None

        if self.instance is None and not data.get('base_unit'):
            raise serializers.ValidationError({
                'base_unit': 'Base unit is required when creating a medicine.'
            })

        if self.instance is None:
            forbidden_create_fields = ['batch_number', 'manufacture_date', 'expiry_date', 'purchase_price', 'stock_quantity']
            forbidden_supplied = [
                field_name for field_name in forbidden_create_fields
                if self.initial_data.get(field_name) not in (None, '', [])
            ]
            if forbidden_supplied:
                raise serializers.ValidationError({
                    field_name: 'Enter batch, expiry, manufacture, cost, and stock during purchase receiving, not medicine creation.'
                    for field_name in forbidden_supplied
                })

        conversions = data.get('unit_conversions', [])
        seen_units = set()
        for conversion in conversions:
            unit_name = conversion['unit_name']
            if unit_name in seen_units:
                raise serializers.ValidationError({
                    'unit_conversions': f'Duplicate unit conversion "{unit_name}" is not allowed.'
                })
            if int(conversion['factor_to_base_unit']) <= 0:
                raise serializers.ValidationError({
                    'unit_conversions': f'Conversion factor for "{unit_name}" must be greater than 0.'
                })
            seen_units.add(unit_name)

        return data

    def _save_unit_conversions(self, medicine, conversions):
        MedicineUnitConversion.objects.filter(medicine=medicine).update(is_base_unit=False)
        MedicineUnitConversion.objects.update_or_create(
            medicine=medicine,
            unit_name=medicine.base_unit,
            defaults={
                'factor_to_base_unit': 1,
                'is_base_unit': True,
                'allow_purchase': True,
                'allow_sale': True,
                'is_active': True,
                'sort_order': 0,
            },
        )

        for index, conversion in enumerate(conversions, start=1):
            if conversion['unit_name'] == medicine.base_unit:
                continue
            MedicineUnitConversion.objects.update_or_create(
                medicine=medicine,
                unit_name=conversion['unit_name'],
                defaults={
                    'factor_to_base_unit': conversion['factor_to_base_unit'],
                    'is_base_unit': False,
                    'allow_purchase': conversion.get('allow_purchase', True),
                    'allow_sale': conversion.get('allow_sale', True),
                    'is_active': conversion.get('is_active', True),
                    'sort_order': conversion.get('sort_order', index),
                },
            )

    @transaction.atomic
    def create(self, validated_data):
        conversions = validated_data.pop('unit_conversions', [])
        validated_data.pop('dosage_form', None)
        validated_data['unit'] = validated_data['base_unit']
        validated_data.setdefault('min_stock_level', 10)
        validated_data.setdefault('max_stock_level', 1000)
        validated_data.setdefault('requires_prescription', False)
        validated_data.setdefault('is_active', True)
        validated_data['unit_review_required'] = False
        medicine = super().create(validated_data)
        self._save_unit_conversions(medicine, conversions)
        return medicine

    @transaction.atomic
    def update(self, instance, validated_data):
        conversions = validated_data.pop('unit_conversions', None)
        validated_data.pop('dosage_form', None)
        if 'base_unit' in validated_data:
            validated_data['unit'] = validated_data['base_unit']
            validated_data['unit_review_required'] = False
        medicine = super().update(instance, validated_data)
        if conversions is not None:
            self._save_unit_conversions(medicine, conversions)
        return medicine


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
    
    medicine_id = serializers.UUIDField()
    adjustment_type = serializers.ChoiceField(choices=['increase', 'decrease'])
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500)
    
    def validate_medicine_id(self, value):
        """Ensure medicine exists"""
        if not Medicine.objects.filter(id=value).exists():
            raise serializers.ValidationError("Medicine not found")
        return value


class MedicineUnitConversionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicineUnitConversion
        fields = [
            'id',
            'unit_name',
            'factor_to_base_unit',
            'is_base_unit',
            'allow_purchase',
            'allow_sale',
            'is_active',
            'sort_order',
        ]


class MedicineBatchSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)

    class Meta:
        model = MedicineBatch
        fields = [
            'id',
            'batch_number',
            'manufacture_date',
            'expiry_date',
            'purchase_price',
            'selling_price',
            'quantity_received',
            'quantity_on_hand',
            'received_at',
            'supplier',
            'supplier_name',
            'is_active',
            'is_legacy',
            'notes',
        ]
