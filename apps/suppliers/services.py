"""
Service layer for supplier and purchase operations.

Handles business logic for:
- Purchase creation with items
- Receiving items and updating stock
- Payment status updates
- Dashboard statistics
"""
from decimal import Decimal
from datetime import date
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Purchase, PurchaseItem
from apps.inventory.models import StockTransaction, Medicine
from rest_framework import serializers


class SupplierService:
    """Business logic for supplier management."""

    @staticmethod
    def get_supplier_stats(supplier):
        """Get supplier statistics.

        Returns:
        - total_purchases: Count of purchases
        - total_amount_spent: Total amount spent
        - pending_payments: Amount still owed
        - active_medicines: Count of active medicines from supplier
        - last_purchase_date: Most recent purchase date
        """
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
                if supplier.purchases.exists() else None
        }


class PurchaseService:
    """Business logic for purchase operations."""

    @staticmethod
    def create_purchase_with_items(user, data):
        """Create a purchase with items in one transaction.

        Expected data keys: supplier, invoice_number, purchase_date, items,
        tax_amount, discount_amount, payment_status, notes
        """
        items_data = data.get('items') or []

        with transaction.atomic():
            # Calculate total from items
            total_amount = Decimal('0')
            for item in items_data:
                qty = Decimal(item['quantity'])
                unit_price = Decimal(item['unit_price'])
                total_amount += qty * unit_price

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
                created_by=user
            )

            # Create purchase items
            for item_data in items_data:
                purchase_item = PurchaseItem.objects.create(
                    purchase=purchase,
                    medicine_id=item_data['medicine'],
                    quantity=item_data['quantity'],
                    unit_price=Decimal(item_data['unit_price']),
                    discount_percent=Decimal(item_data.get('discount_percent', 0)),
                    tax_percent=Decimal(item_data.get('tax_percent', 0))
                )

                # Treat procurement as the source of truth for stock and cost.
                received_qty = int(item_data['quantity'])
                purchase_item.received_quantity = received_qty
                purchase_item.save(update_fields=['received_quantity'])

                medicine = Medicine.objects.select_for_update().get(pk=item_data['medicine'])
                old_stock = int(medicine.stock_quantity or 0)
                old_cost = Decimal(medicine.purchase_price or 0)
                new_cost = Decimal(item_data['unit_price'])

                # Weighted average cost update.
                total_old_value = old_cost * Decimal(old_stock)
                total_new_value = new_cost * Decimal(received_qty)
                combined_qty = old_stock + received_qty
                weighted_cost = (total_old_value + total_new_value) / Decimal(combined_qty) if combined_qty > 0 else new_cost

                medicine.purchase_price = weighted_cost.quantize(Decimal('0.01'))

                # Keep selling price populated (manager can adjust later in inventory).
                if not medicine.selling_price or medicine.selling_price <= Decimal('0'):
                    medicine.selling_price = max(
                        medicine.purchase_price + Decimal('0.01'),
                        (medicine.purchase_price * Decimal('1.20')).quantize(Decimal('0.01'))
                    )

                # Optional batch/expiry provided by procurement flow updates medicine lot metadata.
                batch_number = item_data.get('batch_number')
                expiry_date = item_data.get('expiry_date')
                manufacture_date = item_data.get('manufacture_date')

                if batch_number:
                    medicine.batch_number = batch_number
                if expiry_date:
                    medicine.expiry_date = date.fromisoformat(expiry_date) if isinstance(expiry_date, str) else expiry_date
                if manufacture_date:
                    medicine.manufacture_date = date.fromisoformat(manufacture_date) if isinstance(manufacture_date, str) else manufacture_date

                medicine.save()

                StockTransaction.objects.create(
                    medicine=medicine,
                    transaction_type='purchase',
                    quantity=received_qty,
                    reference_type='purchase',
                    reference_id=purchase.id,
                    notes=f'Received from purchase {purchase.invoice_number}',
                    created_by=user
                )

            return purchase

    @staticmethod
    def receive_items(purchase, items_to_receive, user):
        """Mark items as received and update stock.

        Args:
            purchase: Purchase instance
            items_to_receive: List of {'item_id': id, 'received_quantity': qty}
            user: User processing the receipt

        Returns:
            Dictionary with receipt results
        """
        with transaction.atomic():
            received_items = []
            for item_data in items_to_receive:
                item_id = item_data['item_id']
                received_qty = int(item_data['received_quantity'])

                try:
                    item = PurchaseItem.objects.select_for_update().get(
                        pk=item_id,
                        purchase=purchase
                    )
                except PurchaseItem.DoesNotExist:
                    raise serializers.ValidationError(f'Purchase item {item_id} not found')

                if received_qty > item.quantity:
                    raise serializers.ValidationError(
                        f'Received quantity ({received_qty}) exceeds ordered quantity ({item.quantity})'
                    )

                outstanding_qty = item.quantity - item.received_quantity
                if received_qty > outstanding_qty:
                    raise serializers.ValidationError(
                        f'Received quantity ({received_qty}) exceeds outstanding quantity ({outstanding_qty})'
                    )

                # Update received quantity cumulatively
                item.received_quantity = item.received_quantity + received_qty
                item.save()

                # Create stock transaction (increases stock)
                StockTransaction.objects.create(
                    medicine=item.medicine,
                    transaction_type='purchase',
                    quantity=received_qty,
                    reference_type='purchase',
                    reference_id=purchase.id,
                    notes=f'Received from purchase {purchase.invoice_number}',
                    created_by=user
                )

                received_items.append({
                    'item_id': item_id,
                    'medicine': item.medicine.name,
                    'received_quantity': received_qty
                })

            return {
                'purchase_id': purchase.id,
                'received_items': received_items
            }

    @staticmethod
    def get_purchase_dashboard_stats(queryset):
        """Get purchase dashboard statistics.

        Returns:
        - total_purchases: Count
        - total_amount: Sum of net amounts
        - pending_amount: Pending/partial payments
        - paid_amount: Paid amounts
        - recent_purchases_count: Last 30 days
        """
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
            ).count()
        }
