"""Role-based access control.

Every protected endpoint declares the `Permission` it needs; `require(...)` in
`app.api.deps` resolves the caller's role against `ROLE_PERMISSIONS` below. Roles
are coarse and fixed — a role gets a whole permission or it doesn't — which keeps
the matrix auditable in one place instead of scattered across route handlers.
"""

import enum

from app.models.user import UserRole


class Permission(str, enum.Enum):
    # Organization & users
    ORG_MANAGE = "org:manage"
    USER_INVITE = "user:invite"
    USER_MANAGE = "user:manage"
    USER_VIEW = "user:view"

    # Portfolio
    PROPERTY_VIEW = "property:view"
    PROPERTY_MANAGE = "property:manage"
    UNIT_VIEW = "unit:view"
    UNIT_MANAGE = "unit:manage"
    UNIT_STATUS_UPDATE = "unit:status_update"

    # Tenancy
    TENANT_VIEW = "tenant:view"
    TENANT_MANAGE = "tenant:manage"
    TENANCY_VIEW = "tenancy:view"
    TENANCY_MANAGE = "tenancy:manage"
    LEASE_TEMPLATE_MANAGE = "lease_template:manage"
    APPLICATION_VIEW = "application:view"
    APPLICATION_MANAGE = "application:manage"
    # Approving or rejecting commits the landlord to a person, so it is separated
    # from the day-to-day management of the application file.
    APPLICATION_DECIDE = "application:decide"

    # Money
    PAYMENT_VIEW = "payment:view"
    PAYMENT_RECORD = "payment:record"
    INVOICE_VIEW = "invoice:view"
    INVOICE_MANAGE = "invoice:manage"
    ARREARS_VIEW = "arrears:view"

    # Operations
    METER_READING_VIEW = "meter_reading:view"
    METER_READING_RECORD = "meter_reading:record"
    MAINTENANCE_VIEW = "maintenance:view"
    MAINTENANCE_MANAGE = "maintenance:manage"
    MAINTENANCE_CREATE = "maintenance:create"
    MAINTENANCE_APPROVE = "maintenance:approve"
    VENDOR_VIEW = "vendor:view"
    VENDOR_MANAGE = "vendor:manage"

    # Reporting
    DASHBOARD_VIEW = "dashboard:view"
    FINANCIALS_VIEW = "financials:view"
    AUDIT_VIEW = "audit:view"

    # Files
    FILE_UPLOAD = "file:upload"
    FILE_VIEW = "file:view"

    # Developer platform (Sprint 19)
    API_KEY_MANAGE = "api_key:manage"
    WEBHOOK_MANAGE = "webhook:manage"


_FULL_OPERATOR_PERMISSIONS: set[Permission] = {
    Permission.USER_INVITE,
    Permission.USER_MANAGE,
    Permission.USER_VIEW,
    Permission.PROPERTY_VIEW,
    Permission.PROPERTY_MANAGE,
    Permission.UNIT_VIEW,
    Permission.UNIT_MANAGE,
    Permission.UNIT_STATUS_UPDATE,
    Permission.TENANT_VIEW,
    Permission.TENANT_MANAGE,
    Permission.TENANCY_VIEW,
    Permission.TENANCY_MANAGE,
    Permission.LEASE_TEMPLATE_MANAGE,
    Permission.APPLICATION_VIEW,
    Permission.APPLICATION_MANAGE,
    Permission.APPLICATION_DECIDE,
    Permission.PAYMENT_VIEW,
    Permission.PAYMENT_RECORD,
    Permission.INVOICE_VIEW,
    Permission.INVOICE_MANAGE,
    Permission.ARREARS_VIEW,
    Permission.METER_READING_VIEW,
    Permission.METER_READING_RECORD,
    Permission.MAINTENANCE_VIEW,
    Permission.MAINTENANCE_MANAGE,
    Permission.MAINTENANCE_CREATE,
    Permission.MAINTENANCE_APPROVE,
    Permission.VENDOR_VIEW,
    Permission.VENDOR_MANAGE,
    Permission.DASHBOARD_VIEW,
    Permission.FINANCIALS_VIEW,
    Permission.AUDIT_VIEW,
    Permission.FILE_UPLOAD,
    Permission.FILE_VIEW,
    Permission.API_KEY_MANAGE,
    Permission.WEBHOOK_MANAGE,
}

ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.SYSTEM_ADMIN: set(Permission),
    UserRole.OWNER: _FULL_OPERATOR_PERMISSIONS | {Permission.ORG_MANAGE},
    UserRole.AGENCY_ADMIN: _FULL_OPERATOR_PERMISSIONS | {Permission.ORG_MANAGE},
    # A property manager runs day-to-day operations but cannot reconfigure the org.
    UserRole.PROPERTY_MANAGER: _FULL_OPERATOR_PERMISSIONS,
    # A caretaker works on their assigned properties only (enforced separately by
    # property scoping) and records rather than configures.
    UserRole.CARETAKER: {
        Permission.PROPERTY_VIEW,
        Permission.UNIT_VIEW,
        Permission.UNIT_STATUS_UPDATE,
        Permission.TENANT_VIEW,
        Permission.TENANT_MANAGE,
        Permission.TENANCY_VIEW,
        Permission.TENANCY_MANAGE,
        Permission.APPLICATION_VIEW,
        Permission.PAYMENT_VIEW,
        Permission.PAYMENT_RECORD,
        Permission.INVOICE_VIEW,
        Permission.METER_READING_VIEW,
        Permission.METER_READING_RECORD,
        Permission.MAINTENANCE_VIEW,
        Permission.MAINTENANCE_CREATE,
        Permission.VENDOR_VIEW,
        Permission.FILE_UPLOAD,
        Permission.FILE_VIEW,
    },
    UserRole.ACCOUNTANT: {
        Permission.PROPERTY_VIEW,
        Permission.UNIT_VIEW,
        Permission.TENANT_VIEW,
        Permission.TENANCY_VIEW,
        Permission.PAYMENT_VIEW,
        Permission.PAYMENT_RECORD,
        Permission.INVOICE_VIEW,
        Permission.INVOICE_MANAGE,
        Permission.ARREARS_VIEW,
        Permission.DASHBOARD_VIEW,
        Permission.FINANCIALS_VIEW,
        Permission.FILE_VIEW,
    },
    # Read-only transparency portal for owners inside an agency account (Phase 2).
    UserRole.OWNER_PORTAL_USER: {
        Permission.PROPERTY_VIEW,
        Permission.UNIT_VIEW,
        Permission.TENANCY_VIEW,
        # An owner sees what is being spent on their buildings, but approves nothing.
        Permission.MAINTENANCE_VIEW,
        Permission.PAYMENT_VIEW,
        Permission.INVOICE_VIEW,
        Permission.ARREARS_VIEW,
        Permission.DASHBOARD_VIEW,
        Permission.FINANCIALS_VIEW,
        Permission.FILE_VIEW,
    },
    # Tenants never touch the operator API — the tenant portal has its own routes.
    UserRole.TENANT: {
        Permission.MAINTENANCE_CREATE,
        Permission.FILE_UPLOAD,
        Permission.FILE_VIEW,
    },
}

# Roles that may hold a caretaker-style property assignment.
PROPERTY_SCOPED_ROLES = {UserRole.CARETAKER}

# Writes are blocked for these roles regardless of permission matrix (read-only accounts).
READ_ONLY_ROLES = {UserRole.OWNER_PORTAL_USER}


def role_has(role: UserRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def permissions_for(role: UserRole) -> list[str]:
    return sorted(p.value for p in ROLE_PERMISSIONS.get(role, set()))
