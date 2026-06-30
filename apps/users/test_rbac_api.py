import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from apps.users.models import PermissionProfile, Role, User, UserDirectPermission, UserRoleAssignment
from apps.users.rbac import get_access_content_type, set_role_permissions


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def superuser():
    return User.objects.create_superuser(
        email='superadmin@example.com',
        username='superadmin',
        password='secret123',
    )


@pytest.fixture
def authenticated_superuser(api_client, superuser):
    api_client.force_authenticate(user=superuser)
    return api_client


def create_permission(
    *,
    codename,
    name,
    module,
    resource,
    action,
    is_active=True,
    is_assignable=True,
    is_system=False,
):
    permission = Permission.objects.create(
        content_type=get_access_content_type(),
        codename=codename,
        name=name,
    )
    PermissionProfile.objects.create(
        permission=permission,
        module=module,
        resource=resource,
        action=action,
        description=f'{name} permission.',
        is_active=is_active,
        is_system=is_system,
        is_assignable=is_assignable,
    )
    return permission


@pytest.mark.django_db
def test_superuser_can_create_permission_definition_via_api(authenticated_superuser):
    response = authenticated_superuser.post(
        '/api/auth/permissions/',
        {
            'name': 'View clinical notes',
            'module': 'clinical',
            'resource': 'note',
            'action': 'view',
            'description': 'Allows viewing clinical notes.',
            'is_active': True,
            'is_system': False,
            'is_assignable': True,
        },
        format='json',
    )

    assert response.status_code == 201, response.json()
    payload = response.json()
    permission = Permission.objects.get(id=payload['id'])

    assert payload['codename'] == 'clinical.note.view'
    assert permission.name == 'View clinical notes'
    assert permission.profile.module == 'clinical'
    assert permission.profile.resource == 'note'
    assert permission.profile.action == 'view'
    assert permission.profile.is_system is False


@pytest.mark.django_db
def test_superuser_can_update_permission_definition_via_api(authenticated_superuser):
    permission = create_permission(
        codename='sales.dispense.view',
        name='View dispense queue',
        module='sales',
        resource='dispense',
        action='view',
    )

    response = authenticated_superuser.patch(
        f'/api/auth/permissions/{permission.id}/',
        {
            'name': 'Dispense medicines',
            'codename': 'sales.dispense.execute',
            'module': 'sales',
            'resource': 'dispense',
            'action': 'execute',
            'description': 'Allows dispensing medicines.',
            'is_active': False,
            'is_assignable': True,
        },
        format='json',
    )

    assert response.status_code == 200, response.json()
    permission.refresh_from_db()
    permission.profile.refresh_from_db()

    assert permission.name == 'Dispense medicines'
    assert permission.codename == 'sales.dispense.execute'
    assert permission.profile.action == 'execute'
    assert permission.profile.description == 'Allows dispensing medicines.'
    assert permission.profile.is_active is False


@pytest.mark.django_db
def test_role_permission_assignment_endpoint_sets_role_permissions(authenticated_superuser):
    role = Role.objects.create(name='Access Manager', code='access-manager')
    first_permission = create_permission(
        codename='inventory.batch.view',
        name='View batches',
        module='inventory',
        resource='batch',
        action='view',
    )
    second_permission = create_permission(
        codename='inventory.batch.update',
        name='Update batches',
        module='inventory',
        resource='batch',
        action='update',
    )

    response = authenticated_superuser.put(
        f'/api/auth/roles/{role.id}/permissions/',
        {
            'permission_ids': [first_permission.id],
            'permission_codenames': [second_permission.codename],
        },
        format='json',
    )

    assert response.status_code == 200, response.json()
    role.refresh_from_db()
    assigned_codenames = set(role.permissions.values_list('codename', flat=True))

    assert assigned_codenames == {
        'inventory.batch.view',
        'inventory.batch.update',
    }
    assert {item['codename'] for item in response.json()['permissions_detail']} == assigned_codenames


@pytest.mark.django_db
def test_user_role_assignment_endpoint_updates_effective_permissions(authenticated_superuser):
    permission = create_permission(
        codename='reports.sales.view',
        name='View sales reports',
        module='reports',
        resource='sales',
        action='view',
    )
    role = Role.objects.create(name='Reporting Manager', code='reporting-manager')
    set_role_permissions(role, [permission])
    target_user = User.objects.create_user(
        email='staff@example.com',
        username='staff',
        password='secret123',
    )

    response = authenticated_superuser.put(
        f'/api/users/{target_user.id}/roles/',
        {'role_codes': [role.code]},
        format='json',
    )

    assert response.status_code == 200, response.json()
    target_user.refresh_from_db()

    assert UserRoleAssignment.objects.filter(user=target_user, role=role, is_active=True).exists()
    assert permission.codename in response.json()['effective_permissions']
    assert permission.codename in target_user.get_effective_permissions()


@pytest.mark.django_db
def test_user_direct_permission_assignment_endpoint_updates_effective_permissions(authenticated_superuser):
    permission = create_permission(
        codename='dashboard.custom.view',
        name='View custom dashboard',
        module='dashboard',
        resource='custom',
        action='view',
    )
    target_user = User.objects.create_user(
        email='cashier@example.com',
        username='cashier',
        password='secret123',
    )

    response = authenticated_superuser.put(
        f'/api/users/{target_user.id}/permissions/',
        {'permission_codenames': [permission.codename]},
        format='json',
    )

    assert response.status_code == 200, response.json()
    target_user.refresh_from_db()

    assert UserDirectPermission.objects.filter(user=target_user, permission=permission, is_active=True).exists()
    assert permission.codename in response.json()['effective_permissions']
    assert {item['codename'] for item in response.json()['direct_permissions']} == {permission.codename}
    assert permission.codename in target_user.get_effective_permissions()
