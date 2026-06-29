from decimal import Decimal
from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def _default_expiry():
    return timezone.localdate() + timedelta(days=365)


def seed_batches_and_conversions(apps, schema_editor):
    Medicine = apps.get_model('inventory', 'Medicine')
    MedicineBatch = apps.get_model('inventory', 'MedicineBatch')
    MedicineUnitConversion = apps.get_model('inventory', 'MedicineUnitConversion')
    StockTransaction = apps.get_model('inventory', 'StockTransaction')
    User = apps.get_model('users', 'User')

    default_user = User.objects.order_by('created_at').first()
    db_alias = schema_editor.connection.alias

    for medicine in Medicine.objects.using(db_alias).select_related('supplier').iterator():
        base_unit = medicine.unit or 'pieces'
        if medicine.base_unit != base_unit:
            medicine.base_unit = base_unit
            medicine.save(update_fields=['base_unit'])

        conversion, _ = MedicineUnitConversion.objects.using(db_alias).get_or_create(
            medicine=medicine,
            unit_name=base_unit,
            defaults={
                'factor_to_base_unit': 1,
                'is_base_unit': True,
                'allow_purchase': True,
                'allow_sale': True,
                'is_active': True,
                'sort_order': 0,
            },
        )

        quantity_on_hand = int(medicine.stock_quantity or 0)
        if quantity_on_hand < 0:
            raise ValueError(
                f'Cannot migrate negative stock for medicine {medicine.id} ({medicine.name}).'
            )

        purchase_price = medicine.purchase_price or Decimal('0.01')
        selling_price = medicine.selling_price or max(
            purchase_price + Decimal('0.01'),
            (purchase_price * Decimal('1.20')).quantize(Decimal('0.01')),
        )
        batch_number = medicine.batch_number or f'LEGACY-{str(medicine.id)[:8].upper()}'
        expiry_date = medicine.expiry_date or _default_expiry()

        batch, created = MedicineBatch.objects.using(db_alias).get_or_create(
            medicine=medicine,
            batch_number=batch_number,
            defaults={
                'supplier': medicine.supplier,
                'manufacture_date': medicine.manufacture_date,
                'expiry_date': expiry_date,
                'purchase_price': purchase_price,
                'selling_price': selling_price,
                'quantity_received': quantity_on_hand,
                'quantity_on_hand': quantity_on_hand,
                'notes': 'Legacy opening batch created during stock migration.',
                'is_active': True,
                'is_legacy': True,
            },
        )

        if not created:
            changed = False
            if batch.supplier_id != medicine.supplier_id:
                batch.supplier = medicine.supplier
                changed = True
            if batch.manufacture_date != medicine.manufacture_date:
                batch.manufacture_date = medicine.manufacture_date
                changed = True
            if batch.expiry_date != expiry_date:
                batch.expiry_date = expiry_date
                changed = True
            if batch.purchase_price != purchase_price:
                batch.purchase_price = purchase_price
                changed = True
            if batch.selling_price != selling_price:
                batch.selling_price = selling_price
                changed = True
            if batch.quantity_received != quantity_on_hand:
                batch.quantity_received = quantity_on_hand
                changed = True
            if batch.quantity_on_hand != quantity_on_hand:
                batch.quantity_on_hand = quantity_on_hand
                changed = True
            if not batch.is_legacy:
                batch.is_legacy = True
                changed = True
            if changed:
                batch.save()

        if default_user and quantity_on_hand > 0 and not StockTransaction.objects.using(db_alias).filter(
            medicine=medicine,
            batch=batch,
            transaction_type='adjustment',
            reference_type='legacy_migration',
            reference_id=str(medicine.id),
        ).exists():
            StockTransaction.objects.using(db_alias).create(
                medicine=medicine,
                batch=batch,
                unit_conversion=conversion,
                transaction_type='adjustment',
                quantity=quantity_on_hand,
                quantity_base_units=quantity_on_hand,
                quantity_in_unit=quantity_on_hand,
                unit_name=base_unit,
                previous_quantity=0,
                new_quantity=quantity_on_hand,
                previous_batch_quantity=0,
                new_batch_quantity=quantity_on_hand,
                reference_type='legacy_migration',
                reference_id=str(medicine.id),
                notes='Legacy opening stock created during batch migration.',
                created_by=default_user,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0005_medicine_base_unit_and_more'),
        ('users', '0006_dashboard_permissions'),
    ]

    operations = [
        migrations.RunPython(seed_batches_and_conversions, migrations.RunPython.noop),
    ]
