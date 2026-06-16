from django.contrib import admin
from .models import Supplier, Purchase, PurchaseItem
from apps.inventory.models import StockTransaction


class PurchaseItemInline(admin.TabularInline):
	model = PurchaseItem
	extra = 0
	readonly_fields = ('subtotal',)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
	list_display = ('name', 'contact_person', 'phone', 'email', 'is_active', 'created_at')
	search_fields = ('name', 'phone', 'email')
	list_filter = ('is_active',)


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
	list_display = ('invoice_number', 'supplier', 'purchase_date', 'net_amount', 'payment_status', 'created_by')
	search_fields = ('invoice_number', 'supplier__name')
	list_filter = ('payment_status', 'purchase_date')
	inlines = [PurchaseItemInline]


@admin.register(PurchaseItem)
class PurchaseItemAdmin(admin.ModelAdmin):
	list_display = ('purchase', 'medicine', 'quantity', 'unit_price', 'subtotal', 'received_quantity')
	search_fields = ('medicine__name',)
	readonly_fields = ('subtotal',)

