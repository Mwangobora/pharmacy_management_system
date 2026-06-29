from django.db import models
from django.db.models import Max
from django.core.validators import MinValueValidator
import uuid
from decimal import Decimal



class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    class Meta:
        abstract = True

class Category(BaseModel):
    """Medicine classification - Flat structure"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'categories'
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.code:
            # Get the highest existing CAT### code only
            last_code = Category.objects.filter(code__regex=r'^CAT\d+$').aggregate(
                max_code=Max('code')
            )['max_code']

            if last_code:
                last_num = int(last_code.replace('CAT', ''))
                new_num = last_num + 1
            else:
                new_num = 1

            self.code = f"CAT{new_num:03d}"

        super().save(*args, **kwargs)


class Medicine(BaseModel):
    """Core product/medicine catalog"""
    
    UNIT_CHOICES = [
        ('pieces', 'Pieces'),
        ('tablets', 'Tablets'),
        ('capsules', 'Capsules'),
        ('bottles', 'Bottles'),
        ('boxes', 'Boxes'),
        ('strips', 'Strips'),
        ('vials', 'Vials'),
        ('tubes', 'Tubes'),
        ('sachets', 'Sachets'),
        ('other', 'Other'),
    ]

    # Basic Information
    name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200, blank=True, null=True)
    
    # Relationships
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='medicines'
    )
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        related_name='medicines'
    )
    
    # Batch Information
    batch_number = models.CharField(max_length=50, blank=True, null=True)
    manufacture_date = models.DateField(blank=True, null=True)
    expiry_date = models.DateField(blank=True, null=True)
    
    # Pricing
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        blank=True,
        null=True,
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    markup_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True
    )
    
    # Stock Management
    stock_quantity = models.IntegerField(default=0)
    min_stock_level = models.IntegerField(default=10)
    max_stock_level = models.IntegerField(default=1000)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES)
    base_unit = models.CharField(max_length=20, choices=UNIT_CHOICES)
    unit_review_required = models.BooleanField(default=False)
    storage_location = models.CharField(max_length=50, blank=True, null=True)
    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True)
    
    # Compliance & Status
    requires_prescription = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'medicines'
        verbose_name = 'Medicine'
        verbose_name_plural = 'Medicines'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['category']),
            models.Index(fields=['supplier']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['stock_quantity']),
            models.Index(fields=['batch_number']),
            models.Index(fields=['barcode']),
        ]

    def __str__(self):
        return f"{self.name} ({self.batch_number or self.base_unit})"


class MedicineUnitConversion(BaseModel):
    """Configured selling and purchasing units for a medicine."""

    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.CASCADE,
        related_name='unit_conversions',
    )
    unit_name = models.CharField(max_length=30)
    factor_to_base_unit = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text='How many base units are contained in one selected unit.',
    )
    is_base_unit = models.BooleanField(default=False)
    allow_purchase = models.BooleanField(default=True)
    allow_sale = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'medicine_unit_conversions'
        ordering = ['sort_order', 'unit_name']
        constraints = [
            models.UniqueConstraint(
                fields=['medicine', 'unit_name'],
                name='uniq_medicine_unit_conversion',
            ),
        ]
        indexes = [
            models.Index(fields=['medicine', 'is_active']),
            models.Index(fields=['unit_name']),
        ]

    def __str__(self):
        return f"{self.medicine.name} - {self.unit_name}"


class MedicineBatch(BaseModel):
    """Physical stock lots received through procurement."""

    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.CASCADE,
        related_name='batches',
    )
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        related_name='medicine_batches',
        null=True,
        blank=True,
    )
    batch_number = models.CharField(max_length=50)
    manufacture_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField()
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        null=True,
        blank=True,
    )
    quantity_received = models.PositiveIntegerField(default=0)
    quantity_on_hand = models.PositiveIntegerField(default=0)
    received_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_legacy = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'medicine_batches'
        ordering = ['expiry_date', 'received_at', 'created_at']
        indexes = [
            models.Index(fields=['medicine', 'expiry_date']),
            models.Index(fields=['medicine', 'quantity_on_hand']),
            models.Index(fields=['batch_number']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.medicine.name} - {self.batch_number}"


class StockTransaction(BaseModel):
    """Audit trail for all inventory movements"""
    
    TRANSACTION_TYPE_CHOICES = [
        ('purchase', 'Purchase'),
        ('sale', 'Sale'),
        ('return', 'Return'),
        ('adjustment', 'Adjustment'),
        ('damage', 'Damage'),
        ('expired', 'Expired'),
        ('transfer', 'Transfer'),
    ]
    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.PROTECT,
        related_name='stock_transactions'
    )
    batch = models.ForeignKey(
        MedicineBatch,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
    )
    source_batch = models.ForeignKey(
        MedicineBatch,
        on_delete=models.PROTECT,
        related_name='outbound_transactions',
        null=True,
        blank=True,
    )
    destination_batch = models.ForeignKey(
        MedicineBatch,
        on_delete=models.PROTECT,
        related_name='inbound_transactions',
        null=True,
        blank=True,
    )
    unit_conversion = models.ForeignKey(
        MedicineUnitConversion,
        on_delete=models.PROTECT,
        related_name='stock_transactions',
        null=True,
        blank=True,
    )
    transaction_type = models.CharField(max_length=50, choices=TRANSACTION_TYPE_CHOICES)
    quantity = models.IntegerField()
    quantity_base_units = models.IntegerField(default=0)
    quantity_in_unit = models.IntegerField(null=True, blank=True)
    unit_name = models.CharField(max_length=30, blank=True, null=True)
    previous_quantity = models.IntegerField(default=0)
    new_quantity = models.IntegerField(default=0)
    previous_batch_quantity = models.IntegerField(null=True, blank=True)
    new_batch_quantity = models.IntegerField(null=True, blank=True)
    
    # Reference to related transaction
    reference_type = models.CharField(max_length=50, blank=True, null=True)
    reference_id = models.CharField(max_length=64, blank=True, null=True)
    
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        related_name='stock_transactions'
    )
    transaction_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stock_transactions'
        verbose_name = 'Stock Transaction'
        verbose_name_plural = 'Stock Transactions'
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['medicine']),
            models.Index(fields=['batch']),
            models.Index(fields=['transaction_date']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['reference_type', 'reference_id']),
        ]

    def __str__(self):
        return f"{self.get_transaction_type_display()}: {self.medicine.name} ({self.quantity})"

    def save(self, *args, **kwargs):
        """Keep compatibility quantity fields aligned without mutating stock implicitly."""
        if not self.quantity_base_units:
            self.quantity_base_units = self.quantity
        if self.quantity == 0:
            self.quantity = self.quantity_base_units
        super().save(*args, **kwargs)
