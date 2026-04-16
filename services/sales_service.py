from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum
from rest_framework import serializers

from sales.models import Sale, SaleItem, Payment
from inventory.models import Medicine, StockTransaction
from django.conf import settings


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
    def create_sale(user, data):
        """Create a Sale with items and payment in a single transaction.

        Expected `data` keys: items (list), payment_amount (Decimal), transaction_ref,
        sale_date, customer (optional), payment_method, tax_amount, discount_amount, notes
        """
        items = data.get('items') or []
        transaction_ref = data.get('transaction_ref', '')

        total_amount = Decimal('0')
        tax_rate = Decimal(str(getattr(settings, 'SALES_TAX_PERCENT', '0')))

        with transaction.atomic():
            # Lock medicines and compute totals
            for item in items:
                try:
                    medicine = Medicine.objects.select_for_update().get(pk=item['medicine'])
                except Medicine.DoesNotExist:
                    raise serializers.ValidationError(f"Medicine with id {item['medicine']} not found")

                qty = int(item['quantity'])
                if medicine.stock_quantity < qty:
                    raise serializers.ValidationError(f"{medicine.name}: Insufficient stock (Available: {medicine.stock_quantity})")

                # Cashier flow: price is sourced from inventory policy.
                unit_price = Decimal(medicine.selling_price)
                discount_percent = Decimal(item.get('discount_percent', 0))
                tax_percent = Decimal(item.get('tax_percent', 0))

                base_amount = unit_price * qty
                discount = base_amount * (discount_percent / Decimal('100'))
                tax = (base_amount - discount) * (tax_percent / Decimal('100'))
                total_amount += base_amount - discount + tax

            invoice_number = SalesService.generate_invoice_number()

            computed_tax_amount = (total_amount * tax_rate / Decimal('100')).quantize(Decimal('0.01'))
            tax_amount = computed_tax_amount
            discount_amount = Decimal(data.get('discount_amount', 0))
            net_amount = total_amount + tax_amount - discount_amount

            payment_amount = data.get('payment_amount')
            payment_amount = Decimal(payment_amount) if payment_amount is not None else net_amount

            # Determine payment status
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
                tax_amount=tax_amount,
                discount_amount=discount_amount,
                net_amount=net_amount,
                payment_method=data['payment_method'],
                payment_status=payment_status,
                served_by=user,
                notes=data.get('notes', '')
            )

            # Create sale items and stock transactions
            for item in items:
                medicine = Medicine.objects.get(pk=item['medicine'])
                qty = int(item['quantity'])
                unit_price = Decimal(medicine.selling_price)
                discount_percent = Decimal(item.get('discount_percent', 0))
                tax_percent = Decimal(item.get('tax_percent', 0))
                batch_number = item.get('batch_number') or medicine.batch_number

                SaleItem.objects.create(
                    sale=sale,
                    medicine=medicine,
                    batch_number=batch_number,
                    quantity=qty,
                    unit_price=unit_price,
                    discount_percent=discount_percent,
                    tax_percent=tax_percent
                )

                StockTransaction.objects.create(
                    medicine=medicine,
                    transaction_type='sale',
                    quantity=qty,
                    reference_type='sale',
                    reference_id=sale.id,
                    notes=f'Sale {invoice_number}',
                    created_by=user
                )

            if payment_amount > 0:
                Payment.objects.create(
                    sale=sale,
                    amount=payment_amount,
                    payment_method=data['payment_method'],
                    transaction_ref=transaction_ref,
                    received_by=user
                )

            # Loyalty points
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
            for item in items_to_refund or []:
                item_id = item.get('item_id')
                qty = int(item.get('quantity', 0) or 0)
                if not item_id or qty <= 0:
                    continue
                try:
                    sale_item = SaleItem.objects.select_for_update().get(pk=item_id, sale=sale)
                except SaleItem.DoesNotExist:
                    continue

                if qty > sale_item.quantity:
                    raise serializers.ValidationError(f'Return quantity for item {item_id} exceeds sold quantity')

                StockTransaction.objects.create(
                    medicine=sale_item.medicine,
                    transaction_type='return',
                    quantity=qty,
                    reference_type='sale_refund',
                    reference_id=sale.id,
                    notes=f'Refund for sale {sale.invoice_number}: {reason}',
                    created_by=user
                )

                returned_items.append({'item_id': item_id, 'quantity': qty, 'medicine': sale_item.medicine.name})

            sale.net_amount = Decimal(sale.net_amount) - refund_amount
            if sale.net_amount < 0:
                sale.net_amount = Decimal('0')
            sale.save()

            new_total_paid = total_paid
            if new_total_paid >= sale.net_amount:
                sale.payment_status = 'paid'
            elif new_total_paid > 0:
                sale.payment_status = 'partial'
            else:
                sale.payment_status = 'pending'
            sale.save()

            return {
                'sale_id': sale.sale_id,
                'refund_amount': float(refund_amount),
                'returned_items': returned_items,
                'new_net_amount': float(sale.net_amount),
                'payment_status': sale.payment_status
            }

    @staticmethod
    def daily_summary(date):
        sales = Sale.objects.filter(sale_date__date=date)
        return {
            'date': date,
            'total_sales': sales.count(),
            'total_revenue': float(sales.aggregate(total=Sum('net_amount'))['total'] or 0),
            'cash_sales': float(sales.filter(payment_method='cash').aggregate(total=Sum('net_amount'))['total'] or 0),
            'mobile_sales': float(sales.filter(payment_method='mobile').aggregate(total=Sum('net_amount'))['total'] or 0),
            'card_sales': float(sales.filter(payment_method='card').aggregate(total=Sum('net_amount'))['total'] or 0),
            'insurance_sales': float(sales.filter(payment_method='insurance').aggregate(total=Sum('net_amount'))['total'] or 0),
            'pending_payments': sales.filter(payment_status__in=['pending', 'partial']).count(),
            'items_sold': sales.aggregate(total=Sum('items__quantity'))['total'] or 0
        }

    @staticmethod
    def top_selling(days=30, limit=10):
        start_date = timezone.now() - timezone.timedelta(days=days)
        top = SaleItem.objects.filter(sale__sale_date__gte=start_date).values(
            'medicine__name', 'medicine__medicine_id'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('subtotal')
        ).order_by('-total_quantity')[:limit]
        return list(top)

    @staticmethod
    def process_payment(sale, payment_amount, payment_method, user, transaction_ref='', notes=''):
        """Process an additional payment for a sale.

        Validates the payment amount does not exceed amount due,
        creates Payment record, updates sale payment_status.
        """
        payment_amount = Decimal(payment_amount)
        total_paid = sale.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        amount_due = Decimal(sale.net_amount) - total_paid

        if payment_amount <= 0:
            raise serializers.ValidationError('Payment amount must be greater than 0')

        if payment_amount > amount_due:
            raise serializers.ValidationError(f'Payment amount ({payment_amount}) exceeds amount due ({amount_due})')

        with transaction.atomic():
            Payment.objects.create(
                sale=sale,
                amount=payment_amount,
                payment_method=payment_method,
                transaction_ref=transaction_ref,
                notes=notes,
                received_by=user
            )

            new_total_paid = total_paid + payment_amount
            if new_total_paid >= sale.net_amount:
                sale.payment_status = 'paid'
            else:
                sale.payment_status = 'partial'
            sale.save()

            return {
                'sale_id': sale.sale_id,
                'amount_paid': float(payment_amount),
                'total_paid': float(new_total_paid),
                'amount_due': float(sale.net_amount - new_total_paid),
                'payment_status': sale.payment_status
            }
