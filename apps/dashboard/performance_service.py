from __future__ import annotations

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce

from apps.sales.models import Sale, SaleItem

from .query_utils import apply_sale_filters, cost_visibility


class PerformanceDashboardService:
    @staticmethod
    def get_data(user, filters):
        sales = apply_sale_filters(Sale.objects.select_related('served_by', 'customer'), filters)
        items = SaleItem.objects.filter(sale__in=sales)
        can_view_staff = user.is_superuser or user.has_permission('dashboard.performance.view_staff')
        can_view_profit = cost_visibility(user)

        cashier_performance = sales.values(
            'served_by_id',
            'served_by__username',
        ).annotate(
            revenue=Coalesce(Sum('net_amount'), 0),
            sales_count=Count('id'),
        ).order_by('-revenue', '-sales_count')

        customer_growth = sales.exclude(customer__isnull=True).values('customer_id').distinct().count()
        repeat_customer_count = sales.exclude(customer__isnull=True).values('customer_id').annotate(
            sale_count=Count('id')
        ).filter(sale_count__gt=1).count()

        gross_profit_expression = ExpressionWrapper(
            F('subtotal') - (F('quantity') * F('medicine__purchase_price')),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
        category_performance = items.values('medicine__category__name').annotate(
            revenue=Coalesce(Sum('subtotal'), 0),
            quantity_sold=Coalesce(Sum('quantity'), 0),
            gross_profit=Coalesce(Sum(gross_profit_expression), 0)
            if can_view_profit else Coalesce(Sum('subtotal'), 0),
        ).order_by('-revenue')

        return {
            'staff_visible': can_view_staff,
            'cashier_performance': [
                {
                    'staff_id': item['served_by_id'],
                    'name': item['served_by__username'],
                    'revenue': float(item['revenue']),
                    'sales_count': item['sales_count'],
                    'average_sale': float(item['revenue']) / item['sales_count'] if item['sales_count'] else 0,
                }
                for item in cashier_performance
            ] if can_view_staff else [],
            'category_performance': [
                {
                    'category': item['medicine__category__name'],
                    'revenue': float(item['revenue']),
                    'quantity_sold': item['quantity_sold'],
                    'gross_profit': float(item['gross_profit']) if can_view_profit else None,
                }
                for item in category_performance
            ],
            'growth_indicators': {
                'identified_customers': customer_growth,
                'repeat_customer_rate': (repeat_customer_count / customer_growth) * 100 if customer_growth else None,
                'average_basket_value': float(sales.aggregate(value=Coalesce(Sum('net_amount'), 0))['value']) / sales.count() if sales.count() else 0,
                'sales_volume': sales.count(),
            },
        }
