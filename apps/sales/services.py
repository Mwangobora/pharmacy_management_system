from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Sum
from django.utils import timezone
from rest_framework import serializers

from apps.inventory.models import Medicine
from apps.inventory.selectors import (
    build_fefo_allocation_plan,
    convert_to_base_units,
    get_or_create_base_unit_conversion,
)
from apps.inventory.stock_service import decrease_batch_stock, increase_batch_stock

from .models import Payment, Sale, SaleItem, SaleItemBatchAllocation


class SalesService:
    @staticmethod
    def generate_invoice_number():
        last_sale = Sale.objects.order_by('-created_at').first()
        if last_sale and last_sale.invoice_number:
            try:
                last_num = int(last_sale.invoice_number.split('-')[-1])
                new_num = last_num + 1
            except Exception:
                new_num = 1
        else:
            new_num = 1
        return f"INV-{timezone.now().strftime('%Y%m%d')}-{new_num:04d}"

    @staticmethod
    def _resolve_sale_item(medicine, item_data):
        unit_name = item_data.get('unit_name') or medicine.base_unit or medicine.unit
        quantity_in_unit = int(item_data['quantity'])
        if medicine.selling_price is None:
            raise serializers.ValidationError(
                f'{medicine.name}: selling price must be configured before sale.'
            )
        conversion, quantity_base_units = convert_to_base_units(
            medicine,
            quantity_in_unit,
            unit_name,
            allow_sale=True,
        )
        allocation_plan = build_fefo_allocation_plan(
            medicine,
            quantity_base_units,
            requested_allocations=item_data.get('batch_allocations'),
        )
        unit_price = Decimal(str(medicine.selling_price))
        total_cost = sum(
            Decimal(plan.quantity) * Decimal(plan.batch.purchase_price)
            for plan in allocation_plan
        )
        total_revenue = Decimal(quantity_base_units) * unit_price
        return {
            'medicine': medicine,
            'conversion': conversion,
            'unit_name': unit_name,
            'quantity_in_unit': quantity_in_unit,
            'quantity_base_units': quantity_base_units,
            'unit_price': unit_price,
            'allocation_plan': allocation_plan,
            'cost_price_snapshot': (
                total_cost / Decimal(quantity_base_units)
            ).quantize(Decimal('0.01')),
            'profit_snapshot': (total_revenue - total_cost).quantize(Decimal('0.01')),
            'line_total': total_revenue,
        }

    @staticmethod
    def create_sale(user, data):
        items = data.get('items') or []
        transaction_ref = data.get('transaction_ref', '')
        tax_rate = Decimal(str(getattr(settings, 'SALES_TAX_PERCENT', '0')))

        with transaction.atomic():
            resolved_items = []
            total_amount = Decimal('0')

            for item_data in items:
                try:
                    medicine = Medicine.objects.select_for_update().get(pk=item_data['medicine'])
                except Medicine.DoesNotExist:
                    raise serializers.ValidationError(
                        f"Medicine with id {item_data['medicine']} not found"
                    )

                if not medicine.base_unit:
                    medicine.base_unit = medicine.unit or 'pieces'
                    medicine.save(update_fields=['base_unit', 'updated_at'])
                get_or_create_base_unit_conversion(medicine)

                resolved = SalesService._resolve_sale_item(medicine, item_data)
                resolved['discount_percent'] = Decimal(item_data.get('discount_percent', 0))
                resolved['tax_percent'] = Decimal(item_data.get('tax_percent', 0))
                total_amount += resolved['line_total']
                resolved_items.append(resolved)

            invoice_number = SalesService.generate_invoice_number()
            computed_tax_amount = (
                total_amount * tax_rate / Decimal('100')
            ).quantize(Decimal('0.01'))
            discount_amount = Decimal(data.get('discount_amount', 0))
            net_amount = total_amount + computed_tax_amount - discount_amount

            payment_amount = data.get('payment_amount')
            payment_amount = Decimal(payment_amount) if payment_amount is not None else net_amount

            if payment_amount >= net_amount:
                payment_status = 'paid'
            elif payment_amount > 0:
                payment_status = 'partial'
            else:
                payment_status = 'pending'

            sale = Sale.objects.create(
                customer=data.get('customer'),
                invoice_number=invoice_number,
                sale_date=data.get('sale_date') or timezone.now(),
                total_amount=total_amount,
                tax_amount=computed_tax_amount,
                discount_amount=discount_amount,
                net_amount=net_amount,
                payment_method=data['payment_method'],
                payment_status=payment_status,
                served_by=user,
                notes=data.get('notes', ''),
            )

            for resolved in resolved_items:
                batch_numbers = [plan.batch.batch_number for plan in resolved['allocation_plan']]
                sale_item = SaleItem.objects.create(
                    sale=sale,
                    medicine=resolved['medicine'],
                    unit_conversion=resolved['conversion'],
                    sold_unit_name=resolved['unit_name'],
                    sold_quantity_in_unit=resolved['quantity_in_unit'],
                    batch_number=batch_numbers[0] if len(batch_numbers) == 1 else 'MULTI',
                    quantity=resolved['quantity_base_units'],
                    unit_price=resolved['unit_price'],
                    selling_price_snapshot=resolved['unit_price'],
                    cost_price_snapshot=resolved['cost_price_snapshot'],
                    profit_snapshot=resolved['profit_snapshot'],
                    discount_percent=resolved['discount_percent'],
                    tax_percent=resolved['tax_percent'],
                )

                for plan in resolved['allocation_plan']:
                    decrease_batch_stock(
                        batch=plan.batch,
                        quantity=plan.quantity,
                        created_by=user,
                        transaction_type='sale',
                        reference_type='sale',
                        reference_id=str(sale.id),
                        notes=f'Sale {invoice_number}',
                        unit_conversion=resolved['conversion'],
                        quantity_in_unit=resolved['quantity_in_unit'],
                    )
                    SaleItemBatchAllocation.objects.create(
                        sale_item=sale_item,
                        batch=plan.batch,
                        quantity=plan.quantity,
                        cost_price_snapshot=plan.batch.purchase_price,
                        selling_price_snapshot=resolved['unit_price'],
                        total_cost_snapshot=(
                            Decimal(plan.quantity) * Decimal(plan.batch.purchase_price)
                        ).quantize(Decimal('0.01')),
                        total_revenue_snapshot=(
                            Decimal(plan.quantity) * resolved['unit_price']
                        ).quantize(Decimal('0.01')),
                    )

            if payment_amount > 0:
                Payment.objects.create(
                    sale=sale,
                    amount=payment_amount,
                    payment_method=data['payment_method'],
                    transaction_ref=transaction_ref,
                    received_by=user,
                )

            if sale.customer:
                divisor = getattr(settings, 'LOYALTY_TZS_PER_POINT', 1000)
                try:
                    points = int(Decimal(net_amount) / Decimal(divisor))
                except Exception:
                    points = int(net_amount // divisor)
                sale.customer.loyalty_points += points
                sale.customer.save()

            return sale

    @staticmethod
    def process_refund(sale, refund_amount, items_to_refund, user, reason=''):
        refund_amount = Decimal(refund_amount)
        total_paid = sale.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')

        if refund_amount <= 0:
            raise serializers.ValidationError('Refund amount must be greater than 0')
        if refund_amount > total_paid:
            raise serializers.ValidationError('Refund amount exceeds total paid')

        with transaction.atomic():
            returned_items = []
            refund_value_total = Decimal('0')

            for item in items_to_refund or []:
                sale_item_id = item.get('sale_item_id') or item.get('item_id')
                qty = int(item.get('quantity', 0) or 0)
                if not sale_item_id or qty <= 0:
                    continue

                try:
                    sale_item = SaleItem.objects.select_for_update().prefetch_related(
                        'batch_allocations__batch'
                    ).get(pk=sale_item_id, sale=sale)
                except SaleItem.DoesNotExist:
                    continue

                refundable_qty = sale_item.quantity - sale_item.refunded_quantity
                if qty > refundable_qty:
                    raise serializers.ValidationError(
                        f'Return quantity for item {sale_item_id} exceeds refundable quantity ({refundable_qty})'
                    )

                remaining = qty
                item_refund_value = Decimal('0')
                for allocation in sale_item.batch_allocations.select_for_update().all():
                    available = allocation.quantity - allocation.returned_quantity
                    if available <= 0 or remaining <= 0:
                        continue
                    restore_qty = min(available, remaining)
                    increase_batch_stock(
                        batch=allocation.batch,
                        quantity=restore_qty,
                        created_by=user,
                        transaction_type='return',
                        reference_type='sale_refund',
                        reference_id=str(sale.id),
                        notes=f'Refund for sale {sale.invoice_number}: {reason}',
                    )
                    allocation.returned_quantity += restore_qty
                    allocation.save(update_fields=['returned_quantity'])
                    remaining -= restore_qty
                    item_refund_value += (
                        Decimal(restore_qty) * Decimal(allocation.selling_price_snapshot)
                    )

                if remaining > 0:
                    raise serializers.ValidationError(
                        f'Could not restore the full quantity for sale item {sale_item_id}.'
                    )

                sale_item.refunded_quantity += qty
                sale_item.save(update_fields=['refunded_quantity'])
                refund_value_total += item_refund_value
                returned_items.append({
                    'item_id': sale_item_id,
                    'quantity': qty,
                    'medicine': sale_item.medicine.name,
                })

            if returned_items:
                sale.net_amount = max(Decimal('0.00'), Decimal(sale.net_amount) - refund_value_total)
            else:
                sale.net_amount = max(Decimal('0.00'), Decimal(sale.net_amount) - refund_amount)
            sale.save(update_fields=['net_amount'])

            new_total_paid = total_paid
            if new_total_paid >= sale.net_amount:
                sale.payment_status = 'paid'
            elif new_total_paid > 0:
                sale.payment_status = 'partial'
            else:
                sale.payment_status = 'pending'
            sale.save(update_fields=['payment_status'])

            return {
                'sale_id': str(sale.id),
                'refund_amount': float(refund_value_total or refund_amount),
                'returned_items': returned_items,
                'new_net_amount': float(sale.net_amount),
                'payment_status': sale.payment_status,
            }

    @staticmethod
    def daily_summary(date):
        sales = Sale.objects.filter(sale_date__date=date)
        allocations = SaleItemBatchAllocation.objects.filter(sale_item__sale__sale_date__date=date)
        return {
            'date': date,
            'total_sales': sales.count(),
            'total_revenue': float(sales.aggregate(total=Sum('net_amount'))['total'] or 0),
            'cash_sales': float(sales.filter(payment_method='cash').aggregate(total=Sum('net_amount'))['total'] or 0),
            'mobile_sales': float(sales.filter(payment_method='mobile').aggregate(total=Sum('net_amount'))['total'] or 0),
            'card_sales': float(sales.filter(payment_method='card').aggregate(total=Sum('net_amount'))['total'] or 0),
            'insurance_sales': float(sales.filter(payment_method='insurance').aggregate(total=Sum('net_amount'))['total'] or 0),
            'pending_payments': sales.filter(payment_status__in=['pending', 'partial']).count(),
            'items_sold': sales.aggregate(total=Sum('items__quantity'))['total'] or 0,
            'total_profit': float(
                allocations.aggregate(total=Sum('total_revenue_snapshot'))['total'] or 0
            ) - float(
                allocations.aggregate(total=Sum('total_cost_snapshot'))['total'] or 0
            ),
        }

    @staticmethod
    def top_selling(days=30, limit=10):
        start_date = timezone.now() - timezone.timedelta(days=days)
        top = SaleItem.objects.filter(sale__sale_date__gte=start_date).values(
            'medicine__name', 'medicine__id'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('subtotal'),
        ).order_by('-total_quantity')[:limit]
        return [
            {
                'medicine_id': str(item['medicine__id']),
                'medicine_name': item['medicine__name'],
                'total_quantity': item['total_quantity'],
                'total_revenue': float(item['total_revenue'] or 0),
            }
            for item in top
        ]

    @staticmethod
    def process_payment(sale, payment_amount, payment_method, user, transaction_ref='', notes=''):
        payment_amount = Decimal(payment_amount)
        total_paid = sale.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        amount_due = Decimal(sale.net_amount) - total_paid

        if payment_amount <= 0:
            raise serializers.ValidationError('Payment amount must be greater than 0')
        if payment_amount > amount_due:
            raise serializers.ValidationError(
                f'Payment amount ({payment_amount}) exceeds amount due ({amount_due})'
            )

        with transaction.atomic():
            Payment.objects.create(
                sale=sale,
                amount=payment_amount,
                payment_method=payment_method,
                transaction_ref=transaction_ref,
                notes=notes,
                received_by=user,
            )

            new_total_paid = total_paid + payment_amount
            sale.payment_status = 'paid' if new_total_paid >= sale.net_amount else 'partial'
            sale.save(update_fields=['payment_status'])

            return {
                'sale_id': str(sale.id),
                'amount_paid': float(payment_amount),
                'total_paid': float(new_total_paid),
                'amount_due': float(sale.net_amount - new_total_paid),
                'payment_status': sale.payment_status,
            }
