"""
Legacy helper for bootstrapping access control.

Prefer:
    python manage.py sync_rbac
"""

from users.rbac import sync_default_roles, sync_existing_role_assignments, sync_permissions

permissions = sync_permissions()
roles = sync_default_roles()
sync_existing_role_assignments()

print(f'Synchronized {len(permissions)} permissions and {len(roles)} roles.')
