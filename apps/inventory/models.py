from django.db import models
from django.db.models import F, Max
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
import uuid
from django.utils import timezone
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
    batch_number = models.CharField(max_length=50)
    manufacture_date = models.DateField()
    expiry_date = models.DateField()
    
    # Pricing
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
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
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='pieces')
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
        return f"{self.name} ({self.batch_number})"


class StockTransaction(BaseModel):
    """Audit trail for all inventory movements"""
    
    TRANSACTION_TYPE_CHOICES = [
        ('purchase', 'Purchase'),
        ('sale', 'Sale'),
        ('return', 'Return'),
        ('adjustment', 'Adjustment'),
        ('damage', 'Damage'),
        ('expired', 'Expired'),
    ]
    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.PROTECT,
        related_name='stock_transactions'
    )
    transaction_type = models.CharField(max_length=50, choices=TRANSACTION_TYPE_CHOICES)
    quantity = models.IntegerField()
    previous_quantity = models.IntegerField()
    new_quantity = models.IntegerField()
    
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
            models.Index(fields=['transaction_date']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['reference_type', 'reference_id']),
        ]

    def __str__(self):
        return f"{self.get_transaction_type_display()}: {self.medicine.name} ({self.quantity})"

    def save(self, *args, **kwargs):
        """Auto-update medicine stock quantity on transaction creation"""
        if self._state.adding:  # Only on new transactions
            from django.db import transaction as db_transaction
            
            with db_transaction.atomic():
                # Lock medicine row for update
                medicine = Medicine.objects.select_for_update().get(pk=self.medicine.pk)
                self.previous_quantity = medicine.stock_quantity
                
                # Calculate new quantity
                if self.transaction_type in ['purchase', 'return']:
                    change = abs(self.quantity)
                else:
                    change = -abs(self.quantity)
                
                self.new_quantity = self.previous_quantity + change
                
                # Update stock atomically
                Medicine.objects.filter(pk=medicine.pk).update(
                    stock_quantity=F('stock_quantity') + change,
                    updated_at=timezone.now()
                )
        
        super().save(*args, **kwargs)
