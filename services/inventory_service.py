"""
Service layer for inventory operations.

Handles business logic for:
- Dashboard statistics
- Stock adjustments
- Transaction summaries
"""
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, F, Count
from django.utils import timezone
from datetime import timedelta

from inventory.models import Medicine, StockTransaction


class InventoryService:
    """Business logic for inventory management."""

    @staticmethod
    def get_dashboard_stats(is_active_only=True):
        """Get comprehensive inventory dashboard statistics.

        Returns:
        - total_medicines: Count of medicines
        - low_stock_count: Medicines below min stock level
        - expiring_soon_count: Expiring within 30 days
        - expired_count: Already expired medicines
        - total_stock_value: Total value of stock at purchase price
        """
        queryset = Medicine.objects.all()
        if is_active_only:
            queryset = queryset.filter(is_active=True)

        today = timezone.now().date()
        thirty_days = today + timedelta(days=30)

        return {
            'total_medicines': queryset.count(),
            'low_stock_count': queryset.filter(stock_quantity__lte=F('min_stock_level')).count(),
            'expiring_soon_count': queryset.filter(
                expiry_date__gte=today,
                expiry_date__lte=thirty_days,
                stock_quantity__gt=0
            ).count(),
            'expired_count': queryset.filter(
                expiry_date__lt=today,
                stock_quantity__gt=0
            ).count(),
            'total_stock_value': queryset.aggregate(
                total=Sum(F('stock_quantity') * F('purchase_price'), output_field=None)
            )['total'] or Decimal('0')
        }

    @staticmethod
    def adjust_stock(medicine, quantity, adjustment_type, user, reason=''):
        """Adjust medicine stock and create transaction record.

        Args:
            medicine: Medicine instance
            quantity: Amount to adjust (positive number)
            adjustment_type: 'increase' or 'decrease'
            user: User making the adjustment
            reason: Reason for adjustment

        Returns:
            Dictionary with adjustment result
        """
        if adjustment_type == 'decrease':
            quantity = -quantity

        with transaction.atomic():
            StockTransaction.objects.create(
                medicine=medicine,
                transaction_type='adjustment',
                quantity=quantity,
                created_by=user,
                notes=reason
            )

            return {
                'medicine_id': medicine.id,
                'new_stock': medicine.stock_quantity,
                'adjusted_by': quantity,
                'reason': reason
            }

    @staticmethod
    def get_transaction_summary(start_date=None, end_date=None):
        """Get transaction summary grouped by type.

        Returns count and total quantity for each transaction type.
        """
        queryset = StockTransaction.objects.all()

        if start_date:
            queryset = queryset.filter(transaction_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(transaction_date__lte=end_date)

        return list(queryset.values('transaction_type').annotate(
            count=Count('id'),
            total_quantity=Sum('quantity')
        ).order_by('transaction_type'))
