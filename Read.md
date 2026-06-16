# Pharmacy Management System Backend

## Overview

This backend is built with Django and Django REST Framework for a pharmacy management system. It handles authentication, authorization, inventory, suppliers, purchases, sales, customers, and payments.

## Main Stack

- Django
- Django REST Framework
- Djoser
- Simple JWT
- PostgreSQL
- Docker / Docker Compose
- Celery
- Redis

## Project Structure

- `pharmacy/`
  Django project configuration, settings, Celery bootstrap, and root URLs.

- `apps/users/`
  Custom user model, authentication APIs, RBAC logic, roles, permissions, serializers, and access-control endpoints.

- `apps/inventory/`
  Categories, medicines, stock transactions, stock adjustments, expiry tracking, and inventory summaries.

- `apps/suppliers/`
  Suppliers, purchases, receiving workflows, supplier summaries, and procurement-related operations.

- `apps/sales/`
  Customers, sales, sale items, payments, refunds, and sales summaries.

- `apps/*/services.py`
  Business logic for multi-step transactional workflows is kept inside each app instead of a shared top-level services folder.

- `docs/`
  Internal backend documentation such as auth and module notes.

## Authentication

The backend uses JWT authentication.

Important endpoints:

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/jwt/refresh/`
- `GET /api/auth/me/`

The backend remains the source of truth for roles and permissions. The frontend should use `/api/auth/me/` to load the current authenticated user profile and effective permissions.

## Authorization and RBAC

Authorization is implemented in `apps/users/`.

Main RBAC pieces:

- `User`
- `Role`
- Django `Permission`
- direct user permissions
- role assignments
- audit logs

Important files:

- [models.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/apps/users/models.py)
- [permissions.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/apps/users/permissions.py)
- [rbac.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/apps/users/rbac.py)
- [permission_registry.py](/home/francis/Desktop/francis/PMS/pharmacy_management_system/apps/users/permission_registry.py)

The backend computes effective permissions from active roles and direct permission assignments, then enforces them in the API layer.

## Core API Areas

### Inventory

Handles:

- categories
- medicines
- stock transactions
- low-stock checks
- expiry checks
- stock adjustments

Examples:

- `/api/categories/`
- `/api/medicines/`
- `/api/medicines/low_stock/`
- `/api/medicines/expiring_soon/`
- `/api/stock-transactions/`

### Suppliers and Purchases

Handles:

- suppliers
- purchases
- purchase items
- receiving purchased stock
- supplier statistics

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
- daily summaries

Examples:

- `/api/customers/`
- `/api/sales/`
- `/api/sales/create_with_items/`
- `/api/sales/{id}/process_payment/`
- `/api/sales/{id}/refund/`

## Service Layer

Views do not keep all business logic directly inside themselves. Transaction-heavy workflows are delegated to per-app service modules:

- [inventory services](/home/francis/Desktop/francis/PMS/pharmacy_management_system/apps/inventory/services.py)
- [sales services](/home/francis/Desktop/francis/PMS/pharmacy_management_system/apps/sales/services.py)
- [supplier services](/home/francis/Desktop/francis/PMS/pharmacy_management_system/apps/suppliers/services.py)

This keeps viewsets thinner and makes business logic easier to reuse and test.

## Docker

This backend is intended to run with Docker.

Main files:

- [Dockerfile](/home/francis/Desktop/francis/PMS/pharmacy_management_system/Dockerfile)
- [docker-compose.yml](/home/francis/Desktop/francis/PMS/pharmacy_management_system/docker-compose.yml)

Typical run command:

```bash
cd pharmacy_management_system
docker compose up --build
```

## Notes

- The backend uses PostgreSQL in Docker by default.
- Celery uses Redis as broker and result backend.
- Module imports now resolve from `apps.*`.
- If app paths are changed again, update `INSTALLED_APPS`, root URL imports, and any hardcoded dotted paths in settings.
