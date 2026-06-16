from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils.text import slugify

from .models import AccessAuditLog, PermissionProfile, Role, User, UserDirectPermission, UserRoleAssignment
from .permission_registry import DEFAULT_ROLES, PERMISSIONS


def sync_permissions():
    content_type = ContentType.objects.get_for_model(Role)
    synced_permissions = []

    for codename, config in PERMISSIONS.items():
        permission, _ = Permission.objects.update_or_create(
            content_type=content_type,
            codename=codename,
            defaults={'name': config['name']},
        )
        PermissionProfile.objects.update_or_create(
            permission=permission,
            defaults={
                'module': config['module'],
                'resource': config['resource'],
                'action': config['action'],
                'description': config.get('description', ''),
                'is_active': True,
                'is_system': True,
                'is_assignable': True,
            },
        )
        synced_permissions.append(permission)

    return synced_permissions


def sync_default_roles():
    permissions_by_code = {permission.codename: permission for permission in Permission.objects.filter(codename__in=PERMISSIONS)}
    roles = []

    for code, config in DEFAULT_ROLES.items():
        role, _ = Role.objects.update_or_create(
            code=code,
            defaults={
                'name': config['name'],
                'description': config.get('description', ''),
                'is_active': True,
                'is_system': True,
            },
        )
        role.permissions.set([permissions_by_code[codename] for codename in config['permissions'] if codename in permissions_by_code])
        roles.append(role)

    return roles


def sync_existing_role_assignments():
    for user in User.objects.exclude(role__isnull=True).select_related('role'):
        UserRoleAssignment.objects.get_or_create(
            user=user,
            role=user.role,
            defaults={'is_active': True},
        )


def set_user_roles(user, roles, *, actor=None, reason=''):
    role_ids = {role.id for role in roles}
    current_assignments = {assignment.role_id: assignment for assignment in user.role_assignments.all()}

    with transaction.atomic():
        for role_id, assignment in current_assignments.items():
            should_be_active = role_id in role_ids
            if assignment.is_active != should_be_active:
                assignment.is_active = should_be_active
                assignment.save(update_fields=['is_active'])

        for role in roles:
            assignment, created = UserRoleAssignment.objects.get_or_create(
                user=user,
                role=role,
                defaults={'assigned_by': actor, 'is_active': True},
            )
            if not created and not assignment.is_active:
                assignment.is_active = True
                assignment.assigned_by = actor
                assignment.save(update_fields=['is_active', 'assigned_by'])

        user.increment_authorization_version()
        user.sync_legacy_role()

    log_access_event(
        actor=actor,
        action='user.roles.updated',
        target_user=user,
        after_state={'role_ids': sorted(role_ids)},
        reason=reason,
    )


def set_user_direct_permissions(user, permissions, *, actor=None, reason=''):
    permission_ids = {permission.id for permission in permissions}
    current_assignments = {assignment.permission_id: assignment for assignment in user.direct_permission_assignments.all()}

    with transaction.atomic():
        for permission_id, assignment in current_assignments.items():
            should_be_active = permission_id in permission_ids
            if assignment.is_active != should_be_active:
                assignment.is_active = should_be_active
                assignment.save(update_fields=['is_active'])

        for permission in permissions:
            assignment, created = UserDirectPermission.objects.get_or_create(
                user=user,
                permission=permission,
                defaults={'assigned_by': actor, 'is_active': True},
            )
            if not created and not assignment.is_active:
                assignment.is_active = True
                assignment.assigned_by = actor
                assignment.save(update_fields=['is_active', 'assigned_by'])

        user.increment_authorization_version()

    log_access_event(
        actor=actor,
        action='user.permissions.updated',
        target_user=user,
        after_state={'permission_ids': sorted(permission_ids)},
        reason=reason,
    )


def log_access_event(*, actor=None, action, target_user=None, target_role=None, target_permission=None, before_state=None, after_state=None, reason=''):
    AccessAuditLog.objects.create(
        actor=actor,
        target_user=target_user,
        target_role=target_role,
        target_permission=target_permission,
        action=action,
        before_state=before_state or {},
        after_state=after_state or {},
        reason=reason,
    )
