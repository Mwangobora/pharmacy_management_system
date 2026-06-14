# Refactor Pharmacy System to Complete Dynamic Role-Based Access Control

The pharmacy management system is already functional, but its authentication, roles, permissions, API authorization, and frontend access control now need to be reviewed and refactored into a complete **dynamic Role-Based Access Control system**.

The system must not depend on hardcoded role names such as:

* `if user.role == "admin"`
* `if role === "pharmacist"`
* `isManager`
* `isCashier`
* Hardcoded permission arrays in the frontend
* Hardcoded sidebar visibility rules

Administrators must be able to create roles, assign permissions to roles, assign roles to users, and optionally assign direct permissions to individual users through APIs and the user-management interface.

The backend must remain the authoritative source for all authorization decisions.

---

# 1. Inspect the Existing Project First

Before changing code, inspect the complete existing implementation, including:

* User model
* Authentication system
* Login and refresh-token flow
* Django authentication configuration
* Existing roles or user types
* Existing permissions
* Existing API permission classes
* Existing serializers and viewsets
* Existing middleware
* Existing user-management APIs
* Existing frontend authentication state
* Existing route guards
* Sidebar navigation configuration
* Form fields and action-button permissions
* Existing audit-log implementation
* Existing notification components
* Existing API service architecture
* Existing Zustand, Context, Redux, or other state-management implementation

Do not replace working functionality unnecessarily.

Refactor existing structures cleanly and preserve compatibility where reasonable.

---

# 2. Main Goal

Implement a complete dynamic RBAC architecture where:

1. Permissions are defined in the backend.
2. Roles are stored in the database.
3. Permissions are assigned to roles through APIs.
4. Users can receive one or multiple roles.
5. Users may optionally receive direct permissions.
6. The frontend fetches the authenticated user's effective permissions from an API.
7. Routes, sidebar items, tabs, form fields, buttons, tables, drawers, and actions are displayed or enabled according to permissions.
8. Every protected backend operation validates permissions independently.
9. Frontend hiding is only a usability feature, not the security boundary.
10. No authorization decision depends only on frontend logic.

---

# 3. Required Authorization Model

Use the following relationship:

```text
User
  ├── Roles
  │     └── Permissions
  └── Direct Permissions
```

Effective permissions should be calculated from:

```text
Effective Permissions =
Permissions from all active assigned roles
+
Active direct permissions assigned to the user
-
Any explicitly revoked permissions, if revocation is supported
```

A user may have multiple roles, for example:

* Pharmacist
* Inventory Supervisor
* Report Viewer

The user's effective access should be the union of permissions from all assigned roles and direct permissions.

Do not restrict a user to only one hardcoded role unless the existing business requirement explicitly requires it.

---

# 4. Recommended Data Models

Review whether Django's existing `Group` and `Permission` models can be extended cleanly.

Prefer using Django's built-in permission framework where practical instead of recreating authentication and authorization from scratch.

The final implementation should provide models equivalent to the following concepts.

## Role

A role should contain:

* ID
* Name
* Unique code or slug
* Description
* Permissions
* Active status
* System role indicator
* Created by
* Updated by
* Created date
* Updated date

Example role codes:

```text
pharmacist
cashier
inventory_manager
procurement_officer
branch_manager
system_administrator
```

Role codes must be database values, not authorization conditions hardcoded throughout the application.

## Permission

Every permission should contain:

* ID
* Name
* Codename
* Module
* Resource
* Action
* Description
* Active status
* System permission indicator

Suggested permission format:

```text
module.resource.action
```

Examples:

```text
sales.sale.view
sales.sale.create
sales.sale.complete
sales.sale.cancel
sales.sale.refund
sales.sale.discount
sales.sale.override_price

inventory.medicine.view
inventory.medicine.create
inventory.medicine.update
inventory.medicine.delete

inventory.batch.view
inventory.batch.create
inventory.batch.update
inventory.batch.adjust_stock

prescriptions.prescription.view
prescriptions.prescription.verify
prescriptions.prescription.approve

customers.customer.view
customers.customer.create
customers.customer.update

reports.sales.view
reports.inventory.view
reports.financial.view
reports.export

users.user.view
users.user.create
users.user.update
users.user.activate
users.user.deactivate

access.role.view
access.role.create
access.role.update
access.role.delete
access.role.assign_permissions

access.permission.view
access.permission.assign

access.user.assign_roles
access.user.assign_permissions

settings.system.view
settings.system.update
```

Use a consistent naming convention across the whole application.

## User Role Assignment

Store:

* User
* Role
* Assigned by
* Assigned date
* Expiry date, if supported
* Active status

## Direct User Permission Assignment

Store:

* User
* Permission
* Assigned by
* Assigned date
* Expiry date, if supported
* Active status

Direct user permissions should be exceptional overrides, not the normal way of assigning access.

---

# 5. Permission Registry

Create a centralized backend permission registry.

Permissions must not be declared randomly across multiple files without structure.

The registry should define:

* Permission codename
* Human-readable name
* Module
* Resource
* Action
* Description

Example structure:

```python
PERMISSIONS = {
    "sales.sale.view": {
        "name": "View sales",
        "module": "sales",
        "resource": "sale",
        "action": "view",
        "description": "Allows the user to view sales records.",
    },
    "sales.sale.create": {
        "name": "Create sale",
        "module": "sales",
        "resource": "sale",
        "action": "create",
        "description": "Allows the user to create a new pharmacy sale.",
    },
}
```

Create a safe mechanism such as:

* Data migration
* Management command
* Application startup synchronization command
* Seeder

This mechanism should synchronize defined system permissions with the database without deleting valid administrator-created configuration unexpectedly.

Permission synchronization should be idempotent.

---

# 6. Backend Authorization Enforcement

Every protected API endpoint must check permissions on the backend.

Do not rely on:

* Hidden frontend buttons
* Disabled frontend fields
* Sidebar visibility
* Route guards alone

Implement reusable permission classes such as:

```python
HasPermission
HasAnyPermission
HasAllPermissions
```

Possible usage:

```python
permission_classes = [
    IsAuthenticated,
    HasPermission("sales.sale.create"),
]
```

Or declarative configuration:

```python
required_permissions = {
    "list": ["sales.sale.view"],
    "retrieve": ["sales.sale.view"],
    "create": ["sales.sale.create"],
    "update": ["sales.sale.update"],
    "partial_update": ["sales.sale.update"],
    "destroy": ["sales.sale.delete"],
}
```

Create a reusable DRF mixin that selects permissions based on:

* Viewset
* Action
* HTTP method
* Custom action

Custom actions must also be protected.

Example:

```python
@action(detail=True, methods=["post"])
def refund(self, request, pk=None):
    ...
```

The refund action must require:

```text
sales.sale.refund
```

---

# 7. Object-Level and Branch-Level Permissions

Where the system supports multiple branches, pharmacies, tenants, or stores, permission checks must also respect data scope.

A permission such as:

```text
sales.sale.view
```

does not automatically mean the user may view every branch's sales.

Support access scopes such as:

* Own records
* Assigned branch
* Multiple assigned branches
* All branches
* Entire organization

Use the existing tenant or branch architecture.

Do not expose records from another tenant or organization.

Permission checks and queryset filtering must work together.

Examples:

* Cashier sees sales from the assigned branch.
* Branch manager sees all records from their branch.
* System administrator may see all branches where permitted.
* Pharmacist approves prescriptions only for an assigned pharmacy or branch.

Never rely only on client-supplied `branch_id` or `tenant_id`.

---

# 8. Superuser and System Administrator Behaviour

Django superusers may bypass permission checks for emergency administration.

However:

* Normal administrators should still use database roles and permissions.
* Do not treat every staff user as fully authorized.
* `is_staff` should only allow administration-site access where appropriate.
* `is_superuser` must not be used as the normal business role.
* A `System Administrator` role should exist as a normal dynamic role where practical.

Protect system roles and critical permissions from accidental deletion.

---

# 9. Authentication APIs

Review and preserve the existing JWT or session authentication system.

The login response should remain focused and secure.

Do not place all authorization logic permanently inside the JWT token because role and permission assignments may change before token expiry.

The frontend should retrieve current authorization data from a dedicated endpoint.

Create or improve:

```http
GET /api/v1/auth/me/
```

The response should include:

```json
{
  "id": "user-id",
  "email": "user@example.com",
  "full_name": "User Name",
  "is_active": true,
  "roles": [
    {
      "id": "role-id",
      "name": "Pharmacist",
      "code": "pharmacist"
    }
  ],
  "permissions": [
    "sales.sale.view",
    "sales.sale.create",
    "inventory.medicine.view",
    "prescriptions.prescription.verify"
  ],
  "branches": [],
  "default_branch": null
}
```

Only return fields needed by the client.

Do not expose sensitive user or internal security information.

The permissions returned must be the calculated effective permissions for that user.

---

# 10. Authorization Versioning and Refresh

Role and permission assignments can change while a user is logged in.

Implement a reliable strategy so permission changes take effect without requiring long delays.

Possible approach:

* Add `authorization_version` to the user.
* Increment it whenever roles or direct permissions change.
* Include the version in the authenticated-user response.
* Refetch permissions after login, refresh, account update, or authorization failure.
* Invalidate cached permission data when assignments change.

Do not keep stale permissions indefinitely in frontend local storage.

Do not store sensitive tokens in unsafe browser storage if the existing system uses secure HttpOnly cookies.

Preserve the current secure token strategy.

---

# 11. Role Management APIs

Implement secured CRUD APIs for roles.

Required endpoints should support:

```http
GET    /api/v1/access/roles/
POST   /api/v1/access/roles/
GET    /api/v1/access/roles/{id}/
PATCH  /api/v1/access/roles/{id}/
DELETE /api/v1/access/roles/{id}/
```

Additional endpoints may include:

```http
GET /api/v1/access/roles/{id}/permissions/
PUT /api/v1/access/roles/{id}/permissions/
POST /api/v1/access/roles/{id}/assign-permissions/
POST /api/v1/access/roles/{id}/remove-permissions/
```

Use one clear assignment pattern consistently.

Role APIs must support:

* Search
* Pagination
* Active/inactive filtering
* Module filtering
* Ordering
* Permission count
* User count

Prevent deletion of a role that is protected or currently required by the system unless there is a safe reassignment process.

---

# 12. Permission APIs

Implement read-focused permission APIs.

Administrators should normally select from registered system permissions instead of freely inventing invalid permission codes.

Required endpoint:

```http
GET /api/v1/access/permissions/
```

Support:

* Search by name or codename
* Filter by module
* Filter by resource
* Filter by action
* Grouping by module
* Pagination where appropriate

Example response:

```json
{
  "module": "sales",
  "permissions": [
    {
      "id": "permission-id",
      "codename": "sales.sale.view",
      "name": "View sales",
      "resource": "sale",
      "action": "view",
      "description": "Allows viewing pharmacy sales."
    }
  ]
}
```

Do not let unauthorized users enumerate the entire permission system.

---

# 13. User Role and Permission Assignment APIs

Implement secure APIs for managing user access.

Possible endpoints:

```http
GET /api/v1/users/{id}/access/
PUT /api/v1/users/{id}/roles/
PUT /api/v1/users/{id}/permissions/
```

The access response should show:

* Assigned roles
* Permissions inherited from roles
* Direct permissions
* Effective permissions
* Assigned branches or scopes
* Assignment metadata

Example:

```json
{
  "roles": [],
  "inherited_permissions": [],
  "direct_permissions": [],
  "effective_permissions": []
}
```

Assignments must be performed inside database transactions.

Validate that:

* Role exists
* Role is active
* Permission exists
* Permission is active
* Administrator has permission to assign access
* Tenant or organization boundaries are respected
* A user cannot assign permissions beyond their own permitted administrative scope unless explicitly allowed

Do not allow privilege escalation.

---

# 14. Prevent Privilege Escalation

A user who can manage users should not automatically be able to grant every permission.

Separate permissions such as:

```text
users.user.update
access.user.assign_roles
access.user.assign_permissions
access.role.assign_permissions
```

Consider implementing an assignment rule where administrators may only assign:

* Roles within their administrative scope
* Permissions they themselves possess
* Permissions marked as assignable
* Permissions allowed by their tenant or organization

Protect critical permissions such as:

* Managing system administrators
* Editing access-control configuration
* Accessing audit records
* Changing security settings
* Viewing financial reports
* Performing refunds
* Overriding prices
* Adjusting stock

---

# 15. Frontend Authorization Architecture

The frontend must fetch roles and effective permissions from the backend.

Do not hardcode access rules based on role names.

Create or improve a centralized authorization store.

Example interface:

```typescript
interface AuthUser {
  id: string;
  fullName: string;
  email: string;
  roles: RoleSummary[];
  permissions: string[];
  authorizationVersion?: number;
}
```

Provide reusable helpers:

```typescript
can(permission: string): boolean
canAny(permissions: string[]): boolean
canAll(permissions: string[]): boolean
```

Example:

```typescript
if (can("sales.sale.refund")) {
  // show refund action
}
```

Do not use:

```typescript
if (user.role === "admin")
```

---

# 16. Reusable Frontend Permission Components

Create reusable components or hooks such as:

```typescript
usePermissions()
```

```tsx
<Can permission="sales.sale.create">
  <CreateSaleButton />
</Can>
```

```tsx
<CanAny permissions={[
  "reports.sales.view",
  "reports.inventory.view"
]}>
  <ReportsNavigation />
</CanAny>
```

```tsx
<CanAll permissions={[
  "sales.sale.view",
  "sales.sale.refund"
]}>
  <RefundButton />
</CanAll>
```

Also support a fallback:

```tsx
<Can
  permission="inventory.medicine.update"
  fallback={<ReadOnlyMedicineDetails />}
>
  <EditableMedicineForm />
</Can>
```

Avoid scattering permission array checks throughout the codebase.

---

# 17. Sidebar and Navigation Permissions

Update the sidebar configuration so each item can declare its required permission.

Example:

```typescript
{
  title: "Sales",
  href: "/sales",
  requiredPermissions: ["sales.sale.view"],
  permissionMode: "any"
}
```

A parent navigation group should be shown only when at least one authorized child is visible.

Do not hardcode navigation based on role names.

The sidebar must automatically react after permissions are refetched.

Examples:

* Sales menu requires a sales-related permission.
* Inventory menu requires an inventory-related permission.
* User management requires `users.user.view`.
* Roles tab requires `access.role.view`.
* Permissions tab requires `access.permission.view`.
* Audit tab requires `audit.log.view`.

---

# 18. Route Guards

Protect frontend routes according to required permissions.

Each protected route should declare its required permission or permissions.

Unauthorized users should receive a proper access-denied state, not a blank page.

Access-denied UI should include:

* Clear title
* Explanation that the account lacks permission
* Back button
* Link to an accessible dashboard where appropriate

Do not expose protected page data while checking permissions.

Handle:

* Loading authentication
* Authenticated but unauthorized
* Expired session
* Account disabled
* API returning `401`
* API returning `403`

Use:

* `401` for unauthenticated sessions
* `403` for authenticated users without permission

---

# 19. Permission-Controlled UI Fields

UI fields and controls must be driven by permissions received from the API.

Examples:

* Cost price visible only with `inventory.medicine.view_cost_price`.
* Price editing enabled only with `sales.sale.override_price`.
* Discount field enabled only with `sales.sale.discount`.
* Refund button visible only with `sales.sale.refund`.
* Stock adjustment form enabled only with `inventory.batch.adjust_stock`.
* Prescription approval action enabled only with `prescriptions.prescription.approve`.
* User activation action enabled only with `users.user.activate`.
* Role assignment enabled only with `access.user.assign_roles`.

Fields should support:

* Hidden state
* Read-only state
* Disabled state
* Masked value where necessary

Choose the correct state according to security and usability.

Sensitive values should not be returned by the API when the user lacks permission.

Do not merely hide sensitive values using CSS.

---

# 20. API Response Field Security

Refactor serializers so unauthorized users do not receive restricted fields.

Examples:

* Cost price
* Profit margin
* Supplier financial details
* Internal audit metadata
* User security details
* Financial summaries
* Controlled-medicine information where restricted

Use permission-aware serializers or serializer field filtering where appropriate.

The backend must control field exposure.

Example:

```python
if not request.user.has_permission(
    "inventory.medicine.view_cost_price"
):
    fields.pop("cost_price", None)
```

Keep the implementation reusable and testable.

---

# 21. Action-Level Permissions

A user may view a resource but not modify it.

Implement separate permissions for actions such as:

* View
* Create
* Update
* Delete
* Approve
* Reject
* Activate
* Deactivate
* Export
* Print
* Refund
* Cancel
* Verify
* Adjust
* Assign
* Override

Do not use one broad permission such as `manage_sales` for every operation.

Use granular permissions where business risk differs.

---

# 22. User Management UI

Update the existing user-management interface with clean horizontal tabs:

* Users
* Pending Users
* Roles
* Permissions
* Audit Logs

Show only tabs the current administrator can access.

## Users Tab

The user details drawer should contain an `Access` section showing:

* Assigned roles
* Direct permissions
* Effective permissions
* Assigned branch or access scope
* Account status
* Last access update
* Updated by

Authorized administrators should be able to:

* Assign roles
* Remove roles
* Assign direct permissions
* Remove direct permissions
* Activate or deactivate the user
* View access history

Use searchable selectors and grouped permissions.

Do not use an uncontrolled list of hundreds of checkboxes on one screen.

## Roles Tab

Allow authorized administrators to:

* Create a role
* Edit role name and description
* Activate or deactivate a role
* Search permissions
* Filter permissions by module
* Select all permissions within a module
* Review selected permissions before saving
* View users assigned to the role
* Duplicate a role where useful
* Delete non-protected roles safely

## Permissions Tab

Display permissions grouped by module and resource.

Show:

* Permission name
* Codename
* Description
* Module
* Resource
* Action
* Roles using the permission
* Users receiving it directly

System permissions should normally be read-only from the UI.

---

# 23. Audit Logging

Every sensitive access-control action must be audited.

Audit events should include:

* Role created
* Role updated
* Role deleted
* Role activated or deactivated
* Permission assigned to role
* Permission removed from role
* Role assigned to user
* Role removed from user
* Direct permission assigned
* Direct permission removed
* User activated
* User deactivated
* Unauthorized access attempt
* Permission-protected action denied

Store:

* Actor
* Target user or role
* Action
* Before state
* After state
* Timestamp
* IP address where available
* Request ID
* Tenant or branch
* Reason where required

Avoid logging passwords, tokens, secrets, or unnecessary sensitive data.

---

# 24. Caching

Permission calculation may be cached for performance, but the cache must invalidate when:

* Role permissions change
* User roles change
* Direct permissions change
* Role is activated or deactivated
* User is activated or deactivated
* Permission is activated or deactivated
* Branch assignment changes

Use a reliable cache key such as:

```text
user_permissions:{user_id}:{authorization_version}
```

Do not cache permission results permanently.

The database remains the source of truth.

---

# 25. Transactions and Concurrency

Use atomic transactions when:

* Assigning roles
* Removing roles
* Assigning permissions
* Updating role permissions
* Changing access scopes
* Incrementing authorization versions
* Writing audit logs

Prevent partial access updates.

Use safe handling for concurrent administrator changes.

---

# 26. Validation and Error Responses

Return consistent errors.

Example unauthorized response:

```json
{
  "detail": "You do not have permission to perform this action.",
  "code": "permission_denied",
  "required_permissions": [
    "sales.sale.refund"
  ]
}
```

Do not expose unnecessary security internals in production.

Handle:

* Invalid role
* Inactive role
* Invalid permission
* Protected role
* Duplicate assignment
* Cross-tenant assignment
* Insufficient assignment authority
* Attempted privilege escalation
* Last administrator removal
* Self-deactivation where prohibited

---

# 27. Database Migration and Existing Users

Create safe database migrations.

Do not break existing users.

The migration process should:

1. Create the new access-control structures.
2. Register all permissions.
3. Create standard default roles.
4. Map existing user types or role values into the new roles.
5. Assign equivalent permissions.
6. Preserve existing active users.
7. Verify that at least one administrative account retains access.
8. Remove old hardcoded role fields only after migration is confirmed.

Do not delete the old role implementation before existing data is migrated.

Add temporary compatibility logic only where required, then remove it after migration.

---

# 28. Suggested Default Roles

Create default roles through seed data, not hardcoded runtime conditions.

Possible roles:

## System Administrator

Full permitted system administration.

## Pharmacy Manager

May manage:

* Sales
* Medicines
* Inventory
* Staff operations
* Reports
* Pharmacy settings

## Pharmacist

May:

* Search medicines
* Process permitted sales
* Review prescriptions
* Approve prescription medicines
* View medicine details
* View stock

## Cashier or Seller

May:

* Search medicines
* Create sales
* Add items to cart
* Receive allowed payments
* Print receipts
* View own or branch sales

Should not automatically:

* View cost price
* Adjust stock
* Override prices
* Approve restricted medicines
* Manage users
* View all financial reports

## Inventory Manager

May:

* Manage medicines
* Manage batches
* Receive stock
* Adjust stock where authorized
* View expiry and low-stock information

## Procurement Officer

May manage:

* Suppliers
* Purchase requests
* Purchase orders
* Receiving workflow where permitted

## Report Viewer

Read-only access to selected reports.

These are initial database roles. Administrators must be able to modify them according to business rules.

---

# 29. Tests

Create comprehensive backend tests for:

* Unauthenticated access returns `401`
* Authenticated unauthorized access returns `403`
* Authorized access succeeds
* Role permissions are inherited
* Multiple roles combine permissions
* Direct permissions work
* Inactive roles do not grant access
* Inactive permissions do not grant access
* Removed permissions stop working
* Cross-tenant data is blocked
* Branch scope is respected
* Sensitive serializer fields are excluded
* Custom viewset actions are protected
* Privilege escalation is blocked
* Audit records are created
* Permission cache invalidates correctly
* Existing users migrate correctly
* Superuser behaviour is controlled

Create frontend tests for:

* Permission helper functions
* Sidebar filtering
* Protected routes
* Authorized and unauthorized buttons
* Read-only fields
* Permission refresh
* `401` handling
* `403` handling
* Empty permission state
* Multiple-role permissions

---

# 30. Code Quality Requirements

The implementation must be:

* Modular
* Testable
* Type-safe
* Reusable
* Consistent with the current architecture
* Free from duplicated permission-checking logic
* Secure by default

Use:

* Services for business logic
* Selectors for complex reads where the project already uses them
* Reusable DRF permission classes
* Reusable frontend authorization hooks
* Strong TypeScript types
* Clear naming
* Database constraints
* Indexes for frequently queried assignment fields
* Transactions for access changes

Avoid:

* Huge serializers
* Huge viewsets
* Permission checks scattered everywhere
* Hardcoded role-name conditions
* Hardcoded frontend permission lists
* Authorization only in React components
* Trusting user IDs, branch IDs, or role IDs from the client without validation

---

# 31. Required Permission Mapping

Review every existing backend endpoint and frontend action.

Create a permission matrix covering:

* Module
* Resource
* Endpoint
* HTTP method
* Viewset action
* Required permission
* Scope
* Sensitive response fields
* Corresponding frontend route
* Corresponding UI action

Example:

| Module    | Resource | Action             | Permission                       |
| --------- | -------- | ------------------ | -------------------------------- |
| Sales     | Sale     | List               | `sales.sale.view`                |
| Sales     | Sale     | Create             | `sales.sale.create`              |
| Sales     | Sale     | Complete           | `sales.sale.complete`            |
| Sales     | Sale     | Refund             | `sales.sale.refund`              |
| Inventory | Medicine | View               | `inventory.medicine.view`        |
| Inventory | Medicine | Create             | `inventory.medicine.create`      |
| Inventory | Medicine | Update             | `inventory.medicine.update`      |
| Inventory | Batch    | Adjust stock       | `inventory.batch.adjust_stock`   |
| Users     | User     | Assign role        | `access.user.assign_roles`       |
| Access    | Role     | Update permissions | `access.role.assign_permissions` |

Do not leave existing endpoints unreviewed.

---

# 32. Implementation Order

Perform the refactor in this order:

1. Inspect the current authentication and authorization system.
2. Produce a concise internal map of current models, APIs, and frontend checks.
3. Design the permission naming convention.
4. Create or refactor role and permission models.
5. Add migrations and safe existing-user migration.
6. Add the permission registry and synchronization mechanism.
7. Implement effective-permission calculation.
8. Implement backend permission classes and viewset mixins.
9. Protect all existing APIs.
10. Add branch, tenant, and object-level filtering.
11. Implement role and permission management APIs.
12. Update the `/auth/me/` endpoint.
13. Add audit logging.
14. Implement cache invalidation.
15. Refactor the frontend authentication store.
16. Add `can`, `canAny`, and `canAll`.
17. Refactor sidebar and route guards.
18. Refactor tabs, fields, buttons, drawers, tables, and forms.
19. Build or update the user-access management UI.
20. Add backend and frontend tests.
21. Remove obsolete hardcoded authorization conditions.
22. Verify all existing workflows.

---

# 33. Final Acceptance Criteria

The work is complete only when:

* Admins can create and update roles from the UI.
* Admins can assign permissions to roles using APIs.
* Admins can assign one or multiple roles to users.
* Authorized admins can assign direct user permissions.
* User effective permissions are calculated dynamically.
* The frontend fetches permissions from the backend.
* Sidebar items are permission-controlled.
* Routes are permission-controlled.
* Tabs are permission-controlled.
* Form fields and sensitive values are permission-controlled.
* Buttons and row actions are permission-controlled.
* APIs independently enforce permissions.
* Cross-branch and cross-tenant access is prevented.
* Sensitive fields are not returned to unauthorized users.
* Changes to permissions take effect reliably.
* Access-control changes are audited.
* Existing users and workflows continue working.
* There are no remaining authorization checks based on hardcoded role names.
* Tests cover authentication, authorization, scopes, APIs, and UI behaviour.

Do not implement only the frontend interface.

Do not implement only role assignment without backend endpoint protection.

Do not simply hide buttons.

Deliver a complete, dynamic, API-driven RBAC system integrated throughout the pharmacy backend and frontend.
