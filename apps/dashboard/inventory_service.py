from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.inventory.models import Medicine, MedicineBatch, StockTransaction

from .comparison import build_metric_payload
from .query_utils import apply_stock_filters, cost_visibility, determine_granularity, integer_zero, money_zero, truncate_for_granularity


class InventoryDashboardService:
    @staticmethod
    def get_data(user, filters):
        today = timezone.localdate()
        can_view_costs = cost_visibility(user)
        medicines = Medicine.objects.filter(is_active=True)
        active_batches = MedicineBatch.objects.filter(medicine__is_active=True, is_active=True)
        cost_stock = active_batches.aggregate(value=Coalesce(Sum(ExpressionWrapper(
            F('quantity_on_hand') * F('purchase_price'),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )), money_zero()))['value'] if can_view_costs else None
        retail_stock = active_batches.aggregate(value=Coalesce(Sum(ExpressionWrapper(
            F('quantity_on_hand') * F('selling_price'),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )), money_zero()))['value']
        expiry_30 = active_batches.filter(quantity_on_hand__gt=0, expiry_date__gte=today, expiry_date__lte=today + timedelta(days=30))
        expired = active_batches.filter(quantity_on_hand__gt=0, expiry_date__lt=today)
        low_stock = medicines.filter(stock_quantity__gt=0, stock_quantity__lte=F('min_stock_level'))
        out_of_stock = medicines.filter(stock_quantity__lte=0)

        stock_movements = apply_stock_filters(
            StockTransaction.objects.all(),
            filters,
        ).annotate(
            bucket=truncate_for_granularity(
                'transaction_date',
                determine_granularity(filters),
            )
        ).values(
            'bucket',
            'transaction_type',
        ).annotate(
            quantity=Coalesce(Sum('quantity'), integer_zero()),
        ).order_by('bucket', 'transaction_type')

        slow_moving = medicines.exclude(
            sale_items__sale__sale_date__gte=filters.date_from,
            sale_items__sale__sale_date__lte=filters.date_to,
        ).annotate(
            stock_value=ExpressionWrapper(
                F('stock_quantity') * F('purchase_price'),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ).filter(stock_quantity__gt=0).order_by('-stock_value', 'name')[:10]

        return {
            'summary': [
                {'key': 'cost_stock_value', 'label': 'Stock Value at Cost', 'restricted': not can_view_costs, **build_metric_payload(cost_stock, None, allow_change=False)} if can_view_costs else {
                    'key': 'cost_stock_value', 'label': 'Stock Value at Cost', 'restricted': True, 'value': None, 'previous_value': None, 'absolute_change': None, 'percentage_change': None, 'comparison_available': False,
                },
                {'key': 'retail_stock_value', 'label': 'Stock Value at Selling Price', **build_metric_payload(retail_stock, None, allow_change=False)},
                {'key': 'active_medicines', 'label': 'Active Medicines', **build_metric_payload(medicines.count(), None, allow_change=False)},
                {'key': 'available_batches', 'label': 'Available Batches', **build_metric_payload(active_batches.filter(quantity_on_hand__gt=0).count(), None, allow_change=False)},
                {'key': 'low_stock_items', 'label': 'Low-Stock Items', **build_metric_payload(low_stock.count(), None, allow_change=False)},
                {'key': 'out_of_stock_items', 'label': 'Out-of-stock Items', **build_metric_payload(out_of_stock.count(), None, allow_change=False)},
                {'key': 'expiring_soon', 'label': 'Expiring within 30 days', **build_metric_payload(expiry_30.count(), None, allow_change=False)},
                {'key': 'expired', 'label': 'Expired Batches', **build_metric_payload(expired.count(), None, allow_change=False)},
            ],
            'stock_status': {
                'healthy': medicines.filter(stock_quantity__gt=F('min_stock_level'), expiry_date__gte=today + timedelta(days=30)).count(),
                'low_stock': low_stock.count(),
                'out_of_stock': out_of_stock.count(),
                'expiring_soon': expiry_30.count(),
                'expired': expired.count(),
            },
            'low_stock': [
                {
                    'id': str(item.id),
                    'medicine': item.name,
                    'current_stock': item.stock_quantity,
                    'reorder_level': item.min_stock_level,
                    'shortage_quantity': max(item.min_stock_level - item.stock_quantity, 0),
                    'supplier': item.supplier.name,
                    'last_purchase_date': item.purchase_items.order_by('-purchase__purchase_date').values_list('purchase__purchase_date', flat=True).first(),
                }
                for item in low_stock.select_related('supplier')[:10]
            ],
            'expiry_monitoring': {
                'expired': [{'id': str(item.id), 'medicine': item.medicine.name, 'batch_number': item.batch_number, 'days_to_expiry': (item.expiry_date - today).days} for item in expired[:10]],
                'within_30_days': [{'id': str(item.id), 'medicine': item.medicine.name, 'batch_number': item.batch_number, 'days_to_expiry': (item.expiry_date - today).days} for item in expiry_30[:10]],
                'within_60_days': [{'id': str(item.id), 'medicine': item.medicine.name, 'batch_number': item.batch_number, 'days_to_expiry': (item.expiry_date - today).days} for item in active_batches.filter(quantity_on_hand__gt=0, expiry_date__gt=today + timedelta(days=30), expiry_date__lte=today + timedelta(days=60))[:10]],
                'within_90_days': [{'id': str(item.id), 'medicine': item.medicine.name, 'batch_number': item.batch_number, 'days_to_expiry': (item.expiry_date - today).days} for item in active_batches.filter(quantity_on_hand__gt=0, expiry_date__gt=today + timedelta(days=60), expiry_date__lte=today + timedelta(days=90))[:10]],
            },
            'stock_movements': [
                {
                    'label': item['bucket'].isoformat(),
                    'transaction_type': item['transaction_type'],
                    'quantity': item['quantity'],
                }
                for item in stock_movements
            ],
            'slow_moving': [
                {
                    'id': str(item.id),
                    'medicine': item.name,
                    'stock_quantity': item.stock_quantity,
                    'stock_value': float(item.stock_value),
                    'expiry_date': item.expiry_date.isoformat(),
                }
                for item in slow_moving
            ],
            'turnover': None,
        }
