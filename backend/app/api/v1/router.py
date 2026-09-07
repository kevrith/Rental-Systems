from fastapi import APIRouter

from app.api.v1.endpoints import (
    agency,
    analytics,
    applications,
    approvals,
    auth,
    billing,
    bulk,
    customer_success,
    dashboard,
    developer,
    etims,
    external,
    facilities,
    files,
    health,
    inspections,
    integrations,
    internal,
    notifications,
    operations,
    organizations,
    portal,
    privacy,
    properties,
    renewals,
    rentals,
    reporting,
    saved_views,
    search,
    security,
    service_charges,
    signatures,
    tasks,
    team,
    tenants,
    vacancies,
    vault,
    vendors,
    webhooks,
)

api_router = APIRouter()

# Public / infrastructure
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(team.public_router, prefix="/invitations", tags=["team"])
api_router.include_router(billing.mpesa_router, prefix="/mpesa", tags=["mpesa"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
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
api_router.include_router(operations.visitor_logs_router, prefix="/visitor-logs", tags=["visitor-logs"])

# Reporting & comms
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(dashboard.activity_router, prefix="/activity", tags=["activity"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(notifications.push_router, prefix="/push", tags=["notifications"])
api_router.include_router(notifications.templates_router, prefix="/message-templates", tags=["notifications"])

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

# Phase 3 — tenant screening. The apply/guarantee/reference routes are public:
# an applicant, a guarantor and a previous landlord all reach them by link.
api_router.include_router(applications.router, prefix="/applications", tags=["applications"])
api_router.include_router(applications.apply_router, prefix="/apply", tags=["applications"])
api_router.include_router(applications.public_router, tags=["applications"])

# Phase 3 — commercial service charges and bulk operations
api_router.include_router(service_charges.router, prefix="/service-charges", tags=["service-charges"])
api_router.include_router(bulk.router, prefix="/bulk", tags=["bulk-operations"])

# Phase 3 — vacancy marketing, the lead pipeline and data export.
# `/listings/{slug}` is public: the whole point of a listing is that it is shared.
api_router.include_router(vacancies.router, prefix="/vacancies", tags=["vacancies"])
api_router.include_router(vacancies.public_router, prefix="/listings", tags=["vacancies"])

# Phase 3 — facilities: compliance, parking, amenities and the building's own bills
api_router.include_router(facilities.compliance_router, prefix="/compliance", tags=["compliance"])
api_router.include_router(facilities.parking_router, prefix="/parking", tags=["parking"])
api_router.include_router(facilities.amenities_router, prefix="/amenities", tags=["amenities"])
api_router.include_router(facilities.utilities_router, prefix="/utilities", tags=["utilities"])

# Phase 3 — vehicle and equipment hire. A car and a generator are the same
# business, so they share one asset table and one agreement lifecycle.
api_router.include_router(rentals.assets_router, prefix="/assets", tags=["rentals"])
api_router.include_router(rentals.agreements_router, prefix="/rental-agreements", tags=["rentals"])

# Phase 4 — developer platform: API keys and webhooks, managed by a logged-in
# user, and the public API those credentials unlock.
api_router.include_router(developer.router, prefix="/developer/api-keys", tags=["developer"])
api_router.include_router(developer.webhooks_router, prefix="/developer/webhooks", tags=["developer"])
api_router.include_router(external.router, prefix="/external", tags=["external-api"])

# Phase 4 — onboarding, help, referrals, NPS, milestones, feature board and
# changelog (Sprint 20), plus the cross-organization view for RentFlow's own
# customer-success team.
api_router.include_router(customer_success.router, prefix="/customer-success", tags=["customer-success"])
api_router.include_router(internal.router, prefix="/internal", tags=["internal"])

# Sprint 21 — the custom report builder and the automatic monthly summary.
api_router.include_router(reporting.router, prefix="/reports", tags=["reports"])

# Sprint 22 — fraud alert triage and the security audit log export.
api_router.include_router(security.router, prefix="/security", tags=["security"])

# Sprint 23 — property portal sync and accounting software sync.
# `portal_webhook_router` and `oauth_callback_router` each carry no RentFlow
# session, so they get their own top-level prefixes rather than sharing
# `/integrations` — the same reason `/mpesa`, `/sign` and `/listings` are
# separate from their authenticated counterparts.
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
api_router.include_router(
    integrations.portal_webhook_router, prefix="/portal-webhooks", tags=["integrations"]
)
api_router.include_router(integrations.oauth_callback_router, prefix="/oauth", tags=["integrations"])

# Sprint 25 — security, privacy & compliance closeout.
api_router.include_router(privacy.router, prefix="/privacy", tags=["privacy"])

# Sprint 26A — cross-entity search, for the command palette.
api_router.include_router(search.router, prefix="/search", tags=["search"])

# Sprint 26A — saved views: named, reusable filter sets for a list screen.
api_router.include_router(saved_views.router, prefix="/saved-views", tags=["saved-views"])

# Sprint 26A — configurable approval chains.
api_router.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
