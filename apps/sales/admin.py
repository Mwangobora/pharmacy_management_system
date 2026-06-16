from django.contrib import admin
from .models import Customer, Sale, SaleItem, Payment


class SaleItemInline(admin.TabularInline):
	model = SaleItem
	extra = 0
	readonly_fields = ('subtotal',)


class PaymentInline(admin.TabularInline):
	model = Payment
	extra = 0
	readonly_fields = ('payment_date',)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
	list_display = ('id', 'full_name', 'phone', 'email', 'loyalty_points', 'created_at')
	search_fields = ('first_name', 'last_name', 'phone', 'email')
	list_filter = ('gender',)
	readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
	list_display = ('invoice_number', 'customer', 'sale_date', 'net_amount', 'payment_status', 'payment_method', 'served_by')
	search_fields = ('invoice_number', 'customer__first_name', 'customer__last_name')
	list_filter = ('payment_status', 'payment_method', 'sale_date')
	readonly_fields = ('id', 'created_at', 'updated_at')
	inlines = [SaleItemInline, PaymentInline]


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
	list_display = ('sale', 'medicine', 'batch_number', 'quantity', 'unit_price', 'subtotal', 'created_at')
	search_fields = ('medicine__name', 'batch_number')
	readonly_fields = ('subtotal', 'created_at')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
	list_display = ('id', 'sale', 'amount', 'payment_method', 'payment_date', 'received_by')
	search_fields = ('payment_id', 'sale__invoice_number', 'transaction_ref')
	list_filter = ('payment_method', 'payment_date')
	readonly_fields = ('id', 'payment_date', 'created_at')

