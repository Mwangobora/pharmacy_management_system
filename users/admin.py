from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Role, User


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
	list_display = ('name', 'is_active', 'created_at')
	list_filter = ('is_active',)
	search_fields = ('name',)
	ordering = ('name',)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
	list_display = ('email', 'username', 'role', 'is_staff', 'is_superuser', 'is_active')
	list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
	search_fields = ('email', 'username')
	ordering = ('email',)
	fieldsets = (
		(None, {'fields': ('email', 'password')}),
		('Personal info', {'fields': ('username', 'role')}),
		('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
		('Important dates', {'fields': ('last_login',)}),
	)
	add_fieldsets = (
		(None, {
			'classes': ('wide',),
			'fields': ('email', 'username', 'password1', 'password2', 'role'),
		}),
	)
