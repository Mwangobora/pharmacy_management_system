from __future__ import annotations

from datetime import timedelta

from django.db.models import DecimalField, Exists, ExpressionWrapper, F, IntegerField, OuterRef, Subquery, Sum, UUIDField, Value
from django.db.models.functions import Cast, Coalesce, TruncDate, TruncHour, TruncMonth, TruncWeek

from apps.inventory.models import Medicine, MedicineBatch, StockTransaction
from apps.sales.models import SaleItem


MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)
AVERAGE_FIELD = DecimalField(max_digits=12, decimal_places=2)


def money_zero():
    return Value(0, output_field=MONEY_FIELD)


def integer_zero():
    return Value(0, output_field=IntegerField())


def apply_sale_filters(queryset, filters):
    queryset = queryset.filter(sale_date__gte=filters.date_from, sale_date__lte=filters.date_to)
    if filters.cashier_id:
        queryset = queryset.filter(served_by_id=filters.cashier_id)
    if filters.payment_method:
        queryset = queryset.filter(payment_method=filters.payment_method)
    return queryset


def apply_payment_filters(queryset, filters):
    queryset = queryset.filter(payment_date__gte=filters.date_from, payment_date__lte=filters.date_to)
    if filters.cashier_id:
        queryset = queryset.filter(received_by_id=filters.cashier_id)
    if filters.payment_method:
        queryset = queryset.filter(payment_method=filters.payment_method)
    return queryset


def apply_purchase_filters(queryset, filters):
    return queryset.filter(
        purchase_date__gte=filters.date_from.date(),
        purchase_date__lte=filters.date_to.date(),
    )


def apply_stock_filters(queryset, filters):
    return queryset.filter(
        transaction_date__gte=filters.date_from,
        transaction_date__lte=filters.date_to,
    )


def cost_visibility(user):
    return (
        user.is_superuser
        or user.has_permission('dashboard.finance.view_profit')
        or user.has_permission('dashboard.inventory.view_cost_value')
        or user.has_permission('inventory.medicine.view_cost_price')
    )


def determine_granularity(filters):
    total_days = (filters.date_to.date() - filters.date_from.date()).days + 1
    if filters.preset in {'today', 'yesterday'} and total_days <= 1:
        return 'hour'
    if total_days <= 31:
        return 'day'
    if total_days <= 120:
        return 'week'
    return 'month'


def truncate_for_granularity(field_name, granularity):
    if granularity == 'hour':
        return TruncHour(field_name)
    if granularity == 'week':
        return TruncWeek(field_name)
    if granularity == 'month':
        return TruncMonth(field_name)
    return TruncDate(field_name)


def sale_item_cost_expression():
    return ExpressionWrapper(
        F('quantity') * F('cost_price_snapshot'),
        output_field=MONEY_FIELD,
    )


def refund_value_subquery():
    sale_item_total = SaleItem.objects.filter(
        sale_id=Cast(OuterRef('reference_id'), output_field=UUIDField()),
        medicine_id=OuterRef('medicine_id'),
    ).values('medicine_id').annotate(
        total_quantity=Coalesce(Sum('quantity'), integer_zero()),
        total_subtotal=Coalesce(Sum('subtotal'), money_zero()),
    ).annotate(
        average_unit_price=ExpressionWrapper(
            F('total_subtotal') / F('total_quantity'),
            output_field=AVERAGE_FIELD,
        )
    ).values('average_unit_price')[:1]

    return ExpressionWrapper(
        F('quantity') * Coalesce(Subquery(sale_item_total), money_zero()),
        output_field=MONEY_FIELD,
    )


def refund_transactions(filters):
    return apply_stock_filters(
        StockTransaction.objects.filter(
            transaction_type='return',
            reference_type='sale_refund',
        ),
        filters,
    )


def slow_moving_medicines(filters, *, limit=10):
    sales_in_range = SaleItem.objects.filter(
        sale__sale_date__gte=filters.date_from,
        sale__sale_date__lte=filters.date_to,
        medicine_id=OuterRef('pk'),
    )
    return Medicine.objects.filter(is_active=True).annotate(
        sold_in_period=Exists(sales_in_range),
        stock_value=ExpressionWrapper(
            F('stock_quantity') * F('purchase_price'),
            output_field=MONEY_FIELD,
        ),
    ).filter(
        stock_quantity__gt=0,
        sold_in_period=False,
    ).order_by('-stock_value', 'name')[:limit]
