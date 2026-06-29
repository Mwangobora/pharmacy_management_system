"""
Service layer for inventory operations.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import timedelta

from django.db.models import Count, F, Sum
from django.utils import timezone
from rest_framework import serializers

from .models import Medicine, MedicineBatch, StockTransaction
from .selectors import build_fefo_allocation_plan, sync_medicine_stock_cache
from .stock_service import decrease_batch_stock, ensure_adjustment_batch, increase_batch_stock


class InventoryService:
    """Business logic for inventory management."""

    @staticmethod
    def get_dashboard_stats(is_active_only=True):
        medicines = Medicine.objects.all()
        batches = MedicineBatch.objects.filter(is_active=True)
        if is_active_only:
            medicines = medicines.filter(is_active=True)
            batches = batches.filter(medicine__is_active=True)

        today = timezone.localdate()
        thirty_days = today + timedelta(days=30)

        return {
            'total_medicines': medicines.count(),
            'low_stock_count': medicines.filter(stock_quantity__lte=F('min_stock_level')).count(),
            'expiring_soon_count': batches.filter(
                expiry_date__gte=today,
                expiry_date__lte=thirty_days,
                quantity_on_hand__gt=0,
            ).count(),
            'expired_count': batches.filter(
                expiry_date__lt=today,
                quantity_on_hand__gt=0,
            ).count(),
            'total_stock_value': sum(
                Decimal(batch.quantity_on_hand) * Decimal(batch.purchase_price)
                for batch in batches.filter(quantity_on_hand__gt=0)
            ) or Decimal('0'),
        }

    @staticmethod
    def adjust_stock(medicine, quantity, adjustment_type, user, reason=''):
        quantity = int(quantity)
        if quantity <= 0:
            raise serializers.ValidationError('Adjustment quantity must be greater than 0.')

        batch = ensure_adjustment_batch(medicine)
        if adjustment_type == 'increase':
            increase_batch_stock(
                batch=batch,
                quantity=quantity,
                created_by=user,
                transaction_type='adjustment',
                reference_type='manual_adjustment',
                reference_id=str(medicine.id),
                notes=reason,
            )
        else:
            for allocation in build_fefo_allocation_plan(medicine, quantity):
                decrease_batch_stock(
                    batch=allocation.batch,
                    quantity=allocation.quantity,
                    created_by=user,
                    transaction_type='adjustment',
                    reference_type='manual_adjustment',
                    reference_id=str(medicine.id),
                    notes=reason,
                )

        sync_medicine_stock_cache(medicine)
        medicine.refresh_from_db(fields=['stock_quantity'])
        return {
            'medicine_id': medicine.id,
            'new_stock': medicine.stock_quantity,
            'adjusted_by': quantity if adjustment_type == 'increase' else -quantity,
            'reason': reason,
            'batch_number': batch.batch_number,
        }

    @staticmethod
    def get_transaction_summary(start_date=None, end_date=None):
        queryset = StockTransaction.objects.all()

        if start_date:
            queryset = queryset.filter(transaction_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(transaction_date__lte=end_date)

        return list(
            queryset.values('transaction_type').annotate(
                count=Count('id'),
                total_quantity=Sum('quantity_base_units'),
            ).order_by('transaction_type')
        )
