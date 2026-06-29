from __future__ import annotations

from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import Medicine, MedicineBatch, MedicineUnitConversion, StockTransaction
from .selectors import sync_medicine_stock_cache


def create_stock_transaction(
    *,
    medicine: Medicine,
    transaction_type: str,
    quantity_delta: int,
    created_by,
    reference_type: str | None = None,
    reference_id: str | None = None,
    notes: str = '',
    batch: MedicineBatch | None = None,
    source_batch: MedicineBatch | None = None,
    destination_batch: MedicineBatch | None = None,
    unit_conversion: MedicineUnitConversion | None = None,
    quantity_in_unit: int | None = None,
    unit_name: str | None = None,
    previous_quantity: int = 0,
    new_quantity: int = 0,
    previous_batch_quantity: int | None = None,
    new_batch_quantity: int | None = None,
):
    return StockTransaction.objects.create(
        medicine=medicine,
        batch=batch,
        source_batch=source_batch,
        destination_batch=destination_batch,
        unit_conversion=unit_conversion,
        transaction_type=transaction_type,
        quantity=quantity_delta,
        quantity_base_units=quantity_delta,
        quantity_in_unit=quantity_in_unit,
        unit_name=unit_name or getattr(unit_conversion, 'unit_name', None),
        previous_quantity=previous_quantity,
        new_quantity=new_quantity,
        previous_batch_quantity=previous_batch_quantity,
        new_batch_quantity=new_batch_quantity,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id else None,
        notes=notes,
        created_by=created_by,
    )


def ensure_adjustment_batch(medicine: Medicine) -> MedicineBatch:
    batch = medicine.batches.filter(is_active=True).order_by('expiry_date', '-received_at').first()
    if batch:
        return batch

    return MedicineBatch.objects.create(
        medicine=medicine,
        supplier=medicine.supplier,
        batch_number=f'ADJ-{timezone.now().strftime("%Y%m%d%H%M%S")}',
        manufacture_date=medicine.manufacture_date,
        expiry_date=medicine.expiry_date or (timezone.localdate() + timedelta(days=365)),
        purchase_price=medicine.purchase_price or Decimal('0.01'),
        selling_price=medicine.selling_price or Decimal('0.02'),
        quantity_received=0,
        quantity_on_hand=0,
        notes='System-created adjustment batch.',
    )


@transaction.atomic
def increase_batch_stock(
    *,
    batch: MedicineBatch,
    quantity: int,
    created_by,
    transaction_type: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    notes: str = '',
    unit_conversion: MedicineUnitConversion | None = None,
    quantity_in_unit: int | None = None,
    increase_received: bool = False,
) -> MedicineBatch:
    if quantity <= 0:
        raise serializers.ValidationError('Stock increase quantity must be greater than 0.')

    medicine = Medicine.objects.select_for_update().get(pk=batch.medicine_id)
    batch = MedicineBatch.objects.select_for_update().get(pk=batch.pk)

    previous_total = medicine.stock_quantity
    previous_batch = batch.quantity_on_hand

    if increase_received:
        batch.quantity_received += quantity
    batch.quantity_on_hand += quantity
    batch.save(update_fields=['quantity_received', 'quantity_on_hand', 'updated_at'])

    sync_medicine_stock_cache(medicine)
    medicine.refresh_from_db(fields=['stock_quantity'])

    create_stock_transaction(
        medicine=medicine,
        batch=batch,
        transaction_type=transaction_type,
        quantity_delta=quantity,
        created_by=created_by,
        reference_type=reference_type,
        reference_id=reference_id,
        notes=notes,
        unit_conversion=unit_conversion,
        quantity_in_unit=quantity_in_unit,
        previous_quantity=previous_total,
        new_quantity=medicine.stock_quantity,
        previous_batch_quantity=previous_batch,
        new_batch_quantity=batch.quantity_on_hand,
    )
    return batch


@transaction.atomic
def decrease_batch_stock(
    *,
    batch: MedicineBatch,
    quantity: int,
    created_by,
    transaction_type: str,
    reference_type: str | None = None,
    reference_id: str | None = None,
    notes: str = '',
    unit_conversion: MedicineUnitConversion | None = None,
    quantity_in_unit: int | None = None,
) -> MedicineBatch:
    if quantity <= 0:
        raise serializers.ValidationError('Stock decrease quantity must be greater than 0.')

    medicine = Medicine.objects.select_for_update().get(pk=batch.medicine_id)
    batch = MedicineBatch.objects.select_for_update().get(pk=batch.pk)

    if batch.expiry_date < timezone.localdate():
        raise serializers.ValidationError(
            f'{medicine.name}: batch {batch.batch_number} is expired and cannot be used.'
        )
    if batch.quantity_on_hand < quantity:
        raise serializers.ValidationError(
            f'{medicine.name}: batch {batch.batch_number} only has {batch.quantity_on_hand} base units available.'
        )

    previous_total = medicine.stock_quantity
    previous_batch = batch.quantity_on_hand

    batch.quantity_on_hand -= quantity
    batch.save(update_fields=['quantity_on_hand', 'updated_at'])

    sync_medicine_stock_cache(medicine)
    medicine.refresh_from_db(fields=['stock_quantity'])

    create_stock_transaction(
        medicine=medicine,
        batch=batch,
        transaction_type=transaction_type,
        quantity_delta=-quantity,
        created_by=created_by,
        reference_type=reference_type,
        reference_id=reference_id,
        notes=notes,
        unit_conversion=unit_conversion,
        quantity_in_unit=quantity_in_unit,
        previous_quantity=previous_total,
        new_quantity=medicine.stock_quantity,
        previous_batch_quantity=previous_batch,
        new_batch_quantity=batch.quantity_on_hand,
    )
    return batch
