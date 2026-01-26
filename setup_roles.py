"""
Script to create initial roles and permissions for the Pharmacy Management System.
Run this after migrations to set up default roles.

Usage:
    python manage.py shell < setup_roles.py
    
Or in Django shell:
    exec(open('setup_roles.py').read())
"""

from django.contrib.auth.models import Permission
from users.models import Role, User

def create_role_with_permissions(role_name, permission_codenames):
    """Helper function to create a role and assign permissions"""
    role, created = Role.objects.get_or_create(name=role_name)
    permissions = Permission.objects.filter(codename__in=permission_codenames)
    role.permissions.set(permissions)
    status = "Created" if created else "Updated"
    print(f"{status} role '{role_name}' with {permissions.count()} permissions")
    return role

# =============================================================================
# Admin Role - Full Access
# =============================================================================
print("\n📋 Creating Admin role...")
# Admin role is typically granted to is_staff users, but we can create it for clarity
admin_permissions = list(Permission.objects.all().values_list('codename', flat=True))
admin_role = create_role_with_permissions('Admin', admin_permissions)

# =============================================================================
# Owner Role - View-only access to all modules
# =============================================================================
print("\n📋 Creating Owner role...")
owner_permissions = [
    # View all modules
    'view_user', 'view_role', 'view_permission',
    'view_category', 'view_medicine', 'view_stocktransaction',
    'view_supplier', 'view_purchase', 'view_purchaseitem',
    'view_customer', 'view_sale', 'view_saleitem', 'view_payment',
]
owner_role = create_role_with_permissions('Owner', owner_permissions)

# =============================================================================
# Pharmacist/Cashier Role - Sales focused
# =============================================================================
print("\n📋 Creating Pharmacist role...")
pharmacist_permissions = [
    # Medicine management
    'view_medicine', 'view_category',
    
    # Stock viewing
    'view_stocktransaction',
    
    # Sales operations
    'view_customer', 'add_customer', 'change_customer',
    'view_sale', 'add_sale', 'change_sale',
    'view_saleitem', 'add_saleitem',
    'view_payment', 'add_payment', 'change_payment',
]
pharmacist_role = create_role_with_permissions('Pharmacist', pharmacist_permissions)

# =============================================================================
# Inventory Manager Role - Inventory focused
# =============================================================================
print("\n📋 Creating Inventory Manager role...")
inventory_permissions = [
    # Categories
    'view_category', 'add_category', 'change_category', 'delete_category',
    
    # Medicines
    'view_medicine', 'add_medicine', 'change_medicine', 'delete_medicine',
    
    # Stock management
    'view_stocktransaction', 'add_stocktransaction', 'change_stocktransaction',
    
    # Suppliers and purchases (view only)
    'view_supplier', 'view_purchase', 'view_purchaseitem',
]
inventory_role = create_role_with_permissions('Inventory Manager', inventory_permissions)

# =============================================================================
# Purchase Manager Role - Supplier and purchase management
# =============================================================================
print("\n📋 Creating Purchase Manager role...")
purchase_permissions = [
    # View medicines and categories
    'view_category', 'view_medicine',
    
    # Supplier management
    'view_supplier', 'add_supplier', 'change_supplier', 'delete_supplier',
    
    # Purchase management
    'view_purchase', 'add_purchase', 'change_purchase', 'delete_purchase',
    'view_purchaseitem', 'add_purchaseitem', 'change_purchaseitem', 'delete_purchaseitem',
    
    # Stock transactions (add only, for receiving goods)
    'view_stocktransaction', 'add_stocktransaction',
]
purchase_role = create_role_with_permissions('Purchase Manager', purchase_permissions)

# =============================================================================
# Sales Manager Role - Sales and customer management
# =============================================================================
print("\n📋 Creating Sales Manager role...")
sales_permissions = [
    # View medicines and stock
    'view_category', 'view_medicine', 'view_stocktransaction',
    
    # Customer management
    'view_customer', 'add_customer', 'change_customer', 'delete_customer',
    
    # Sales management
    'view_sale', 'add_sale', 'change_sale', 'delete_sale',
    'view_saleitem', 'add_saleitem', 'change_saleitem', 'delete_saleitem',
    
    # Payment management
    'view_payment', 'add_payment', 'change_payment', 'delete_payment',
]
sales_role = create_role_with_permissions('Sales Manager', sales_permissions)

print("\n✅ All roles created successfully!")
print("\n📊 Summary:")
print(f"  - Admin: {admin_role.permissions.count()} permissions")
print(f"  - Owner: {owner_role.permissions.count()} permissions")
print(f"  - Pharmacist: {pharmacist_role.permissions.count()} permissions")
print(f"  - Inventory Manager: {inventory_role.permissions.count()} permissions")
print(f"  - Purchase Manager: {purchase_role.permissions.count()} permissions")
print(f"  - Sales Manager: {sales_role.permissions.count()} permissions")

print("\n💡 Next steps:")
print("  1. Assign roles to users in the admin dashboard")
print("  2. Or use: User.objects.filter(email='user@example.com').update(role=pharmacist_role)")
print("  3. Log in with different users to test permissions")
