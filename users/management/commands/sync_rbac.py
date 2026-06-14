from django.core.management.base import BaseCommand

from users.rbac import sync_default_roles, sync_existing_role_assignments, sync_permissions


class Command(BaseCommand):
    help = 'Synchronize system RBAC permissions, default roles, and legacy role assignments.'

    def handle(self, *args, **options):
        permissions = sync_permissions()
        roles = sync_default_roles()
        sync_existing_role_assignments()
        self.stdout.write(self.style.SUCCESS(f'Synchronized {len(permissions)} permissions and {len(roles)} default roles.'))
