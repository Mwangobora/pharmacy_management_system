# Sales API

Base URL: `/api`

## Customers
Base path: `/api/customers/`

- `GET /api/customers/` -> List customers.
  - Query params: `gender`, `search`, `ordering`.
- `POST /api/customers/` -> Create customer.
- `GET /api/customers/{id}/` -> Retrieve customer by UUID.
- `PUT/PATCH /api/customers/{id}/` -> Update customer.
- `DELETE /api/customers/{id}/` -> Delete customer.
- `GET /api/customers/{id}/purchase_history/` -> Customer sales.
- `GET /api/customers/{id}/loyalty_summary/` -> Loyalty stats.
- `POST /api/customers/{id}/add_loyalty_points/` -> Add points.

Customer fields:
- `id` (uuid, read-only)
- `first_name`
- `last_name`
- `full_name` (read-only)
- `phone`
- `email` (nullable)
- `address` (nullable)
- `date_of_birth` (nullable, YYYY-MM-DD)
- `gender` (M|F|Other)
- `loyalty_points`
- `created_at` (read-only)
- `updated_at` (read-only)
- computed read-only: `total_purchases`, `total_spent`

Add loyalty points request:
```json
{ "points": 50 }
```

## Sales
Base path: `/api/sales/`

- `GET /api/sales/` -> List sales.
  - Query params: `customer`, `payment_method`, `payment_status`, `served_by`, `start_date`, `end_date`, `search`, `ordering`.
- `POST /api/sales/` -> Create sale (standard model create).
- `GET /api/sales/{id}/` -> Retrieve sale by UUID.
- `PUT/PATCH /api/sales/{id}/` -> Update sale.
- `DELETE /api/sales/{id}/` -> Delete sale.
- `POST /api/sales/create_with_items/` -> Create sale with items + initial payment.
- `POST /api/sales/{id}/process_payment/` -> Add additional payment.
- `POST /api/sales/{id}/refund/` -> Refund all/part of a sale.
- `GET /api/sales/daily_summary/?date=YYYY-MM-DD` -> Daily summary (default: today).
- `GET /api/sales/top_selling/?days=30&limit=10` -> Top selling medicines.

Sale detail fields (from `SaleDetailSerializer`):
- `id` (uuid, read-only)
- `customer` (nullable)
- `invoice_number`
- `sale_date` (datetime)
- `total_amount`
- `tax_amount`
- `discount_amount`
- `net_amount`
- `payment_method` (cash|card|mobile|insurance|credit)
- `payment_status` (paid|partial|pending)
- `served_by` (user id)
- `notes` (nullable)
- `created_at` (read-only)
- `updated_at` (read-only)
- read-only: `customer_name`, `served_by_username`, `items`, `payments`, `total_paid`, `amount_due`, `total_profit`

Create sale with items request:
```json
{
  "customer": 1,
  "sale_date": "2025-01-15T10:00:00Z",
  "tax_amount": "100.00",
  "discount_amount": "50.00",
  "payment_method": "cash",
  "notes": "Walk-in",
  "items": [
    {
      "medicine": 1,
      "quantity": 2,
      "unit_price": "250.00",
      "batch_number": "B-001"
    }
  ],
  "payment_amount": "450.00",
  "transaction_ref": ""
}
```

Process payment request:
```json
{
  "amount": "200.00",
  "payment_method": "card",
  "transaction_ref": "TXN-123",
  "notes": "Visa"
}
```

Refund request:
```json
{
  "refund_amount": "100.00",
  "reason": "Returned items",
  "items_to_refund": [
    {"sale_item_id": 1, "quantity": 1}
  ]
}
```

## Payments
Base path: `/api/payments/` (read-only)

- `GET /api/payments/` -> List payments.
  - Query params: `sale`, `payment_method`, `received_by`, `ordering`.
- `GET /api/payments/{id}/` -> Retrieve payment by UUID.

Payment fields:
- `id` (uuid, read-only)
- `payment_id` (read-only)
- `sale`
- `amount`
- `payment_method`
- `payment_method_display` (read-only)
- `payment_date` (read-only)
- `transaction_ref` (nullable)
- `received_by`
- `received_by_username` (read-only)
- `notes` (nullable)
- `created_at` (read-only)
