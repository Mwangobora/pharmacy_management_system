from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import AccessAuditLog, PermissionProfile, Role, User, UserDirectPermission, UserRoleAssignment


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
	list_display = ('name', 'code', 'is_active', 'is_system', 'created_at')
	list_filter = ('is_active', 'is_system')
	search_fields = ('name', 'code')
	ordering = ('name',)
	filter_horizontal = ('permissions',)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
	list_display = ('email', 'username', 'role', 'authorization_version', 'is_staff', 'is_superuser', 'is_active')
	list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
	search_fields = ('email', 'username')
	ordering = ('email',)
	fieldsets = (
		(None, {'fields': ('email', 'password')}),
		('Personal info', {'fields': ('username', 'role', 'authorization_version')}),
		('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
		('Important dates', {'fields': ('last_login',)}),
	)
	add_fieldsets = (
		(None, {
			'classes': ('wide',),
			'fields': ('email', 'username', 'password1', 'password2', 'role', 'groups', 'user_permissions'),
		}),
	)


@admin.register(UserRoleAssignment)
class UserRoleAssignmentAdmin(admin.ModelAdmin):
	list_display = ('user', 'role', 'is_active', 'assigned_at', 'expires_at')
	list_filter = ('is_active', 'role')
	search_fields = ('user__email', 'user__username', 'role__name')


@admin.register(UserDirectPermission)
class UserDirectPermissionAdmin(admin.ModelAdmin):
	list_display = ('user', 'permission', 'is_active', 'assigned_at', 'expires_at')
	list_filter = ('is_active',)
	search_fields = ('user__email', 'user__username', 'permission__codename')


@admin.register(PermissionProfile)
class PermissionProfileAdmin(admin.ModelAdmin):
	list_display = ('permission', 'module', 'resource', 'action', 'is_active', 'is_system')
	list_filter = ('module', 'resource', 'action', 'is_active', 'is_system')
	search_fields = ('permission__codename', 'permission__name')


@admin.register(AccessAuditLog)
class AccessAuditLogAdmin(admin.ModelAdmin):
	list_display = ('action', 'actor', 'target_user', 'target_role', 'created_at')
	list_filter = ('action', 'created_at')
	search_fields = ('actor__email', 'target_user__email', 'target_role__name', 'action')
