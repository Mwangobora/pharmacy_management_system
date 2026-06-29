from __future__ import annotations

from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce

from apps.sales.models import Payment, Sale, SaleItem
from apps.suppliers.models import Purchase

from .comparison import build_metric_payload
from .query_utils import apply_payment_filters, apply_purchase_filters, apply_sale_filters, cost_visibility, refund_transactions, refund_value_subquery, truncate_for_granularity, determine_granularity


class FinanceDashboardService:
    @staticmethod
    def get_data(user, filters):
        sales = apply_sale_filters(Sale.objects.all(), filters)
        items = SaleItem.objects.filter(sale__in=sales)
        payments = apply_payment_filters(Payment.objects.all(), filters)
        purchases = apply_purchase_filters(Purchase.objects.all(), filters)
        can_view_profit = cost_visibility(user)

        revenue = sales.aggregate(value=Coalesce(Sum('net_amount'), 0))['value']
        cogs = items.aggregate(value=Coalesce(Sum(ExpressionWrapper(
            F('quantity') * F('medicine__purchase_price'),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )), 0))['value'] if can_view_profit else None
        gross_profit = (revenue - cogs) if can_view_profit else None
        margin = ((gross_profit / revenue) * 100) if can_view_profit and revenue else None
        refund_value = refund_transactions(filters).annotate(
            estimated_value=refund_value_subquery()
        ).aggregate(value=Coalesce(Sum('estimated_value'), 0))['value']
        outstanding_credit = sales.filter(payment_status__in=['pending', 'partial']).aggregate(value=Coalesce(Sum('net_amount'), 0))['value']
        supplier_balances = purchases.filter(payment_status__in=['pending', 'partial']).aggregate(value=Coalesce(Sum('net_amount'), 0))['value']
        inflows = payments.values('payment_method').annotate(amount=Coalesce(Sum('amount'), 0)).order_by('-amount')
        trend = sales.values(
            bucket=truncate_for_granularity('sale_date', determine_granularity(filters))
        ).annotate(
            revenue=Coalesce(Sum('net_amount'), 0),
            refund_value=Coalesce(Sum('discount_amount'), 0),
        ).order_by('bucket')

        return {
            'summary': [
                {'key': 'revenue', 'label': 'Revenue', **build_metric_payload(revenue, None, allow_change=False)},
                {'key': 'cogs', 'label': 'Cost of Goods Sold', 'restricted': not can_view_profit, **build_metric_payload(cogs, None, allow_change=False)} if can_view_profit else {
                    'key': 'cogs', 'label': 'Cost of Goods Sold', 'restricted': True, 'value': None, 'previous_value': None, 'absolute_change': None, 'percentage_change': None, 'comparison_available': False,
                },
                {'key': 'gross_profit', 'label': 'Estimated Gross Profit', 'restricted': not can_view_profit, **build_metric_payload(gross_profit, None, allow_change=False)} if can_view_profit else {
                    'key': 'gross_profit', 'label': 'Estimated Gross Profit', 'restricted': True, 'value': None, 'previous_value': None, 'absolute_change': None, 'percentage_change': None, 'comparison_available': False,
                },
                {'key': 'gross_margin', 'label': 'Gross Margin %', 'restricted': not can_view_profit, **build_metric_payload(margin, None, allow_change=False)} if can_view_profit else {
                    'key': 'gross_margin', 'label': 'Gross Margin %', 'restricted': True, 'value': None, 'previous_value': None, 'absolute_change': None, 'percentage_change': None, 'comparison_available': False,
                },
                {'key': 'refund_value', 'label': 'Estimated Refund Value', **build_metric_payload(refund_value, None, allow_change=False)},
                {'key': 'outstanding_credit', 'label': 'Outstanding Credit', **build_metric_payload(outstanding_credit, None, allow_change=False)},
                {'key': 'supplier_balances', 'label': 'Supplier Balances', **build_metric_payload(supplier_balances, None, allow_change=False)},
            ],
            'trend': [
                {
                    'label': item['bucket'].isoformat(),
                    'revenue': float(item['revenue']),
                    'cogs': float(cogs or 0) if can_view_profit else None,
                    'gross_profit': float(gross_profit or 0) if can_view_profit else None,
                    'refund_value': float(item['refund_value']),
                }
                for item in trend
            ],
            'cash_flow': {
                'inflows': [{'payment_method': item['payment_method'], 'amount': float(item['amount'])} for item in inflows],
                'outflows': [
                    {'label': 'Supplier balances', 'amount': float(supplier_balances or 0)},
                    {'label': 'Estimated refunds', 'amount': float(refund_value or 0)},
                ],
            },
            'expense_data_available': False,
            'profit_visible': can_view_profit,
            'profitability': [],
        }
