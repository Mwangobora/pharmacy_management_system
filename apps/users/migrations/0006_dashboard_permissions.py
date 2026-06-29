from django.db import migrations


DASHBOARD_PERMISSIONS = {
    'dashboard.overview.view': {
        'name': 'View dashboard overview',
        'module': 'dashboard',
        'resource': 'overview',
        'action': 'view',
        'description': 'Allows viewing the dashboard overview tab.',
    },
    'dashboard.sales.view': {
        'name': 'View sales dashboard',
        'module': 'dashboard',
        'resource': 'sales',
        'action': 'view',
        'description': 'Allows viewing sales dashboard analytics.',
    },
    'dashboard.inventory.view': {
        'name': 'View inventory dashboard',
        'module': 'dashboard',
        'resource': 'inventory',
        'action': 'view',
        'description': 'Allows viewing inventory dashboard analytics.',
    },
    'dashboard.inventory.view_cost_value': {
        'name': 'View inventory cost values',
        'module': 'dashboard',
        'resource': 'inventory',
        'action': 'view_cost_value',
        'description': 'Allows viewing stock values based on cost.',
    },
    'dashboard.finance.view': {
        'name': 'View finance dashboard',
        'module': 'dashboard',
        'resource': 'finance',
        'action': 'view',
        'description': 'Allows viewing finance dashboard analytics.',
    },
    'dashboard.finance.view_profit': {
        'name': 'View finance profit data',
        'module': 'dashboard',
        'resource': 'finance',
        'action': 'view_profit',
        'description': 'Allows viewing profit, margin, and cost of goods sold.',
    },
    'dashboard.operations.view': {
        'name': 'View operations dashboard',
        'module': 'dashboard',
        'resource': 'operations',
        'action': 'view',
        'description': 'Allows viewing operational dashboard analytics.',
    },
    'dashboard.performance.view': {
        'name': 'View performance dashboard',
        'module': 'dashboard',
        'resource': 'performance',
        'action': 'view',
        'description': 'Allows viewing performance dashboard analytics.',
    },
    'dashboard.performance.view_staff': {
        'name': 'View staff performance',
        'module': 'dashboard',
        'resource': 'performance',
        'action': 'view_staff',
        'description': 'Allows viewing cashier and staff performance details.',
    },
}


def seed_dashboard_permissions(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    PermissionProfile = apps.get_model('users', 'PermissionProfile')
    Role = apps.get_model('users', 'Role')

    role_content_type, _ = ContentType.objects.get_or_create(app_label='users', model='role')

    created_permissions = {}
    for codename, config in DASHBOARD_PERMISSIONS.items():
        permission, _ = Permission.objects.update_or_create(
            content_type=role_content_type,
            codename=codename,
            defaults={'name': config['name']},
        )
        PermissionProfile.objects.update_or_create(
            permission=permission,
            defaults={
                'module': config['module'],
                'resource': config['resource'],
                'action': config['action'],
                'description': config['description'],
                'is_active': True,
                'is_system': True,
                'is_assignable': True,
            },
        )
        created_permissions[codename] = permission

    role_map = {
        'system_administrator': list(DASHBOARD_PERMISSIONS.keys()),
        'pharmacist': [
            'dashboard.overview.view',
            'dashboard.sales.view',
            'dashboard.inventory.view',
            'dashboard.operations.view',
        ],
        'cashier': [
            'dashboard.overview.view',
            'dashboard.sales.view',
        ],
    }

    for code, permission_codes in role_map.items():
        try:
            role = Role.objects.get(code=code)
        except Role.DoesNotExist:
            continue
        role.permissions.add(
            *[
                created_permissions[permission_code]
                for permission_code in permission_codes
                if permission_code in created_permissions
            ]
        )


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0005_rename_access_audi_action_cdf690_idx_access_audi_action_3e0ca8_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_dashboard_permissions, migrations.RunPython.noop),
    ]
