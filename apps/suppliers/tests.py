from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.inventory.models import Category, Medicine, MedicineBatch, MedicineUnitConversion, StockTransaction
from apps.suppliers.models import PurchaseItem
from apps.suppliers.services import PurchaseService
from apps.users.models import User

from .models import Supplier


class PurchaseServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='buyer@example.com',
            username='buyer',
            password='secret123',
        )
        self.category = Category.objects.create(name='Antibiotics')
        self.supplier = Supplier.objects.create(name='Good Pharma', phone='255700000001')
        self.medicine = Medicine.objects.create(
            name='Amoxicillin 500mg',
            generic_name='Amoxicillin',
            category=self.category,
            supplier=self.supplier,
            batch_number='LEG-AMOX',
            manufacture_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=365),
            purchase_price=Decimal('50.00'),
            selling_price=Decimal('75.00'),
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
            unit_name='boxes',
            factor_to_base_unit=10,
            allow_purchase=True,
            allow_sale=False,
            sort_order=1,
        )

    def test_create_purchase_receives_into_batch_and_updates_stock(self):
        purchase = PurchaseService.create_purchase_with_items(
            self.user,
            {
                'supplier': self.supplier,
                'invoice_number': 'PUR-1001',
                'purchase_date': timezone.localdate(),
                'items': [
                    {
                        'medicine': str(self.medicine.id),
                        'quantity': 2,
                        'unit_name': 'boxes',
                        'unit_price': '500.00',
                        'batch_number': 'BOX-AMOX-01',
                        'expiry_date': (timezone.localdate() + timedelta(days=540)).isoformat(),
                    }
                ],
            },
        )

        self.medicine.refresh_from_db()
        purchase_item = PurchaseItem.objects.get(purchase=purchase)
        batch = MedicineBatch.objects.get(purchase_items=purchase_item)
        transaction = StockTransaction.objects.get(reference_id=str(purchase.id))

        self.assertEqual(self.medicine.stock_quantity, 20)
        self.assertEqual(batch.batch_number, 'BOX-AMOX-01')
        self.assertEqual(batch.quantity_received, 20)
        self.assertEqual(batch.quantity_on_hand, 20)
        self.assertEqual(batch.purchase_price, Decimal('50.00'))
        self.assertEqual(purchase_item.quantity, 20)
        self.assertEqual(purchase_item.quantity_base_units, 20)
        self.assertEqual(purchase_item.quantity_in_unit, 2)
        self.assertEqual(purchase_item.unit_name, 'boxes')
        self.assertEqual(purchase_item.unit_price, Decimal('50.00'))
        self.assertEqual(transaction.quantity, 20)
        self.assertEqual(transaction.batch_id, batch.id)
