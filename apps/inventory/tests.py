from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.inventory.models import Category, Medicine, MedicineUnitConversion
from apps.inventory.serializers import MedicineDetailSerializer
from apps.inventory.unit_suggestions import suggest_base_unit_for_dosage_form
from apps.suppliers.models import Supplier
from apps.users.models import User


class MedicineUnitFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='inventory@example.com',
            username='inventory',
            password='secret123',
        )
        self.category = Category.objects.create(name='Respiratory')
        self.supplier = Supplier.objects.create(name='Unit Supplier', phone='255700000011')

    def test_missing_base_unit_is_rejected(self):
        serializer = MedicineDetailSerializer(data={
            'name': 'Cetirizine',
            'category': str(self.category.id),
            'supplier': str(self.supplier.id),
            'selling_price': '2500.00',
        })

        self.assertFalse(serializer.is_valid())
        self.assertIn('base_unit', serializer.errors)

    def test_dosage_form_suggestion_mapping(self):
        self.assertEqual(suggest_base_unit_for_dosage_form('tablet'), 'tablets')
        self.assertEqual(suggest_base_unit_for_dosage_form('suspension'), 'bottles')
        self.assertEqual(suggest_base_unit_for_dosage_form('injection'), 'vials')
        self.assertIsNone(suggest_base_unit_for_dosage_form('unknown-form'))

    def test_medicine_creation_saves_base_unit_and_package_conversions(self):
        serializer = MedicineDetailSerializer(data={
            'name': 'Azithromycin',
            'category': str(self.category.id),
            'supplier': str(self.supplier.id),
            'base_unit': 'tablets',
            'selling_price': '1500.00',
            'unit_conversions': [
                {
                    'unit_name': 'strips',
                    'factor_to_base_unit': 10,
                    'allow_purchase': True,
                    'allow_sale': True,
                },
                {
                    'unit_name': 'boxes',
                    'factor_to_base_unit': 100,
                    'allow_purchase': True,
                    'allow_sale': False,
                },
            ],
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        medicine = serializer.save()

        conversions = {
            item.unit_name: item
            for item in MedicineUnitConversion.objects.filter(medicine=medicine)
        }
        self.assertEqual(medicine.base_unit, 'tablets')
        self.assertEqual(medicine.unit, 'tablets')
        self.assertFalse(medicine.unit_review_required)
        self.assertEqual(conversions['tablets'].factor_to_base_unit, 1)
        self.assertTrue(conversions['tablets'].is_base_unit)
        self.assertEqual(conversions['strips'].factor_to_base_unit, 10)
        self.assertEqual(conversions['boxes'].factor_to_base_unit, 100)


class BatchMigrationTests(TransactionTestCase):
    migrate_from = [
        ('inventory', '0004_change_reference_id_to_char'),
        ('sales', '0002_initial'),
        ('suppliers', '0002_initial'),
        ('users', '0006_dashboard_permissions'),
    ]
    migrate_to = [
        ('inventory', '0007_medicine_unit_review_required_and_more'),
        ('sales', '0004_backfill_sale_item_allocations'),
        ('suppliers', '0004_backfill_purchase_item_batches'),
        ('users', '0006_dashboard_permissions'),
    ]

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)
        old_apps = self.executor.loader.project_state(self.migrate_from).apps

        User = old_apps.get_model('users', 'User')
        Category = old_apps.get_model('inventory', 'Category')
        Supplier = old_apps.get_model('suppliers', 'Supplier')
        Medicine = old_apps.get_model('inventory', 'Medicine')
        Purchase = old_apps.get_model('suppliers', 'Purchase')
        PurchaseItem = old_apps.get_model('suppliers', 'PurchaseItem')
        Customer = old_apps.get_model('sales', 'Customer')
        Sale = old_apps.get_model('sales', 'Sale')
        SaleItem = old_apps.get_model('sales', 'SaleItem')

        self.user = User.objects.create(
            email='legacy@example.com',
            username='legacy',
            password='raw-password',
            is_active=True,
            is_staff=True,
        )
        self.category = Category.objects.create(name='Legacy Category')
        self.supplier = Supplier.objects.create(name='Legacy Supplier', phone='255700000003')
        self.medicine = Medicine.objects.create(
            name='Legacy Medicine',
            generic_name='Legacy Generic',
            category=self.category,
            supplier=self.supplier,
            batch_number='LEG-001',
            manufacture_date=timezone.localdate() - timedelta(days=15),
            expiry_date=timezone.localdate() + timedelta(days=180),
            purchase_price=Decimal('80.00'),
            selling_price=Decimal('120.00'),
            stock_quantity=40,
            unit='tablets',
        )
        Medicine.objects.create(
            name='Legacy Loose Item',
            category=self.category,
            supplier=self.supplier,
            batch_number='LEG-PIECES',
            manufacture_date=timezone.localdate() - timedelta(days=3),
            expiry_date=timezone.localdate() + timedelta(days=90),
            purchase_price=Decimal('10.00'),
            selling_price=Decimal('20.00'),
            stock_quantity=12,
            unit='pieces',
        )
        purchase = Purchase.objects.create(
            supplier=self.supplier,
            invoice_number='LEG-PUR-1',
            purchase_date=timezone.localdate(),
            total_amount=Decimal('3200.00'),
            tax_amount=Decimal('0.00'),
            discount_amount=Decimal('0.00'),
            net_amount=Decimal('3200.00'),
            payment_status='paid',
            created_by=self.user,
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            medicine=self.medicine,
            quantity=40,
            unit_price=Decimal('80.00'),
            discount_percent=Decimal('0.00'),
            tax_percent=Decimal('0.00'),
            subtotal=Decimal('3200.00'),
            received_quantity=40,
        )
        customer = Customer.objects.create(
            first_name='Legacy',
            last_name='Buyer',
            phone='255700000004',
        )
        sale = Sale.objects.create(
            customer=customer,
            invoice_number='LEG-SALE-1',
            sale_date=timezone.now(),
            total_amount=Decimal('600.00'),
            tax_amount=Decimal('0.00'),
            discount_amount=Decimal('0.00'),
            net_amount=Decimal('600.00'),
            payment_method='cash',
            payment_status='paid',
            served_by=self.user,
        )
        SaleItem.objects.create(
            sale=sale,
            medicine=self.medicine,
            batch_number='LEG-001',
            quantity=5,
            unit_price=Decimal('120.00'),
            discount_percent=Decimal('0.00'),
            tax_percent=Decimal('0.00'),
            subtotal=Decimal('600.00'),
        )

        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_to)
        self.apps = self.executor.loader.project_state(self.migrate_to).apps

    def test_legacy_medicine_backfills_batch_conversion_and_sale_allocation(self):
        Medicine = self.apps.get_model('inventory', 'Medicine')
        MedicineBatch = self.apps.get_model('inventory', 'MedicineBatch')
        MedicineUnitConversion = self.apps.get_model('inventory', 'MedicineUnitConversion')
        PurchaseItem = self.apps.get_model('suppliers', 'PurchaseItem')
        SaleItem = self.apps.get_model('sales', 'SaleItem')
        SaleItemBatchAllocation = self.apps.get_model('sales', 'SaleItemBatchAllocation')

        medicine = Medicine.objects.get(name='Legacy Medicine')
        batch = MedicineBatch.objects.get(medicine=medicine)
        conversion = MedicineUnitConversion.objects.get(medicine=medicine, unit_name='tablets')
        purchase_item = PurchaseItem.objects.get(medicine=medicine)
        sale_item = SaleItem.objects.get(medicine=medicine)
        allocation = SaleItemBatchAllocation.objects.get(sale_item=sale_item)

        self.assertEqual(medicine.base_unit, 'tablets')
        self.assertEqual(batch.batch_number, 'LEG-001')
        self.assertEqual(batch.quantity_on_hand, 40)
        self.assertTrue(batch.is_legacy)
        self.assertEqual(conversion.factor_to_base_unit, 1)
        self.assertEqual(purchase_item.batch_id, batch.id)
        self.assertEqual(purchase_item.quantity_base_units, 40)
        self.assertEqual(sale_item.unit_conversion_id, conversion.id)
        self.assertEqual(sale_item.cost_price_snapshot, Decimal('80.00'))
        self.assertEqual(allocation.batch_id, batch.id)
        self.assertEqual(allocation.quantity, 5)
        self.assertFalse(medicine.unit_review_required)

    def test_legacy_pieces_medicine_is_flagged_for_review(self):
        Medicine = self.apps.get_model('inventory', 'Medicine')
        medicine = Medicine.objects.get(name='Legacy Loose Item')
        self.assertTrue(medicine.unit_review_required)
