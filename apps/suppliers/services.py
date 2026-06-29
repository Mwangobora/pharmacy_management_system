"""
Service layer for supplier and purchase operations.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from apps.inventory.models import Medicine, MedicineBatch
from apps.inventory.selectors import (
    convert_to_base_units,
    get_or_create_base_unit_conversion,
)
from apps.inventory.stock_service import increase_batch_stock

from .models import Purchase, PurchaseItem


class SupplierService:
    """Business logic for supplier management."""

    @staticmethod
    def get_supplier_stats(supplier):
        return {
            'total_purchases': supplier.purchases.count(),
            'total_amount_spent': supplier.purchases.aggregate(
                total=Sum('net_amount')
            )['total'] or Decimal('0'),
            'pending_payments': supplier.purchases.filter(
                payment_status__in=['pending', 'partial']
            ).aggregate(
                total=Sum('net_amount')
            )['total'] or Decimal('0'),
            'active_medicines': supplier.medicines.filter(is_active=True).count(),
            'last_purchase_date': supplier.purchases.order_by('-purchase_date').first().purchase_date
            if supplier.purchases.exists() else None,
        }


class PurchaseService:
    """Business logic for purchase operations."""

    @staticmethod
    def _resolve_purchase_item_quantity(medicine, item_data):
        unit_name = item_data.get('unit_name') or medicine.base_unit or medicine.unit
        quantity_in_unit = int(item_data['quantity'])
        conversion, quantity_base_units = convert_to_base_units(
            medicine,
            quantity_in_unit,
            unit_name,
            allow_purchase=True,
        )
        entered_unit_price = Decimal(str(item_data['unit_price']))
        cost_per_base_unit = (
            entered_unit_price / Decimal(conversion.factor_to_base_unit)
        ).quantize(Decimal('0.01'))
        return conversion, unit_name, quantity_in_unit, quantity_base_units, cost_per_base_unit

    @staticmethod
    def _build_batch(medicine, purchase, item_data, cost_per_base_unit):
        batch_number = item_data.get('batch_number') or (
            f'PUR-{purchase.invoice_number}-{medicine.id.hex[:8].upper()}'
        )
        expiry_date = item_data.get('expiry_date')
        manufacture_date = item_data.get('manufacture_date')

        if isinstance(expiry_date, str):
            expiry_date = date.fromisoformat(expiry_date)
        if isinstance(manufacture_date, str):
            manufacture_date = date.fromisoformat(manufacture_date)

        return MedicineBatch.objects.create(
            medicine=medicine,
            supplier=purchase.supplier,
            batch_number=batch_number,
            manufacture_date=manufacture_date,
            expiry_date=expiry_date,
            purchase_price=cost_per_base_unit,
            selling_price=medicine.selling_price,
            quantity_received=0,
            quantity_on_hand=0,
            notes=f'Created from purchase {purchase.invoice_number}',
        )

    @staticmethod
    def create_purchase_with_items(user, data):
        items_data = data.get('items') or []

        with transaction.atomic():
            resolved_items = []
            total_amount = Decimal('0')

            for item_data in items_data:
                medicine = Medicine.objects.select_for_update().get(pk=item_data['medicine'])
                if not medicine.base_unit:
                    medicine.base_unit = medicine.unit or 'pieces'
                    medicine.save(update_fields=['base_unit', 'updated_at'])
                get_or_create_base_unit_conversion(medicine)

                conversion, unit_name, quantity_in_unit, quantity_base_units, cost_per_base_unit = (
                    PurchaseService._resolve_purchase_item_quantity(medicine, item_data)
                )
                total_amount += Decimal(quantity_base_units) * cost_per_base_unit
                resolved_items.append({
                    'medicine': medicine,
                    'conversion': conversion,
                    'unit_name': unit_name,
                    'quantity_in_unit': quantity_in_unit,
                    'quantity_base_units': quantity_base_units,
                    'cost_per_base_unit': cost_per_base_unit,
                    'discount_percent': Decimal(item_data.get('discount_percent', 0)),
                    'tax_percent': Decimal(item_data.get('tax_percent', 0)),
                    'batch_number': item_data.get('batch_number'),
                    'expiry_date': item_data.get('expiry_date'),
                    'manufacture_date': item_data.get('manufacture_date'),
                })

            tax_amount = Decimal(data.get('tax_amount', 0))
            discount_amount = Decimal(data.get('discount_amount', 0))
            net_amount = total_amount + tax_amount - discount_amount

            purchase = Purchase.objects.create(
                supplier=data['supplier'],
                invoice_number=data['invoice_number'],
                purchase_date=data['purchase_date'],
                total_amount=total_amount,
                tax_amount=tax_amount,
                discount_amount=discount_amount,
                net_amount=net_amount,
                payment_status=data.get('payment_status', 'pending'),
                notes=data.get('notes', ''),
                created_by=user,
            )

            for item in resolved_items:
                medicine = item['medicine']
                purchase_item = PurchaseItem.objects.create(
                    purchase=purchase,
                    medicine=medicine,
                    quantity=item['quantity_base_units'],
                    quantity_base_units=item['quantity_base_units'],
                    quantity_in_unit=item['quantity_in_unit'],
                    unit_conversion=item['conversion'],
                    unit_name=item['unit_name'],
                    unit_price=item['cost_per_base_unit'],
                    cost_price_snapshot=item['cost_per_base_unit'],
                    discount_percent=item['discount_percent'],
                    tax_percent=item['tax_percent'],
                    received_quantity=0,
                )

                batch = PurchaseService._build_batch(
                    medicine,
                    purchase,
                    item,
                    item['cost_per_base_unit'],
                )
                purchase_item.batch = batch
                purchase_item.received_quantity = item['quantity_base_units']
                purchase_item.save(update_fields=['batch', 'received_quantity'])

                increase_batch_stock(
                    batch=batch,
                    quantity=item['quantity_base_units'],
                    created_by=user,
                    transaction_type='purchase',
                    reference_type='purchase',
                    reference_id=str(purchase.id),
                    notes=f'Received from purchase {purchase.invoice_number}',
                    unit_conversion=item['conversion'],
                    quantity_in_unit=item['quantity_in_unit'],
                    increase_received=True,
                )

                medicine.refresh_from_db(fields=['selling_price'])
                if not medicine.selling_price or medicine.selling_price <= Decimal('0'):
                    medicine.selling_price = max(
                        item['cost_per_base_unit'] + Decimal('0.01'),
                        (item['cost_per_base_unit'] * Decimal('1.20')).quantize(Decimal('0.01')),
                    )
                    medicine.save(update_fields=['selling_price', 'updated_at'])

            return purchase

    @staticmethod
    def receive_items(purchase, items_to_receive, user):
        with transaction.atomic():
            received_items = []
            for item_data in items_to_receive:
                item_id = item_data['item_id']
                received_qty = int(item_data['received_quantity'])

                try:
                    item = PurchaseItem.objects.select_for_update().select_related(
                        'medicine',
                        'batch',
                        'unit_conversion',
                        'purchase__supplier',
                    ).get(pk=item_id, purchase=purchase)
                except PurchaseItem.DoesNotExist:
                    raise serializers.ValidationError(f'Purchase item {item_id} not found')

                if received_qty <= 0:
                    raise serializers.ValidationError('Received quantity must be greater than 0')

                outstanding_qty = item.quantity - item.received_quantity
                if received_qty > outstanding_qty:
                    raise serializers.ValidationError(
                        f'Received quantity ({received_qty}) exceeds outstanding quantity ({outstanding_qty})'
                    )

                batch = item.batch
                if not batch:
                    batch = MedicineBatch.objects.create(
                        medicine=item.medicine,
                        supplier=purchase.supplier,
                        batch_number=item.medicine.batch_number,
                        manufacture_date=item.medicine.manufacture_date,
                        expiry_date=item.medicine.expiry_date,
                        purchase_price=item.cost_price_snapshot or item.unit_price,
                        selling_price=item.medicine.selling_price,
                        quantity_received=0,
                        quantity_on_hand=0,
                        notes=f'Backfilled batch for purchase {purchase.invoice_number}',
                    )
                    item.batch = batch

                increase_batch_stock(
                    batch=batch,
                    quantity=received_qty,
                    created_by=user,
                    transaction_type='purchase',
                    reference_type='purchase',
                    reference_id=str(purchase.id),
                    notes=f'Additional receipt from purchase {purchase.invoice_number}',
                    unit_conversion=item.unit_conversion,
                    quantity_in_unit=received_qty,
                    increase_received=True,
                )

                item.received_quantity += received_qty
                item.save(update_fields=['batch', 'received_quantity'])

                received_items.append({
                    'item_id': item_id,
                    'medicine': item.medicine.name,
                    'received_quantity': received_qty,
                    'batch_number': batch.batch_number,
                })

            return {
                'purchase_id': purchase.id,
                'received_items': received_items,
            }

    @staticmethod
    def get_purchase_dashboard_stats(queryset):
        return {
            'total_purchases': queryset.count(),
            'total_amount': queryset.aggregate(total=Sum('net_amount'))['total'] or Decimal('0'),
            'pending_amount': queryset.filter(
                payment_status__in=['pending', 'partial']
            ).aggregate(total=Sum('net_amount'))['total'] or Decimal('0'),
            'paid_amount': queryset.filter(
                payment_status='paid'
            ).aggregate(total=Sum('net_amount'))['total'] or Decimal('0'),
            'recent_purchases_count': queryset.filter(
                purchase_date__gte=timezone.now().date() - timezone.timedelta(days=30)
            ).count(),
        }
