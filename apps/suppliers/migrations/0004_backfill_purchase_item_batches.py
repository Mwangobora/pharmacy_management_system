from django.db import migrations


def backfill_purchase_items(apps, schema_editor):
    MedicineBatch = apps.get_model('inventory', 'MedicineBatch')
    MedicineUnitConversion = apps.get_model('inventory', 'MedicineUnitConversion')
    PurchaseItem = apps.get_model('suppliers', 'PurchaseItem')
    db_alias = schema_editor.connection.alias

    for item in PurchaseItem.objects.using(db_alias).select_related('medicine').iterator():
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
        batch = MedicineBatch.objects.using(db_alias).filter(
            medicine=medicine,
            is_legacy=True,
        ).order_by('expiry_date', 'created_at').first() or MedicineBatch.objects.using(db_alias).filter(
            medicine=medicine,
        ).order_by('expiry_date', 'created_at').first()

        item.unit_conversion = item.unit_conversion or conversion
        item.unit_name = item.unit_name or unit_name
        item.quantity_base_units = item.quantity_base_units or int(item.quantity or 0)
        item.quantity_in_unit = item.quantity_in_unit or int(item.quantity or 0)
        item.cost_price_snapshot = item.cost_price_snapshot or item.unit_price
        if batch and not item.batch_id:
            item.batch = batch
        item.save(
            update_fields=[
                'unit_conversion',
                'unit_name',
                'quantity_base_units',
                'quantity_in_unit',
                'cost_price_snapshot',
                'batch',
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_backfill_batch_inventory'),
        ('suppliers', '0003_purchaseitem_batch_purchaseitem_cost_price_snapshot_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_purchase_items, migrations.RunPython.noop),
    ]
