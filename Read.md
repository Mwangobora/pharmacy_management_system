# Pharmacy Management System Backend

## Overview

This backend powers a pharmacy management system built with Django and Django REST Framework. It exposes APIs for inventory, procurement, sales, customers, payments, and access control. The backend is the source of truth for authentication, authorization, business rules, and data validation.

## Main Stack

- Django
- Django REST Framework
- Djoser
- Simple JWT
- PostgreSQL
- Docker / Docker Compose
- Celery and Redis

## Project Structure

- `pharmacy/`
  Main Django project configuration, settings, and root URLs.

- `apps/users/`
  Custom user model, authentication, RBAC, roles, permissions, serializers, and user-management APIs.

- `apps/inventory/`
  Category management, medicines, stock tracking, expiry checks, and stock adjustment flows.

- `apps/suppliers/`
  Supplier records, purchases, receiving workflows, and procurement-related summaries.

- `apps/sales/`
  Customers, sales, payments, refunds, and sales summaries.

- `apps/*/services.py`
  Each business area now keeps its own transactional service logic inside the same app instead of using a shared top-level `services/` folder.

## Authentication

The backend uses JWT authentication.

Important auth endpoints:

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/jwt/refresh/`
- `GET /api/auth/me/`

The login response is intentionally small and the backend remains authoritative for access decisions. The frontend should rely on `/api/auth/me/` to get current roles and effective permissions.

## Authorization and RBAC

The backend uses a dynamic RBAC approach centered in `apps/users/`.

Authorization model:

- `User`
- `Role`
- `Role -> Permissions`
- `Direct user permissions`

Effective permissions are calculated on the backend from:

- active assigned roles
- active direct permissions
- Django permissions already attached to the user where applicable

Key RBAC files:

- [users/models.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/apps/users/models.py)
- [users/permissions.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/apps/users/permissions.py)
- [users/rbac.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/apps/users/rbac.py)
- [users/permission_registry.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/apps/users/permission_registry.py)

Important concepts:

- permission registry for system permissions
- default roles synced from backend definitions
- per-view required permissions
- backend-only enforcement of protected actions
- audit log model for access-control changes

## API Modules

### Inventory

Handles:

- categories
- medicines
- stock transactions
- low stock and expiry monitoring
- stock adjustment

Examples:

- `/api/categories/`
- `/api/medicines/`
- `/api/medicines/low_stock/`
- `/api/medicines/expiring_soon/`
- `/api/stock-transactions/`

### Procurement

Handles:

- suppliers
- purchases
- purchase items
- receiving items
- procurement summaries

Examples:

- `/api/suppliers/`
- `/api/purchases/`
- `/api/purchases/create_with_items/`
- `/api/purchases/{id}/receive_items/`

### Sales

Handles:

- customers
- sales
- sale items
- payments
- refunds
- sales summaries

Examples:

- `/api/customers/`
- `/api/sales/`
- `/api/sales/create_with_items/`
- `/api/sales/{id}/process_payment/`
- `/api/sales/{id}/refund/`
- `/api/payments/`

## Business Logic

The backend does not try to keep all logic inside views. Multi-step flows are delegated to service classes such as inventory, purchase, and sales services. This keeps transactional logic reusable and easier to test.

Examples of backend-controlled rules:

- preventing sale of expired medicine
- checking stock availability
- calculating totals
- creating payments and refunds
- adjusting stock through controlled flows
- permission-based field exposure

## Sensitive Data Handling

The backend should decide whether certain fields are returned at all.

Examples:

- cost price
- markup
- profit-related values
- restricted operational metadata

This is safer than only hiding values in the frontend.

## Docker-Based Development

This backend is intended to run in Docker, not as a plain host-only Django process.

Relevant files:

- [docker-compose.yml](/home/francis/Desktop/francis/PMS/pharmacy_management_system/docker-compose.yml)
- [Dockerfile](/home/francis/Desktop/francis/PMS/pharmacy_management_system/Dockerfile)

Typical operations should be done through the container, for example:

- migrations
- management commands
- RBAC sync
- shell access

## Data and Database

The backend uses PostgreSQL and includes migrations for application models. User authentication uses a custom `User` model defined in `users/models.py`.

Important backend data areas:

- users and access control
- medicines and stock levels
- purchases and suppliers
- sales and payments
- audit-oriented access records

## Recommended Backend Entry Points

If you are exploring the backend, start here:

- [pharmacy/settings.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/pharmacy/settings.py)
- [pharmacy/urls.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/pharmacy/urls.py)
- [users/models.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/users/models.py)
- [users/views.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/users/views.py)
- [inventory/views.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/inventory/views.py)
- [suppliers/views.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/suppliers/views.py)
- [sales/views.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/sales/views.py)

## Current Direction

The backend is moving toward:

- stronger dynamic RBAC
- cleaner permission enforcement
- safer serializer-level field filtering
- more reusable business services
- cleaner Docker-based developer workflows

This makes the backend better suited for a pharmacy environment where operational safety, access control, and data integrity matter.
