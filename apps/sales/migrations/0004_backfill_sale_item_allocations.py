from decimal import Decimal

from django.db import migrations


def backfill_sale_items(apps, schema_editor):
    MedicineBatch = apps.get_model('inventory', 'MedicineBatch')
    MedicineUnitConversion = apps.get_model('inventory', 'MedicineUnitConversion')
    SaleItem = apps.get_model('sales', 'SaleItem')
    SaleItemBatchAllocation = apps.get_model('sales', 'SaleItemBatchAllocation')
    db_alias = schema_editor.connection.alias

    for item in SaleItem.objects.using(db_alias).select_related('medicine').iterator():
        medicine = item.medicine
        unit_name = medicine.base_unit or medicine.unit or 'pieces'
        conversion, _ = MedicineUnitConversion.objects.using(db_alias).get_or_create(
            medicine=medicine,
            unit_name=unit_name,
            defaults={
                'factor_to_base_unit': 1,
                'is_base_unit': True,
                'allow_purchase': True,
                'allow_sale': True,
                'is_active': True,
                'sort_order': 0,
            },
        )
        batch = None
        if item.batch_number and item.batch_number != 'MULTI':
            batch = MedicineBatch.objects.using(db_alias).filter(
                medicine=medicine,
                batch_number=item.batch_number,
            ).order_by('expiry_date', 'created_at').first()
        if not batch:
            batch = MedicineBatch.objects.using(db_alias).filter(
                medicine=medicine,
                is_legacy=True,
            ).order_by('expiry_date', 'created_at').first() or MedicineBatch.objects.using(db_alias).filter(
                medicine=medicine,
            ).order_by('expiry_date', 'created_at').first()

        quantity = int(item.quantity or 0)
        cost_snapshot = item.cost_price_snapshot or (
            batch.purchase_price if batch else medicine.purchase_price or Decimal('0.00')
        )
        selling_snapshot = item.selling_price_snapshot or item.unit_price
        profit_snapshot = (
            (Decimal(selling_snapshot) - Decimal(cost_snapshot)) * Decimal(quantity)
        ).quantize(Decimal('0.01'))

        item.unit_conversion = item.unit_conversion or conversion
        item.sold_unit_name = item.sold_unit_name or unit_name
        item.sold_quantity_in_unit = item.sold_quantity_in_unit or quantity
        item.cost_price_snapshot = cost_snapshot
        item.selling_price_snapshot = selling_snapshot
        item.profit_snapshot = item.profit_snapshot if item.profit_snapshot is not None else profit_snapshot
        if batch and (not item.batch_number or item.batch_number == 'MULTI'):
            item.batch_number = batch.batch_number
        item.save(
            update_fields=[
                'unit_conversion',
                'sold_unit_name',
                'sold_quantity_in_unit',
                'cost_price_snapshot',
                'selling_price_snapshot',
                'profit_snapshot',
                'batch_number',
            ]
        )

        if batch and quantity > 0 and not SaleItemBatchAllocation.objects.using(db_alias).filter(
            sale_item=item,
            batch=batch,
        ).exists():
            SaleItemBatchAllocation.objects.using(db_alias).create(
                sale_item=item,
                batch=batch,
                quantity=quantity,
                cost_price_snapshot=cost_snapshot,
                selling_price_snapshot=selling_snapshot,
                total_cost_snapshot=(Decimal(quantity) * Decimal(cost_snapshot)).quantize(Decimal('0.01')),
                total_revenue_snapshot=(Decimal(quantity) * Decimal(selling_snapshot)).quantize(Decimal('0.01')),
                returned_quantity=min(int(item.refunded_quantity or 0), quantity),
            )


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_backfill_batch_inventory'),
        ('sales', '0003_saleitem_cost_price_snapshot_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_sale_items, migrations.RunPython.noop),
    ]
