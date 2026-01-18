# Inventory API

Base URL: `/api`

## Categories
Base path: `/api/categories/`

- `GET /api/categories/` -> List categories (default: only `is_active=true`).
  - Query params: `search`, `ordering`, `is_active`.
- `POST /api/categories/` -> Create category.
- `GET /api/categories/{id}/` -> Retrieve category by UUID.
- `PUT/PATCH /api/categories/{id}/` -> Update category.
- `DELETE /api/categories/{id}/` -> Soft delete (sets `is_active=false`).
- `GET /api/categories/{id}/medicines/` -> Medicines for category.

Category fields:
- `id` (uuid, read-only)
- `name`
- `description`
- `code` (auto-generated when empty)
- `display_order`
- `is_active`
- `created_at` (read-only)
- `medicine_count` (read-only)

## Medicines
Base path: `/api/medicines/`

- `GET /api/medicines/` -> List medicines (default: only `is_active=true`).
  - Query params: `category`, `supplier`, `requires_prescription`, `is_active`,
    `stock_status` (low|ok|overstock), `expiry_status` (expired|expiring_soon|ok),
    `search`, `ordering`.
- `POST /api/medicines/` -> Create medicine.
- `GET /api/medicines/{id}/` -> Retrieve medicine by UUID.
- `PUT/PATCH /api/medicines/{id}/` -> Update medicine.
- `DELETE /api/medicines/{id}/` -> Soft delete (sets `is_active=false`).
- `GET /api/medicines/low_stock/` -> Medicines at/below min stock.
- `GET /api/medicines/expiring_soon/?days=30` -> Expiring within days.
- `GET /api/medicines/expired/` -> Expired medicines.
- `POST /api/medicines/{id}/adjust_stock/` -> Manual stock adjustment.
- `GET /api/medicines/dashboard_stats/` -> Inventory dashboard stats.

Medicine detail fields (`MedicineDetailSerializer` includes all model fields):
- `id` (uuid, read-only)
- `name`
- `generic_name`
- `category` (category id)
- `supplier` (supplier id)
- `batch_number`
- `manufacture_date` (YYYY-MM-DD)
- `expiry_date` (YYYY-MM-DD)
- `purchase_price`
- `selling_price`
- `markup_percentage` (nullable)
- `stock_quantity`
- `min_stock_level`
- `max_stock_level`
- `unit` (pieces|tablets|capsules|bottles|boxes|strips|vials|tubes|sachets)
- `storage_location` (nullable)
- `barcode` (nullable)
- `requires_prescription`
- `is_active`
- `created_at` (read-only)
- `updated_at` (read-only)
- computed read-only: `category_name`, `supplier_name`, `profit_per_unit`, `markup_percentage`, `days_to_expiry`

Manual stock adjustment request:
```json
{
  "adjustment_type": "increase",
  "quantity": 10,
  "reason": "Physical count correction"
}
```

## Stock transactions
Base path: `/api/stock-transactions/`

- `GET /api/stock-transactions/` -> List transactions.
  - Query params: `medicine`, `transaction_type`, `created_by`, `start_date`, `end_date`.
- `GET /api/stock-transactions/{id}/` -> Retrieve transaction by UUID.
- `GET /api/stock-transactions/summary/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` -> Summary stats.

StockTransaction fields:
- `id` (uuid, read-only)
- `medicine` (medicine id)
- `medicine_name` (read-only)
- `transaction_type`
- `transaction_type_display` (read-only)
- `quantity`
- `previous_quantity` (read-only)
- `new_quantity` (read-only)
- `reference_type` (nullable)
- `reference_id` (nullable)
- `notes` (nullable)
- `created_by` (user id)
- `created_by_username` (read-only)
- `transaction_date` (read-only)
