from __future__ import annotations

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce, ExtractHour, ExtractWeekDay

from apps.inventory.models import Medicine
from apps.sales.models import Payment, Sale, SaleItem

from .comparison import build_metric_payload
from .query_utils import (
    apply_payment_filters,
    apply_sale_filters,
    cost_visibility,
    determine_granularity,
    refund_transactions,
    refund_value_subquery,
    truncate_for_granularity,
)


class SalesDashboardService:
    @staticmethod
    def get_data(user, filters):
        sales = apply_sale_filters(Sale.objects.all(), filters)
        previous_filters = filters.__class__(
            **{
                **filters.__dict__,
                'date_from': filters.comparison_date_from,
                'date_to': filters.comparison_date_to,
            }
        )
        previous_sales = apply_sale_filters(Sale.objects.all(), previous_filters)
        items = SaleItem.objects.filter(sale__in=sales)
        payments = apply_payment_filters(Payment.objects.all(), filters)
        can_view_profit = cost_visibility(user)

        revenue = sales.aggregate(value=Coalesce(Sum('net_amount'), 0))['value']
        previous_revenue = previous_sales.aggregate(value=Coalesce(Sum('net_amount'), 0))['value']
        sales_count = sales.count()
        items_sold = items.aggregate(value=Coalesce(Sum('quantity'), 0))['value']
        discounts = sales.aggregate(value=Coalesce(Sum('discount_amount'), 0))['value']
        refunds = refund_transactions(filters).annotate(
            estimated_value=refund_value_subquery()
        ).aggregate(
            value=Coalesce(Sum('estimated_value'), 0),
            count=Count('id'),
        )
        credit_sales = sales.filter(payment_method='credit').aggregate(value=Coalesce(Sum('net_amount'), 0))['value']
        average_sale = (revenue / sales_count) if sales_count else 0
        previous_average = (previous_revenue / previous_sales.count()) if previous_sales.count() else 0

        trend = items.values(
            bucket=truncate_for_granularity('sale__sale_date', determine_granularity(filters))
        ).annotate(
            revenue=Coalesce(Sum('subtotal'), 0),
            quantity_sold=Coalesce(Sum('quantity'), 0),
            average_sale=Coalesce(Sum('sale__net_amount'), 0) / Count('sale', distinct=True),
            discount_value=Coalesce(Sum('sale__discount_amount'), 0),
        ).order_by('bucket')

        top_by_quantity = items.values(
            'medicine_id', 'medicine__name', 'medicine__generic_name'
        ).annotate(
            quantity_sold=Coalesce(Sum('quantity'), 0),
            revenue=Coalesce(Sum('subtotal'), 0),
        ).order_by('-quantity_sold', '-revenue')[:10]

        top_by_revenue = items.values(
            'medicine_id', 'medicine__name', 'medicine__generic_name'
        ).annotate(
            quantity_sold=Coalesce(Sum('quantity'), 0),
            revenue=Coalesce(Sum('subtotal'), 0),
        ).order_by('-revenue', '-quantity_sold')[:10]

        top_by_profit = []
        if can_view_profit:
            top_by_profit = items.values(
                'medicine_id', 'medicine__name', 'medicine__generic_name'
            ).annotate(
                gross_profit=Coalesce(Sum(ExpressionWrapper(
                    F('subtotal') - (F('quantity') * F('medicine__purchase_price')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )), 0),
                revenue=Coalesce(Sum('subtotal'), 0),
            ).order_by('-gross_profit', '-revenue')[:10]

        slow_moving = Medicine.objects.filter(is_active=True).exclude(
            sale_items__sale__sale_date__gte=filters.date_from,
            sale_items__sale__sale_date__lte=filters.date_to,
        ).annotate(
            stock_value=ExpressionWrapper(
                F('stock_quantity') * F('purchase_price'),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ).filter(stock_quantity__gt=0).order_by('-stock_value', 'name')[:10]

        by_category = items.values('medicine__category__name').annotate(
            revenue=Coalesce(Sum('subtotal'), 0),
            quantity_sold=Coalesce(Sum('quantity'), 0),
        ).order_by('-revenue')

        payment_methods = payments.values('payment_method').annotate(
            transactions=Count('id'),
            revenue=Coalesce(Sum('amount'), 0),
        ).order_by('-revenue')

        by_hour = sales.annotate(hour=ExtractHour('sale_date')).values('hour').annotate(
            sales=Count('id'),
            revenue=Coalesce(Sum('net_amount'), 0),
        ).order_by('hour')
        by_weekday = sales.annotate(weekday=ExtractWeekDay('sale_date')).values('weekday').annotate(
            sales=Count('id'),
            revenue=Coalesce(Sum('net_amount'), 0),
        ).order_by('weekday')

        return {
            'summary': [
                {'key': 'revenue', 'label': 'Sales Revenue', **build_metric_payload(revenue, previous_revenue)},
                {'key': 'sales_count', 'label': 'Recorded Sales', **build_metric_payload(sales_count, previous_sales.count())},
                {'key': 'average_sale', 'label': 'Average Basket Value', **build_metric_payload(average_sale, previous_average)},
                {'key': 'items_sold', 'label': 'Items Sold', **build_metric_payload(items_sold, None, allow_change=False)},
                {'key': 'refund_amount', 'label': 'Estimated Refund Value', **build_metric_payload(refunds['value'], None, allow_change=False)},
                {'key': 'discounts', 'label': 'Discount Value', **build_metric_payload(discounts, None, allow_change=False)},
                {'key': 'credit_sales', 'label': 'Credit Sales', **build_metric_payload(credit_sales, None, allow_change=False)},
            ],
            'trend': [
                {
                    'label': item['bucket'].isoformat(),
                    'revenue': float(item['revenue']),
                    'quantity_sold': item['quantity_sold'],
                    'average_sale': float(item['average_sale'] or 0),
                    'discount_value': float(item['discount_value']),
                }
                for item in trend
            ],
            'sales_by_time': {
                'by_hour': [{'hour': item['hour'], 'sales': item['sales'], 'revenue': float(item['revenue'])} for item in by_hour],
                'by_weekday': [{'weekday': item['weekday'], 'sales': item['sales'], 'revenue': float(item['revenue'])} for item in by_weekday],
            },
            'top_by_quantity': list(top_by_quantity),
            'top_by_revenue': list(top_by_revenue),
            'top_by_profit': [
                {
                    **item,
                    'gross_profit': float(item['gross_profit']),
                    'revenue': float(item['revenue']),
                }
                for item in top_by_profit
            ] if can_view_profit else [],
            'slow_moving': [
                {
                    'medicine_id': str(item.id),
                    'name': item.name,
                    'generic_name': item.generic_name,
                    'stock_quantity': item.stock_quantity,
                    'stock_value': float(item.stock_value),
                }
                for item in slow_moving
            ],
            'by_category': [
                {
                    'category': item['medicine__category__name'],
                    'revenue': float(item['revenue']),
                    'quantity_sold': item['quantity_sold'],
                }
                for item in by_category
            ],
            'payment_methods': [
                {
                    'payment_method': item['payment_method'],
                    'transactions': item['transactions'],
                    'revenue': float(item['revenue']),
                }
                for item in payment_methods
            ],
            'profit_visible': can_view_profit,
            'refund_events': refunds['count'],
        }
