from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Customer(models.Model):
    """Customer/patient information"""
    
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('Other', 'Other'),
    ]

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    email = models.EmailField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True)
    loyalty_points = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customers'
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['phone']),
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['email']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Sale(models.Model):
    """Customer sales transactions"""
    
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('mobile', 'Mobile Money'),
        ('insurance', 'Insurance'),
        ('credit', 'Credit'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('paid', 'Paid'),
        ('partial', 'Partial'),
        ('pending', 'Pending'),
    ]

    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales',
        help_text="Optional - for walk-in customers"
    )
    invoice_number = models.CharField(max_length=50, unique=True)
    sale_date = models.DateTimeField()
    
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
    
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='paid'
    )
    
    served_by = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        related_name='sales_served'
    )
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sales'
        verbose_name = 'Sale'
        verbose_name_plural = 'Sales'
        ordering = ['-sale_date', '-created_at']
        indexes = [
            models.Index(fields=['customer']),
            models.Index(fields=['invoice_number']),
            models.Index(fields=['sale_date']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['served_by']),
        ]

    def __str__(self):
        customer_name = self.customer.full_name if self.customer else "Walk-in"
        return f"Sale {self.invoice_number} - {customer_name}"


class SaleItem(models.Model):
    """Line items for each sale transaction"""
    
    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='items'
    )
    medicine = models.ForeignKey(
        'inventory.Medicine',
        on_delete=models.PROTECT,
        related_name='sale_items'
    )
    batch_number = models.CharField(max_length=50)
    
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
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sale_items'
        verbose_name = 'Sale Item'
        verbose_name_plural = 'Sale Items'
        ordering = ['id']
        indexes = [
            models.Index(fields=['sale']),
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


class Payment(models.Model):
    """Payment tracking for sales - supports partial payments"""
    
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('mobile', 'Mobile Money'),
        ('insurance', 'Insurance'),
        ('credit', 'Credit'),
    ]

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='payments'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_date = models.DateTimeField(auto_now_add=True)
    transaction_ref = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Reference number for card/mobile payments"
    )
    received_by = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        related_name='payments_received'
    )
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payments'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['sale']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['payment_method']),
        ]

    def __str__(self):
        return f"Payment {self.amount} for {self.sale.invoice_number}"