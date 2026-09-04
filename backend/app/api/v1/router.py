from fastapi import APIRouter

from app.api.v1.endpoints import (
    agency,
    analytics,
    auth,
    billing,
    dashboard,
    etims,
    files,
    health,
    inspections,
    notifications,
    operations,
    organizations,
    portal,
    properties,
    renewals,
    signatures,
    tasks,
    team,
    tenants,
    vault,
    vendors,
)

api_router = APIRouter()

# Public / infrastructure
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(team.public_router, prefix="/invitations", tags=["team"])
api_router.include_router(billing.mpesa_router, prefix="/mpesa", tags=["mpesa"])
api_router.include_router(files.local_router, prefix="/files/local", tags=["files"])

# Organization & people
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(team.router, prefix="/team", tags=["team"])

# Portfolio
api_router.include_router(properties.router, prefix="/properties", tags=["properties"])
api_router.include_router(properties.units_router, prefix="/units", tags=["units"])
api_router.include_router(properties.dashboard_router, prefix="/dashboard", tags=["dashboard"])

# Tenancy
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(tenants.tenancies_router, prefix="/tenancies", tags=["tenancies"])
api_router.include_router(tenants.lease_templates_router, prefix="/lease-templates", tags=["lease-templates"])

# Money
api_router.include_router(billing.invoices_router, prefix="/invoices", tags=["invoices"])
api_router.include_router(billing.payments_router, prefix="/payments", tags=["payments"])
api_router.include_router(billing.arrears_router, prefix="/arrears", tags=["arrears"])

# Field operations
api_router.include_router(operations.meters_router, prefix="/meter-readings", tags=["meter-readings"])
api_router.include_router(operations.maintenance_router, prefix="/maintenance", tags=["maintenance"])
api_router.include_router(operations.notices_router, prefix="/vacate-notices", tags=["vacate-notices"])
api_router.include_router(operations.caretaker_router, prefix="/caretaker", tags=["caretaker"])

# Reporting & comms
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(dashboard.activity_router, prefix="/activity", tags=["activity"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(notifications.push_router, prefix="/push", tags=["notifications"])

# Files
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(vault.router, prefix="/vault", tags=["vault"])

# Tenant portal
api_router.include_router(portal.router, prefix="/portal", tags=["tenant-portal"])
api_router.include_router(portal.invite_router, prefix="/portal", tags=["tenant-portal"])

# Phase 2 — Agency mode
api_router.include_router(agency.router, prefix="/agency", tags=["agency"])

# Phase 2 — Inspections
api_router.include_router(inspections.router, prefix="/inspections", tags=["inspections"])

# Phase 2 — Digital signatures
api_router.include_router(signatures.router, prefix="/signatures", tags=["signatures"])
api_router.include_router(signatures.public_router, prefix="/sign", tags=["signatures"])

# Lease renewals (Phase 2)
api_router.include_router(renewals.router, prefix="/renewals", tags=["renewals"])
api_router.include_router(renewals.public_router, prefix="/renew", tags=["renewals"])

# Phase 2 — Analytics
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(etims.router, prefix="/etims", tags=["etims"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])

# Phase 3 — maintenance and vendors
api_router.include_router(vendors.router, prefix="/vendors", tags=["vendors"])
