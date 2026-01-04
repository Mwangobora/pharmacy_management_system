from django.contrib import admin
from .models import Category, Medicine, StockTransaction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
	list_display = ('name', 'code', 'is_active', 'created_at')
	search_fields = ('name', 'code')
	list_filter = ('is_active',)
	readonly_fields = ('created_at',)


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
	list_display = ('name', 'batch_number', 'category', 'supplier', 'stock_quantity', 'selling_price', 'expiry_date', 'is_active')
	search_fields = ('name', 'batch_number', 'barcode')
	list_filter = ('category', 'supplier', 'is_active')
	readonly_fields = ('created_at', 'updated_at')
	fieldsets = (
		(None, {'fields': ('name', 'generic_name', 'category', 'supplier')}),
		('Batch & Pricing', {'fields': ('batch_number', 'manufacture_date', 'expiry_date', 'purchase_price', 'selling_price', 'markup_percentage')}),
		('Stock', {'fields': ('stock_quantity', 'min_stock_level', 'max_stock_level', 'unit', 'storage_location', 'barcode')}),
		('Status', {'fields': ('requires_prescription', 'is_active')}),
	)


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
	list_display = ('transaction_type', 'medicine', 'quantity', 'previous_quantity', 'new_quantity', 'created_by', 'transaction_date')
	search_fields = ('medicine__name', 'reference_type', 'reference_id')
	list_filter = ('transaction_type', 'transaction_date')
	readonly_fields = ('previous_quantity', 'new_quantity', 'transaction_date')
