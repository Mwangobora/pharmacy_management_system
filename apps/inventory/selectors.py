from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import serializers

from .models import Medicine, MedicineBatch, MedicineUnitConversion


@dataclass(frozen=True)
class BatchAllocationPlan:
    batch: MedicineBatch
    quantity: int


def get_unit_conversion(
    medicine: Medicine,
    unit_name: str | None = None,
    *,
    allow_purchase: bool = False,
    allow_sale: bool = False,
) -> MedicineUnitConversion:
    resolved_unit = unit_name or medicine.base_unit or medicine.unit
    queryset = MedicineUnitConversion.objects.filter(
        medicine=medicine,
        unit_name=resolved_unit,
        is_active=True,
    )
    if allow_purchase:
        queryset = queryset.filter(allow_purchase=True)
    if allow_sale:
        queryset = queryset.filter(allow_sale=True)

    conversion = queryset.first()
    if not conversion:
        raise serializers.ValidationError(
            f'{medicine.name}: unit "{resolved_unit}" is not configured for this medicine.'
        )
    return conversion


def convert_to_base_units(
    medicine: Medicine,
    quantity: int,
    unit_name: str | None = None,
    *,
    allow_purchase: bool = False,
    allow_sale: bool = False,
) -> tuple[MedicineUnitConversion, int]:
    if int(quantity) <= 0:
        raise serializers.ValidationError('Quantity must be greater than 0.')
    conversion = get_unit_conversion(
        medicine,
        unit_name,
        allow_purchase=allow_purchase,
        allow_sale=allow_sale,
    )
    return conversion, int(quantity) * int(conversion.factor_to_base_unit)


def get_sellable_batches(medicine: Medicine, *, lock: bool = False):
    queryset = MedicineBatch.objects.filter(
        medicine=medicine,
        is_active=True,
        quantity_on_hand__gt=0,
        expiry_date__gte=timezone.localdate(),
    ).order_by('expiry_date', 'received_at', 'created_at', 'id')
    return queryset.select_for_update() if lock else queryset


def get_manual_batch_allocations(
    medicine: Medicine,
    requested_allocations: list[dict],
) -> list[BatchAllocationPlan]:
    if not requested_allocations:
        return []

    batch_ids = [item.get('batch_id') for item in requested_allocations if item.get('batch_id')]
    batches = {
        str(batch.id): batch
        for batch in get_sellable_batches(medicine, lock=True).filter(id__in=batch_ids)
    }

    plans: list[BatchAllocationPlan] = []
    for item in requested_allocations:
        batch_id = str(item.get('batch_id'))
        quantity = int(item.get('quantity') or 0)
        batch = batches.get(batch_id)
        if not batch:
            raise serializers.ValidationError(
                f'{medicine.name}: selected batch {batch_id} is unavailable or expired.'
            )
        if quantity <= 0:
            raise serializers.ValidationError(
                f'{medicine.name}: manual batch quantities must be greater than 0.'
            )
        if quantity > batch.quantity_on_hand:
            raise serializers.ValidationError(
                f'{medicine.name}: batch {batch.batch_number} only has {batch.quantity_on_hand} base units.'
            )
        plans.append(BatchAllocationPlan(batch=batch, quantity=quantity))
    return plans


def build_fefo_allocation_plan(
    medicine: Medicine,
    quantity_base_units: int,
    *,
    requested_allocations: list[dict] | None = None,
) -> list[BatchAllocationPlan]:
    if quantity_base_units <= 0:
        raise serializers.ValidationError('Allocated quantity must be greater than 0.')

    if requested_allocations:
        plans = get_manual_batch_allocations(medicine, requested_allocations)
        allocated_total = sum(item.quantity for item in plans)
        if allocated_total != quantity_base_units:
            raise serializers.ValidationError(
                f'{medicine.name}: manual batch allocations must total {quantity_base_units} base units.'
            )
        return plans

    remaining = quantity_base_units
    plans: list[BatchAllocationPlan] = []
    for batch in get_sellable_batches(medicine, lock=True):
        if remaining <= 0:
            break
        allocated = min(batch.quantity_on_hand, remaining)
        plans.append(BatchAllocationPlan(batch=batch, quantity=allocated))
        remaining -= allocated

    if remaining > 0:
        raise serializers.ValidationError(
            f'{medicine.name}: insufficient non-expired stock. Short by {remaining} base units.'
        )
    return plans


def sync_medicine_stock_cache(medicine: Medicine) -> Medicine:
    batches = medicine.batches.filter(is_active=True)
    on_hand_batches = batches.filter(quantity_on_hand__gt=0)

    total_stock = on_hand_batches.aggregate(
        total=Coalesce(Sum('quantity_on_hand'), 0)
    )['total']

    primary_batch = (
        on_hand_batches.order_by('expiry_date', 'received_at', 'created_at', 'id').first()
        or batches.order_by('-received_at', '-created_at').first()
    )

    weighted_purchase_price = medicine.purchase_price
    if total_stock:
        total_value = sum(
            Decimal(batch.quantity_on_hand) * Decimal(batch.purchase_price)
            for batch in on_hand_batches
        )
        weighted_purchase_price = (
            total_value / Decimal(total_stock)
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    medicine.stock_quantity = int(total_stock or 0)
    medicine.purchase_price = weighted_purchase_price
    medicine.base_unit = medicine.base_unit or medicine.unit or 'pieces'
    medicine.unit = medicine.base_unit

    if primary_batch:
        medicine.batch_number = primary_batch.batch_number
        medicine.manufacture_date = primary_batch.manufacture_date or medicine.manufacture_date
        medicine.expiry_date = primary_batch.expiry_date
        if primary_batch.selling_price:
            medicine.selling_price = primary_batch.selling_price

    medicine.save(
        update_fields=[
            'stock_quantity',
            'purchase_price',
            'selling_price',
            'batch_number',
            'manufacture_date',
            'expiry_date',
            'base_unit',
            'unit',
            'updated_at',
        ]
    )
    return medicine


def get_or_create_base_unit_conversion(medicine: Medicine) -> MedicineUnitConversion:
    return MedicineUnitConversion.objects.get_or_create(
        medicine=medicine,
        unit_name=medicine.base_unit or medicine.unit or 'pieces',
        defaults={
            'factor_to_base_unit': 1,
            'is_base_unit': True,
            'allow_purchase': True,
            'allow_sale': True,
            'is_active': True,
            'sort_order': 0,
        },
    )[0]

