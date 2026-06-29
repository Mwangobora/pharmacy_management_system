from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.inventory.models import Category, Medicine, MedicineBatch, MedicineUnitConversion
from apps.inventory.selectors import sync_medicine_stock_cache
from apps.sales.models import SaleItemBatchAllocation
from apps.sales.services import SalesService
from apps.suppliers.models import Supplier
from apps.users.models import User


class SalesServiceBatchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='cashier@example.com',
            username='cashier',
            password='secret123',
        )
        self.category = Category.objects.create(name='Pain Relief')
        self.supplier = Supplier.objects.create(name='Health Supplier', phone='255700000002')
        self.medicine = Medicine.objects.create(
            name='Paracetamol 500mg',
            generic_name='Paracetamol',
            category=self.category,
            supplier=self.supplier,
            batch_number='BATCH-A',
            manufacture_date=timezone.localdate() - timedelta(days=30),
            expiry_date=timezone.localdate() + timedelta(days=90),
            purchase_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            stock_quantity=0,
            unit='tablets',
            base_unit='tablets',
        )
        MedicineUnitConversion.objects.create(
            medicine=self.medicine,
            unit_name='tablets',
            factor_to_base_unit=1,
            is_base_unit=True,
        )
        MedicineUnitConversion.objects.create(
            medicine=self.medicine,
            unit_name='strips',
            factor_to_base_unit=5,
            allow_purchase=True,
            allow_sale=True,
            sort_order=1,
        )
        self.batch_a = MedicineBatch.objects.create(
            medicine=self.medicine,
            supplier=self.supplier,
            batch_number='BATCH-A',
            manufacture_date=timezone.localdate() - timedelta(days=30),
            expiry_date=timezone.localdate() + timedelta(days=10),
            purchase_price=Decimal('90.00'),
            selling_price=Decimal('150.00'),
            quantity_received=5,
            quantity_on_hand=5,
        )
        self.batch_b = MedicineBatch.objects.create(
            medicine=self.medicine,
            supplier=self.supplier,
            batch_number='BATCH-B',
            manufacture_date=timezone.localdate() - timedelta(days=20),
            expiry_date=timezone.localdate() + timedelta(days=40),
            purchase_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            quantity_received=20,
            quantity_on_hand=20,
        )
        sync_medicine_stock_cache(self.medicine)

    def test_sale_uses_fefo_and_splits_allocations(self):
        sale = SalesService.create_sale(
            self.user,
            {
                'payment_method': 'cash',
                'items': [
                    {
                        'medicine': str(self.medicine.id),
                        'quantity': 3,
                        'unit_name': 'strips',
                    }
                ],
            },
        )

        allocations = list(
            SaleItemBatchAllocation.objects.filter(sale_item__sale=sale)
            .select_related('batch')
            .order_by('batch__expiry_date', 'batch__batch_number')
        )
        self.batch_a.refresh_from_db()
        self.batch_b.refresh_from_db()

        self.assertEqual(len(allocations), 2)
        self.assertEqual([(item.batch.batch_number, item.quantity) for item in allocations], [('BATCH-A', 5), ('BATCH-B', 10)])
        self.assertEqual(self.batch_a.quantity_on_hand, 0)
        self.assertEqual(self.batch_b.quantity_on_hand, 10)

    def test_refund_restores_original_batches(self):
        sale = SalesService.create_sale(
            self.user,
            {
                'payment_method': 'cash',
                'items': [
                    {
                        'medicine': str(self.medicine.id),
                        'quantity': 3,
                        'unit_name': 'strips',
                    }
                ],
            },
        )
        sale_item = sale.items.first()
        refund = SalesService.process_refund(
            sale,
            refund_amount='1050.00',
            items_to_refund=[{'sale_item_id': str(sale_item.id), 'quantity': 7}],
            user=self.user,
            reason='Damaged package',
        )

        allocations = list(
            SaleItemBatchAllocation.objects.filter(sale_item=sale_item)
            .select_related('batch')
            .order_by('batch__expiry_date', 'batch__batch_number')
        )
        self.batch_a.refresh_from_db()
        self.batch_b.refresh_from_db()

        self.assertEqual(refund['refund_amount'], 1050.0)
        self.assertEqual(self.batch_a.quantity_on_hand, 5)
        self.assertEqual(self.batch_b.quantity_on_hand, 12)
        self.assertEqual([(item.batch.batch_number, item.returned_quantity) for item in allocations], [('BATCH-A', 5), ('BATCH-B', 2)])
