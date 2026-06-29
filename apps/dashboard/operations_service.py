from __future__ import annotations

from datetime import timedelta

from django.db.models import F
from django.utils import timezone

from apps.inventory.models import Medicine
from apps.sales.models import Sale
from apps.suppliers.models import Purchase

from .comparison import build_metric_payload
from .query_utils import apply_sale_filters


class OperationsDashboardService:
    @staticmethod
    def get_data(user, filters):
        today_start = timezone.make_aware(
            timezone.datetime.combine(
                timezone.localdate(),
                timezone.datetime.min.time(),
            )
        )
        sales_today = Sale.objects.filter(sale_date__gte=today_start)
        pending_sales = apply_sale_filters(Sale.objects.filter(payment_status__in=['pending', 'partial']), filters)
        pending_purchases = Purchase.objects.filter(payment_status__in=['pending', 'partial']).count()
        expiring_soon = Medicine.objects.filter(
            is_active=True,
            stock_quantity__gt=0,
            expiry_date__gte=timezone.localdate(),
            expiry_date__lte=timezone.localdate() + timedelta(days=30),
        ).count()

        return {
            'summary': [
                {'key': 'sales_today', 'label': 'Sales Completed Today', **build_metric_payload(sales_today.count(), None, allow_change=False)},
                {'key': 'pending_sales', 'label': 'Pending Sales', **build_metric_payload(pending_sales.count(), None, allow_change=False)},
                {'key': 'pending_purchase_payments', 'label': 'Purchase Balances Pending', **build_metric_payload(pending_purchases, None, allow_change=False)},
                {'key': 'failed_payments', 'label': 'Failed Payments', **build_metric_payload(0, None, allow_change=False)},
                {'key': 'returns_awaiting_review', 'label': 'Returns Requiring Review', **build_metric_payload(0, None, allow_change=False)},
                {'key': 'expiring_soon', 'label': 'Expiring Soon', **build_metric_payload(expiring_soon, None, allow_change=False)},
            ],
            'pending_actions': [
                {
                    'type': 'Payment follow-up',
                    'reference': sale.invoice_number,
                    'created_at': sale.sale_date.isoformat(),
                    'assigned_user': sale.served_by.username,
                    'priority': 'high' if sale.payment_status == 'pending' else 'medium',
                    'status': sale.payment_status,
                    'href': f'/dashboard/sales-billing/sales/{sale.id}',
                }
                for sale in pending_sales.select_related('served_by').order_by('sale_date')[:10]
            ],
            'procurement_snapshot': {
                'open_purchase_balances': pending_purchases,
                'recently_received_stock': Purchase.objects.filter(
                    purchase_date__gte=timezone.localdate() - timedelta(days=7)
                ).count(),
            },
            'exceptions': [
                {
                    'label': 'Low-stock medicines requiring reorder',
                    'count': Medicine.objects.filter(is_active=True, stock_quantity__lte=F('min_stock_level')).count(),
                    'status': 'requires_review',
                },
                {
                    'label': 'Expired stock still on shelves',
                    'count': Medicine.objects.filter(is_active=True, stock_quantity__gt=0, expiry_date__lt=timezone.localdate()).count(),
                    'status': 'critical',
                },
            ],
        }
