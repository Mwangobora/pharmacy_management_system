# Suppliers API

Base URL: `/api`

## Suppliers
Base path: `/api/suppliers/`

- `GET /api/suppliers/` -> List suppliers (default: only `is_active=true`).
  - Query params: `is_active`, `search`, `ordering`.
- `POST /api/suppliers/` -> Create supplier.
- `GET /api/suppliers/{id}/` -> Retrieve supplier by UUID.
- `PUT/PATCH /api/suppliers/{id}/` -> Update supplier.
- `DELETE /api/suppliers/{id}/` -> Soft delete (sets `is_active=false`).
- `GET /api/suppliers/{id}/purchases/` -> Purchase history.
- `GET /api/suppliers/{id}/medicines/` -> Medicines provided by supplier.
- `GET /api/suppliers/{id}/statistics/` -> Supplier stats.

Supplier fields:
- `id` (uuid, read-only)
- `name`
- `contact_person` (nullable)
- `phone`
- `email` (nullable)
- `address` (nullable)
- `tax_id` (nullable)
- `is_active`
- `created_at` (read-only)
- `updated_at` (read-only)
- computed read-only: `total_purchases`, `active_medicines_count`

## Purchases
Base path: `/api/purchases/`

- `GET /api/purchases/` -> List purchases.
  - Query params: `supplier`, `payment_status`, `start_date`, `end_date`, `search`, `ordering`.
- `POST /api/purchases/` -> Create purchase (standard model create).
- `GET /api/purchases/{id}/` -> Retrieve purchase by UUID.
- `PUT/PATCH /api/purchases/{id}/` -> Update purchase.
- `DELETE /api/purchases/{id}/` -> Delete purchase.
- `POST /api/purchases/create_with_items/` -> Create purchase with items.
- `POST /api/purchases/{id}/receive_items/` -> Mark items received.
- `PATCH /api/purchases/{id}/update_payment_status/` -> Update payment status.
- `GET /api/purchases/pending_payments/` -> Pending/partial purchases.
- `GET /api/purchases/dashboard_stats/` -> Purchase dashboard stats.

Purchase detail fields:
- `id` (uuid, read-only)
- `supplier` (supplier id)
- `invoice_number`
- `purchase_date` (YYYY-MM-DD)
- `total_amount`
- `tax_amount`
- `discount_amount`
- `net_amount`
- `payment_status` (pending|partial|paid)
- `notes` (nullable)
- `created_by` (user id)
- `created_at` (read-only)
- `updated_at` (read-only)
- read-only: `supplier_name`, `created_by_username`, `items`, `amount_paid`, `amount_due`

Create purchase with items request:
```json
{
  "supplier": 1,
  "invoice_number": "INV-001",
  "purchase_date": "2025-01-15",
  "tax_amount": "1000.00",
  "discount_amount": "500.00",
  "notes": "First order",
  "items": [
    {
      "medicine": 1,
      "quantity": 100,
      "unit_price": "50.00",
      "discount_percent": "5",
      "tax_percent": "18"
    }
  ]
}
```

Receive items request:
```json
{
  "items": [
    {"item_id": 10, "received_quantity": 50}
  ]
}
```

Update payment status request:
```json
{ "payment_status": "paid" }
```

## Purchase items
Base path: `/api/purchase-items/` (read-only)

- `GET /api/purchase-items/` -> List purchase items.
  - Query params: `purchase`, `medicine`.
- `GET /api/purchase-items/{id}/` -> Retrieve purchase item by UUID.

PurchaseItem fields:
- `id` (uuid, read-only)
- `medicine`
- `medicine_name` (read-only)
- `medicine_display_id` (read-only)
- `quantity`
- `unit_price`
- `discount_percent`
- `tax_percent`
- `subtotal` (read-only)
- `received_quantity`
