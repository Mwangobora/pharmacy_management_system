# Authentication and Users API

Base URL: `/api`

## Auth summary
- JWT auth via Djoser + SimpleJWT.
- Use `Authorization: Bearer <access_token>` for protected endpoints.

## Auth endpoints
- `POST /api/auth/register/` -> Create user (alias of Djoser create user).
- `POST /api/auth/login/` -> Obtain JWT access/refresh.
- `POST /api/auth/jwt/refresh/` -> Refresh access token.
- `POST /api/auth/jwt/verify/` -> Verify token.
- `POST /api/auth/logout/` -> Logout (exposed in `auth_info`; confirm frontend flow with backend).
- `GET /api/users/auth_info/` -> Lists auth endpoints and paths.

### Register
`POST /api/auth/register/`

Request body:
```json
{
  "email": "user@example.com",
  "username": "jdoe",
  "password": "secret"
}
```

Response (Djoser default):
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "jdoe"
}
```

### Login (JWT)
`POST /api/auth/login/`

Request body:
```json
{
  "email": "user@example.com",
  "password": "secret"
}
```

Response:
```json
{
  "refresh": "<jwt_refresh>",
  "access": "<jwt_access>"
}
```

### Refresh
`POST /api/auth/jwt/refresh/`

Request body:
```json
{ "refresh": "<jwt_refresh>" }
```

Response:
```json
{ "access": "<jwt_access>" }
```

## User management
Base path: `/api/users/`

- `GET /api/users/` -> List users (AllowAny).
- `POST /api/users/` -> Create user (AdminOrModelPermissions).
- `GET /api/users/{id}/` -> Retrieve user by UUID.
- `PUT/PATCH /api/users/{id}/` -> Update user.
- `DELETE /api/users/{id}/` -> Delete user.

User fields (from `UserSerializer`):
- `id` (uuid, read-only)
- `username`
- `email`
- `role` (role id, nullable)
- `role_name` (read-only)
- `role_detail` (read-only, nested role)
- `is_active` (read-only)
- `is_staff` (read-only)
- `created_at` (read-only)

## Roles
Base path: `/api/auth/roles/`

- `GET /api/auth/roles/`
- `POST /api/auth/roles/`
- `GET /api/auth/roles/{id}/`
- `PUT/PATCH /api/auth/roles/{id}/`
- `DELETE /api/auth/roles/{id}/`

Role fields:
- `id` (read-only)
- `name`
- `permissions` (array of permission ids)
- `permissions_detail` (read-only)
- `is_active`
- `created_at` (read-only)
- `updated_at` (read-only)

## Permissions
Base path: `/api/auth/permissions/`

- `GET /api/auth/permissions/`
- `POST /api/auth/permissions/`
- `GET /api/auth/permissions/{id}/`
- `PUT/PATCH /api/auth/permissions/{id}/`
- `DELETE /api/auth/permissions/{id}/`

Permission fields:
- `id` (read-only)
- `name`
- `codename`
- `content_type` (id)
- `content_type_label` (read-only)
- `content_type_model` (read-only)
