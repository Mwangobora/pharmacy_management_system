import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Permission
from django.utils import timezone
from django.utils.text import slugify


class UserManager(BaseUserManager):
    """Custom user manager"""
    
    def create_user(self, email, password=None, **extra_fields):
        """Create and return a regular user"""

        if not email:
            raise ValueError('Users must have an email address')
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        """Create and return a superuser"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')
        
        return self.create_user(email, password, **extra_fields)


class Role(models.Model):
    """User role managed from the admin panel"""

    name = models.CharField(max_length=50, unique=True)
    code = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name='roles')
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_roles',
    )
    updated_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_roles',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'roles'
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
        ]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model for pharmacy staff"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=50, unique=True)
    email = models.EmailField(max_length=100, unique=True)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True, related_name='users')
    authorization_version = models.PositiveIntegerField(default=1)
    
    # Django required fields for admin
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['username']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        role_name = self.primary_role.name if self.primary_role else 'No role'
        return f"{self.username} ({role_name})"

    @property
    def primary_role(self):
        assignment = self.role_assignments.select_related('role').filter(is_active=True).order_by('assigned_at').first()
        if assignment:
            return assignment.role
        return self.role

    def get_active_roles(self):
        now = timezone.now()
        roles = list(
            self.role_assignments.select_related('role')
            .filter(
                is_active=True,
                role__is_active=True,
            )
            .filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now))
            .values_list('role', flat=True)
        )
        if self.role_id and self.role_id not in roles and self.role and self.role.is_active:
            roles.append(self.role_id)
        return Role.objects.filter(id__in=roles, is_active=True)

    def get_active_direct_permissions(self):
        now = timezone.now()
        return Permission.objects.filter(
            direct_user_assignments__user=self,
            direct_user_assignments__is_active=True,
        ).filter(
            models.Q(direct_user_assignments__expires_at__isnull=True) |
            models.Q(direct_user_assignments__expires_at__gt=now)
        ).filter(
            models.Q(profile__isnull=True) | models.Q(profile__is_active=True)
        )

    def get_effective_permissions_queryset(self):
        if self.is_superuser:
            return Permission.objects.all()

        role_permissions = Permission.objects.filter(
            roles__user_role_assignments__user=self,
            roles__user_role_assignments__is_active=True,
            roles__user_role_assignments__role__is_active=True,
        ).filter(
            models.Q(profile__isnull=True) | models.Q(profile__is_active=True)
        )
        direct_permissions = self.get_active_direct_permissions()
        legacy_role_permissions = Permission.objects.filter(
            roles__users=self
        ).filter(models.Q(profile__isnull=True) | models.Q(profile__is_active=True)) if self.role_id else Permission.objects.none()
        user_permissions = self.user_permissions.filter(
            models.Q(profile__isnull=True) | models.Q(profile__is_active=True)
        )
        return (role_permissions | direct_permissions | legacy_role_permissions | user_permissions).distinct()

    def get_effective_permissions(self):
        return list(self.get_effective_permissions_queryset().values_list('codename', flat=True).order_by('codename'))

    def has_permission(self, codename: str):
        return self.is_superuser or codename in self.get_effective_permissions()

    def increment_authorization_version(self):
        self.authorization_version = models.F('authorization_version') + 1
        self.save(update_fields=['authorization_version'])
        self.refresh_from_db(fields=['authorization_version'])

    def sync_legacy_role(self):
        primary_role = self.primary_role
        if self.role_id != getattr(primary_role, 'id', None):
            self.role = primary_role
            self.save(update_fields=['role'])


class PermissionProfile(models.Model):
    permission = models.OneToOneField(Permission, on_delete=models.CASCADE, related_name='profile')
    module = models.CharField(max_length=50)
    resource = models.CharField(max_length=50)
    action = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=True)
    is_assignable = models.BooleanField(default=True)

    class Meta:
        db_table = 'permission_profiles'
        ordering = ['module', 'resource', 'action']
        indexes = [
            models.Index(fields=['module']),
            models.Index(fields=['resource']),
            models.Index(fields=['action']),
            models.Index(fields=['is_active']),
        ]


class UserRoleAssignment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='role_assignments')
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='user_role_assignments')
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='granted_role_assignments')
    assigned_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'user_role_assignments'
        unique_together = ('user', 'role')
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['role', 'is_active']),
        ]


class UserDirectPermission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='direct_permission_assignments')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name='direct_user_assignments')
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='granted_direct_permissions')
    assigned_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'user_direct_permissions'
        unique_together = ('user', 'permission')
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['permission', 'is_active']),
        ]


class AccessAuditLog(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='access_audit_entries')
    target_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='access_audit_targets')
    target_role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_entries')
    target_permission = models.ForeignKey(Permission, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_entries')
    action = models.CharField(max_length=100)
    before_state = models.JSONField(default=dict, blank=True)
    after_state = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'access_audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action']),
            models.Index(fields=['created_at']),
        ]
