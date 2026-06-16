from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

from apps.inventory.models import BaseModel

class Supplier(BaseModel):
    """Vendor/supplier information management"""
    
    name = models.CharField(max_length=100)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    tax_id = models.CharField(max_length=50, blank=True, null=True, 
                              help_text="TIN (Tax Identification Number)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'suppliers'
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['phone']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.name


class Purchase(BaseModel):
    """Purchase orders from suppliers"""
    
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
    ]
    
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='purchases'
    )
    invoice_number = models.CharField(max_length=50, unique=True)
    purchase_date = models.DateField()
    
    # Amounts
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    net_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending'
    )
    notes = models.TextField(blank=True, null=True)
    
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        related_name='purchases_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'purchases'
        verbose_name = 'Purchase'
        verbose_name_plural = 'Purchases'
        ordering = ['-purchase_date', '-created_at']
        indexes = [
            models.Index(fields=['supplier']),
            models.Index(fields=['invoice_number']),
            models.Index(fields=['purchase_date']),
            models.Index(fields=['payment_status']),
        ]

    def __str__(self):
        return f"Purchase {self.invoice_number} - {self.supplier.name}"


class PurchaseItem(BaseModel):
    """Line items for each purchase order"""
    
    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name='items'
    )
    medicine = models.ForeignKey(
        'inventory.Medicine',
        on_delete=models.PROTECT,
        related_name='purchase_items'
    )
    
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    received_quantity = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'purchase_items'
        verbose_name = 'Purchase Item'
        verbose_name_plural = 'Purchase Items'
        ordering = ['id']
        indexes = [
            models.Index(fields=['purchase']),
            models.Index(fields=['medicine']),
        ]

    def __str__(self):
        return f"{self.medicine.name} x {self.quantity}"

    def save(self, *args, **kwargs):
        """Auto-calculate subtotal on save"""
        # Calculate subtotal: (quantity × unit_price) - discount + tax
        base_amount = self.quantity * self.unit_price
        discount = base_amount * (self.discount_percent / 100)
        tax = (base_amount - discount) * (self.tax_percent / 100)
        self.subtotal = base_amount - discount + tax
        
        super().save(*args, **kwargs)
