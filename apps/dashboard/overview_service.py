from __future__ import annotations

from django.conf import settings
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce

from apps.inventory.models import Medicine
from apps.sales.models import Payment, Sale, SaleItem

from .comparison import build_metric_payload
from .query_utils import (
    apply_payment_filters,
    apply_sale_filters,
    cost_visibility,
    determine_granularity,
    integer_zero,
    money_zero,
    refund_transactions,
    refund_value_subquery,
    truncate_for_granularity,
)


class OverviewDashboardService:
    @staticmethod
    def get_data(user, filters):
        sales = apply_sale_filters(Sale.objects.select_related('customer', 'served_by'), filters)
        previous_filters = filters.__class__(
            **{
                **filters.__dict__,
                'date_from': filters.comparison_date_from,
                'date_to': filters.comparison_date_to,
            }
        )
        previous_sales = apply_sale_filters(Sale.objects.all(), previous_filters)
        payments = apply_payment_filters(Payment.objects.all(), filters)
        can_view_costs = cost_visibility(user)

        sale_item_queryset = SaleItem.objects.filter(sale__in=sales)
        previous_item_queryset = SaleItem.objects.filter(sale__in=previous_sales)
        gross_profit = None
        previous_gross_profit = None
        if can_view_costs:
            gross_profit = sale_item_queryset.aggregate(
                value=Coalesce(Sum(ExpressionWrapper(
                    F('subtotal') - (F('quantity') * F('medicine__purchase_price')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )), money_zero())
            )['value']
            previous_gross_profit = previous_item_queryset.aggregate(
                value=Coalesce(Sum(ExpressionWrapper(
                    F('subtotal') - (F('quantity') * F('medicine__purchase_price')),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )), money_zero())
            )['value']

        revenue = sales.aggregate(value=Coalesce(Sum('net_amount'), money_zero()))['value']
        previous_revenue = previous_sales.aggregate(value=Coalesce(Sum('net_amount'), money_zero()))['value']
        sales_count = sales.count()
        previous_count = previous_sales.count()
        avg_sale = revenue / sales_count if sales_count else 0
        previous_avg = previous_revenue / previous_count if previous_count else 0
        stock_value = Medicine.objects.filter(is_active=True).aggregate(
            value=Coalesce(Sum(ExpressionWrapper(
                F('stock_quantity') * F('purchase_price'),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )), money_zero())
        )['value'] if can_view_costs else None

        low_stock_count = Medicine.objects.filter(is_active=True, stock_quantity__lte=F('min_stock_level')).count()
        refund_events = refund_transactions(filters)
        refund_estimate = refund_events.annotate(
            estimated_value=refund_value_subquery()
        ).aggregate(value=Coalesce(Sum('estimated_value'), money_zero()))['value']
        due_amount = 0
        for sale in sales.filter(payment_status__in=['pending', 'partial']).prefetch_related('payments'):
            paid = sum(payment.amount for payment in sale.payments.all())
            due_amount += max(float(sale.net_amount) - float(paid), 0)

        kpis = [
            {'key': 'revenue', 'label': 'Total Revenue', **build_metric_payload(revenue, previous_revenue)},
            {'key': 'gross_profit', 'label': 'Estimated Gross Profit', 'restricted': not can_view_costs, **build_metric_payload(gross_profit, previous_gross_profit)} if can_view_costs else {
                'key': 'gross_profit', 'label': 'Estimated Gross Profit', 'restricted': True, 'value': None, 'previous_value': None, 'absolute_change': None, 'percentage_change': None, 'comparison_available': False,
            },
            {'key': 'sales_count', 'label': 'Recorded Sales', **build_metric_payload(sales_count, previous_count)},
            {'key': 'average_sale', 'label': 'Average Sale Value', **build_metric_payload(avg_sale, previous_avg)},
            {'key': 'stock_value', 'label': 'Current Stock Value', 'restricted': not can_view_costs, **build_metric_payload(stock_value, None, allow_change=False)} if can_view_costs else {
                'key': 'stock_value', 'label': 'Current Stock Value', 'restricted': True, 'value': None, 'previous_value': None, 'absolute_change': None, 'percentage_change': None, 'comparison_available': False,
            },
            {'key': 'low_stock', 'label': 'Low-Stock Items', **build_metric_payload(low_stock_count, None, allow_change=False)},
        ]

        granularity = determine_granularity(filters)
        gross_profit_expression = ExpressionWrapper(
            F('subtotal') - (F('quantity') * F('medicine__purchase_price')),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
        trend = sale_item_queryset.values(
            bucket=truncate_for_granularity('sale__sale_date', granularity)
        ).annotate(
            revenue=Coalesce(Sum('subtotal'), money_zero()),
            sales=Count('sale', distinct=True),
            gross_profit=Coalesce(Sum(gross_profit_expression), money_zero())
            if can_view_costs else Coalesce(Sum('subtotal'), money_zero()),
        ).order_by('bucket')

        alerts = [
            {
                'key': 'out_of_stock',
                'label': 'Out-of-stock medicines',
                'severity': 'critical',
                'count': Medicine.objects.filter(is_active=True, stock_quantity__lte=0).count(),
                'href': '/dashboard/inventory/medicines?stock_status=out_of_stock',
            },
            {
                'key': 'low_stock',
                'label': 'Low-stock medicines',
                'severity': 'high',
                'count': low_stock_count,
                'href': '/dashboard/inventory/medicines?stock_status=low_stock',
            },
            {
                'key': 'expired',
                'label': 'Expired medicines',
                'severity': 'critical',
                'count': Medicine.objects.filter(is_active=True, expiry_date__lt=filters.date_to.date(), stock_quantity__gt=0).count(),
                'href': '/dashboard/inventory/medicines?expiry_status=expired',
            },
            {
                'key': 'pending_payments',
                'label': 'Incomplete customer payments',
                'severity': 'medium',
                'count': sales.filter(payment_status__in=['pending', 'partial']).count(),
                'href': '/dashboard/sales-billing/sales?payment_status=partial',
            },
        ]

        top_selling = sale_item_queryset.values(
            'medicine_id',
            'medicine__name',
            'medicine__generic_name',
        ).annotate(
            quantity_sold=Coalesce(Sum('quantity'), integer_zero()),
            revenue=Coalesce(Sum('subtotal'), money_zero()),
            gross_profit=Coalesce(Sum(gross_profit_expression), money_zero())
            if can_view_costs else Coalesce(Sum('subtotal'), money_zero()),
        ).order_by('-quantity_sold', '-revenue')[:5]

        recent_sales = sales.order_by('-sale_date')[:8]
        payment_breakdown = payments.values('payment_method').annotate(
            revenue=Coalesce(Sum('amount'), money_zero()),
            transactions=Count('id'),
        ).order_by('-revenue')

        return {
            'period': {
                'preset': filters.preset,
                'date_from': filters.date_from.date().isoformat(),
                'date_to': filters.date_to.date().isoformat(),
                'comparison_date_from': filters.comparison_date_from.date().isoformat(),
                'comparison_date_to': filters.comparison_date_to.date().isoformat(),
                'label': filters.label,
                'currency': getattr(settings, 'DEFAULT_CURRENCY_CODE', 'TZS'),
                'updated_at': filters.date_to.isoformat(),
            },
            'summary': kpis,
            'trend': {
                'granularity': granularity,
                'series': [
                    {
                        'label': item['bucket'].isoformat(),
                        'revenue': float(item['revenue']),
                        'gross_profit': float(item['gross_profit']) if can_view_costs else None,
                        'sales': item['sales'],
                    }
                    for item in trend
                ],
            },
            'profit_summary': {
                'revenue': float(revenue),
                'estimated_gross_profit': float(gross_profit or 0) if can_view_costs else None,
                'refund_estimate': float(refund_estimate or 0),
                'outstanding_balance': due_amount,
                'expense_data_available': False,
            },
            'alerts': [item for item in alerts if item['count'] > 0],
            'top_selling': [
                {
                    'medicine_id': str(item['medicine_id']),
                    'name': item['medicine__name'],
                    'generic_name': item['medicine__generic_name'],
                    'quantity_sold': item['quantity_sold'],
                    'revenue': float(item['revenue']),
                    'gross_profit': float(item['gross_profit']) if can_view_costs else None,
                }
                for item in top_selling
            ],
            'recent_sales': [
                {
                    'id': str(sale.id),
                    'invoice_number': sale.invoice_number,
                    'sale_date': sale.sale_date.isoformat(),
                    'customer_name': sale.customer.full_name if sale.customer else 'Walk-in',
                    'cashier': sale.served_by.username,
                    'items_count': sale.items.count(),
                    'payment_method': sale.payment_method,
                    'total': float(sale.net_amount),
                    'status': sale.payment_status,
                }
                for sale in recent_sales
            ],
            'payment_breakdown': [
                {
                    'payment_method': item['payment_method'],
                    'revenue': float(item['revenue']),
                    'transactions': item['transactions'],
                }
                for item in payment_breakdown
            ],
        }
