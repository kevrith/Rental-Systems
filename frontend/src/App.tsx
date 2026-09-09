import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { AcceptInvitePage, PortalSetupPage } from '@/features/auth/AcceptInvitePage'
import { LoginPage } from '@/features/auth/LoginPage'
import { ForgotPasswordPage, ResetPasswordPage, VerifyEmailPage } from '@/features/auth/PasswordPages'
import { RegisterPage } from '@/features/auth/RegisterPage'
import { LandingPage } from '@/features/marketing/LandingPage'
import { PortalLoginPage } from '@/features/portal/PortalLoginPage'
import { PortalShell } from '@/features/portal/PortalShell'
import { HomeRedirect } from '@/pages/HomeRedirect'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { PageLoader } from '@/components/ui'

/*
 * Every screen past the front door is code-split (US-059).
 *
 * The whole app used to ship as one 1.26MB bundle, so a caretaker on 3G
 * downloaded the analytics charts and the lease editor before they could see
 * the login form. Each route below is fetched the first time it is opened and
 * cached by the service worker after that; the auth pages, the shells and the
 * dashboard stay eager because they are the first paint.
 */
const AgencyDashboardPage = lazy(() =>
  import('@/features/agency/AgencyDashboardPage').then((m) => ({ default: m.AgencyDashboardPage })),
)
const ApplicationsPage = lazy(() =>
  import('@/features/applications/ApplicationsPage').then((m) => ({ default: m.ApplicationsPage })),
)
const ApplicationDetailPage = lazy(() =>
  import('@/features/applications/ApplicationDetailPage').then((m) => ({
    default: m.ApplicationDetailPage,
  })),
)
const PublicApplyPage = lazy(() =>
  import('@/features/applications/PublicApplyPage').then((m) => ({ default: m.PublicApplyPage })),
)
const GuaranteeResponsePage = lazy(() =>
  import('@/features/applications/PublicResponsePages').then((m) => ({
    default: m.GuaranteeResponsePage,
  })),
)
const HelpCenterPage = lazy(() =>
  import('@/features/help/HelpCenterPage').then((m) => ({ default: m.HelpCenterPage })),
)
const HelpArticlePage = lazy(() =>
  import('@/features/help/HelpCenterPage').then((m) => ({ default: m.HelpArticlePage })),
)
const PrivacyPolicyPage = lazy(() =>
  import('@/features/legal/LegalPages').then((m) => ({ default: m.PrivacyPolicyPage })),
)
const TermsOfServicePage = lazy(() =>
  import('@/features/legal/LegalPages').then((m) => ({ default: m.TermsOfServicePage })),
)
const CookiePolicyPage = lazy(() =>
  import('@/features/legal/LegalPages').then((m) => ({ default: m.CookiePolicyPage })),
)
const ReferenceResponsePage = lazy(() =>
  import('@/features/applications/PublicResponsePages').then((m) => ({
    default: m.ReferenceResponsePage,
  })),
)
const FleetPage = lazy(() => import('@/features/rentals/FleetPage').then((m) => ({ default: m.FleetPage })))
const AssetDetailPage = lazy(() =>
  import('@/features/rentals/AssetDetailPage').then((m) => ({ default: m.AssetDetailPage })),
)
const CompliancePage = lazy(() =>
  import('@/features/facilities/CompliancePage').then((m) => ({ default: m.CompliancePage })),
)
const CustomerHealthPage = lazy(() =>
  import('@/features/success/CustomerHealthPage').then((m) => ({ default: m.CustomerHealthPage })),
)
const ReferralPage = lazy(() =>
  import('@/features/success/ReferralPage').then((m) => ({ default: m.ReferralPage })),
)
const FeatureBoardPage = lazy(() =>
  import('@/features/success/FeatureBoardPage').then((m) => ({ default: m.FeatureBoardPage })),
)
const InternalContentPage = lazy(() =>
  import('@/features/success/InternalContentPage').then((m) => ({ default: m.InternalContentPage })),
)
const FacilitiesPage = lazy(() =>
  import('@/features/facilities/FacilitiesPage').then((m) => ({ default: m.FacilitiesPage })),
)
const VacancyDeskPage = lazy(() =>
  import('@/features/vacancies/VacancyDeskPage').then((m) => ({ default: m.VacancyDeskPage })),
)
const PublicListingPage = lazy(() =>
  import('@/features/vacancies/PublicListingPage').then((m) => ({ default: m.PublicListingPage })),
)
const DataExportPage = lazy(() =>
  import('@/features/vacancies/DataExportPage').then((m) => ({ default: m.DataExportPage })),
)
const BulkOperationsPage = lazy(() =>
  import('@/features/bulk/BulkOperationsPage').then((m) => ({ default: m.BulkOperationsPage })),
)
const TenantImportPage = lazy(() =>
  import('@/features/bulk/TenantImportPage').then((m) => ({ default: m.TenantImportPage })),
)
const ServiceChargePage = lazy(() =>
  import('@/features/properties/ServiceChargePage').then((m) => ({ default: m.ServiceChargePage })),
)
const AnalyticsPage = lazy(() =>
  import('@/features/analytics/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })),
)
const ReportsListPage = lazy(() =>
  import('@/features/reports/ReportsListPage').then((m) => ({ default: m.ReportsListPage })),
)
const ReportBuilderPage = lazy(() =>
  import('@/features/reports/ReportBuilderPage').then((m) => ({ default: m.ReportBuilderPage })),
)
const ArrearsPage = lazy(() =>
  import('@/features/arrears/ArrearsPage').then((m) => ({ default: m.ArrearsPage })),
)
const FraudAlertsPage = lazy(() =>
  import('@/features/security/FraudAlertsPage').then((m) => ({ default: m.FraudAlertsPage })),
)
const ApprovalsPage = lazy(() =>
  import('@/features/approvals/ApprovalsPage').then((m) => ({ default: m.ApprovalsPage })),
)
const BulkUnitsPage = lazy(() =>
  import('@/features/units/UnitFormPage').then((m) => ({ default: m.BulkUnitsPage })),
)
const CaretakerHomePage = lazy(() =>
  import('@/features/caretaker/CaretakerHomePage').then((m) => ({ default: m.CaretakerHomePage })),
)
const CaretakerPerformancePage = lazy(() =>
  import('@/features/automation/CaretakerPerformancePage').then((m) => ({
    default: m.CaretakerPerformancePage,
  })),
)
const DashboardPage = lazy(() =>
  import('@/features/dashboard/DashboardPage').then((m) => ({ default: m.DashboardPage })),
)
const DisbursementsPage = lazy(() =>
  import('@/features/agency/DisbursementsPage').then((m) => ({ default: m.DisbursementsPage })),
)
const DeveloperPage = lazy(() =>
  import('@/features/developer/DeveloperPage').then((m) => ({ default: m.DeveloperPage })),
)
const MpesaSettingsPage = lazy(() =>
  import('@/features/settings/MpesaSettingsPage').then((m) => ({ default: m.MpesaSettingsPage })),
)
const BillingSettingsPage = lazy(() =>
  import('@/features/settings/BillingSettingsPage').then((m) => ({ default: m.BillingSettingsPage })),
)
const EtimsSettingsPage = lazy(() =>
  import('@/features/analytics/EtimsSettingsPage').then((m) => ({ default: m.EtimsSettingsPage })),
)
const InspectionCapturePage = lazy(() =>
  import('@/features/inspections/InspectionCapturePage').then((m) => ({ default: m.InspectionCapturePage })),
)
const InspectionDetailPage = lazy(() =>
  import('@/features/inspections/InspectionDetailPage').then((m) => ({ default: m.InspectionDetailPage })),
)
const InspectionsPage = lazy(() =>
  import('@/features/inspections/InspectionsPage').then((m) => ({ default: m.InspectionsPage })),
)
const InvoiceDetailPage = lazy(() =>
  import('@/features/invoices/InvoicesPage').then((m) => ({ default: m.InvoiceDetailPage })),
)
const InvoicesPage = lazy(() =>
  import('@/features/invoices/InvoicesPage').then((m) => ({ default: m.InvoicesPage })),
)
const LeaseTemplatesPage = lazy(() =>
  import('@/features/lease-templates/LeaseTemplatesPage').then((m) => ({ default: m.LeaseTemplatesPage })),
)
const MaintenanceAnalyticsPage = lazy(() =>
  import('@/features/maintenance/MaintenanceAnalyticsPage').then((m) => ({
    default: m.MaintenanceAnalyticsPage,
  })),
)
const MaintenanceDetailPage = lazy(() =>
  import('@/features/maintenance/MaintenanceDetailPage').then((m) => ({
    default: m.MaintenanceDetailPage,
  })),
)
const MaintenanceFormPage = lazy(() =>
  import('@/features/maintenance/MaintenancePage').then((m) => ({ default: m.MaintenanceFormPage })),
)
const MaintenancePage = lazy(() =>
  import('@/features/maintenance/MaintenancePage').then((m) => ({ default: m.MaintenancePage })),
)
const VendorsPage = lazy(() =>
  import('@/features/vendors/VendorsPage').then((m) => ({ default: m.VendorsPage })),
)
const VendorDetailPage = lazy(() =>
  import('@/features/vendors/VendorDetailPage').then((m) => ({ default: m.VendorDetailPage })),
)
const MeterReadingsPage = lazy(() =>
  import('@/features/meters/MeterReadingsPage').then((m) => ({ default: m.MeterReadingsPage })),
)
const VisitorLogPage = lazy(() =>
  import('@/features/visitors/VisitorLogPage').then((m) => ({ default: m.VisitorLogPage })),
)
const LogVisitorPage = lazy(() =>
  import('@/features/visitors/VisitorLogPage').then((m) => ({ default: m.LogVisitorPage })),
)
const NotificationSettings = lazy(() =>
  import('@/features/settings/SettingsPage').then((m) => ({ default: m.NotificationSettings })),
)
const NotificationsPage = lazy(() =>
  import('@/features/notifications/NotificationsPage').then((m) => ({ default: m.NotificationsPage })),
)
const OrganizationSettings = lazy(() =>
  import('@/features/settings/SettingsPage').then((m) => ({ default: m.OrganizationSettings })),
)
const OwnerPortalPage = lazy(() =>
  import('@/features/agency/OwnerPortalPage').then((m) => ({ default: m.OwnerPortalPage })),
)
const OwnerProfileDetailPage = lazy(() =>
  import('@/features/agency/OwnerProfileDetailPage').then((m) => ({ default: m.OwnerProfileDetailPage })),
)
const OwnerProfileFormPage = lazy(() =>
  import('@/features/agency/OwnerProfileFormPage').then((m) => ({ default: m.OwnerProfileFormPage })),
)
const OwnerProfilesPage = lazy(() =>
  import('@/features/agency/OwnerProfilesPage').then((m) => ({ default: m.OwnerProfilesPage })),
)
const PaymentDetailPage = lazy(() =>
  import('@/features/payments/PaymentDetailPage').then((m) => ({ default: m.PaymentDetailPage })),
)
const PaymentsPage = lazy(() =>
  import('@/features/payments/PaymentsPage').then((m) => ({ default: m.PaymentsPage })),
)
const PortalDocumentsPage = lazy(() =>
  import('@/features/portal/PortalPages').then((m) => ({ default: m.PortalDocumentsPage })),
)
const PortalHomePage = lazy(() =>
  import('@/features/portal/PortalHomePage').then((m) => ({ default: m.PortalHomePage })),
)
const PortalMaintenancePage = lazy(() =>
  import('@/features/portal/PortalPages').then((m) => ({ default: m.PortalMaintenancePage })),
)
const PortalPaymentsPage = lazy(() =>
  import('@/features/portal/PortalPages').then((m) => ({ default: m.PortalPaymentsPage })),
)
const PortalPrivacyPage = lazy(() =>
  import('@/features/portal/PortalPages').then((m) => ({ default: m.PortalPrivacyPage })),
)
const ProfileSettings = lazy(() =>
  import('@/features/settings/SettingsPage').then((m) => ({ default: m.ProfileSettings })),
)
const PropertiesPage = lazy(() =>
  import('@/features/properties/PropertiesPage').then((m) => ({ default: m.PropertiesPage })),
)
const PropertyDetailPage = lazy(() =>
  import('@/features/properties/PropertyDetailPage').then((m) => ({ default: m.PropertyDetailPage })),
)
const PropertyFormPage = lazy(() =>
  import('@/features/properties/PropertyFormPage').then((m) => ({ default: m.PropertyFormPage })),
)
const PropertyVaultPage = lazy(() =>
  import('@/features/vault/VaultPages').then((m) => ({ default: m.PropertyVaultPage })),
)
const RecordMeterReadingPage = lazy(() =>
  import('@/features/meters/MeterReadingsPage').then((m) => ({ default: m.RecordMeterReadingPage })),
)
const RecordPaymentPage = lazy(() =>
  import('@/features/payments/RecordPaymentPage').then((m) => ({ default: m.RecordPaymentPage })),
)
const BankReconciliationPage = lazy(() =>
  import('@/features/payments/BankReconciliationPage').then((m) => ({
    default: m.BankReconciliationPage,
  })),
)
const BankStatementDetailPage = lazy(() =>
  import('@/features/payments/BankReconciliationPage').then((m) => ({
    default: m.BankStatementDetailPage,
  })),
)
const RenewalPage = lazy(() =>
  import('@/features/automation/RenewalPage').then((m) => ({ default: m.RenewalPage })),
)
const MessageTemplatesPage = lazy(() =>
  import('@/features/settings/MessageTemplatesPage').then((m) => ({
    default: m.MessageTemplatesPage,
  })),
)
const PortalsSettingsPage = lazy(() =>
  import('@/features/settings/PortalsSettingsPage').then((m) => ({ default: m.PortalsSettingsPage })),
)
const AccountingSettingsPage = lazy(() =>
  import('@/features/settings/AccountingSettingsPage').then((m) => ({
    default: m.AccountingSettingsPage,
  })),
)
const SecuritySettings = lazy(() =>
  import('@/features/settings/SettingsPage').then((m) => ({ default: m.SecuritySettings })),
)
const SessionsSettings = lazy(() =>
  import('@/features/settings/SettingsPage').then((m) => ({ default: m.SessionsSettings })),
)
const SettingsLayout = lazy(() =>
  import('@/features/settings/SettingsPage').then((m) => ({ default: m.SettingsLayout })),
)
const TaskMonitorPage = lazy(() =>
  import('@/features/automation/TaskMonitorPage').then((m) => ({ default: m.TaskMonitorPage })),
)
const TeamPage = lazy(() => import('@/features/team/TeamPage').then((m) => ({ default: m.TeamPage })))
const TenanciesPage = lazy(() =>
  import('@/features/tenancies/TenanciesPage').then((m) => ({ default: m.TenanciesPage })),
)
const TenancyDetailPage = lazy(() =>
  import('@/features/tenancies/TenancyDetailPage').then((m) => ({ default: m.TenancyDetailPage })),
)
const TenancyWizardPage = lazy(() =>
  import('@/features/tenancies/TenancyWizardPage').then((m) => ({ default: m.TenancyWizardPage })),
)
const TenantDetailPage = lazy(() =>
  import('@/features/tenants/TenantDetailPage').then((m) => ({ default: m.TenantDetailPage })),
)
const TenantFormPage = lazy(() =>
  import('@/features/tenants/TenantFormPage').then((m) => ({ default: m.TenantFormPage })),
)
const TenantVaultPage = lazy(() =>
  import('@/features/vault/VaultPages').then((m) => ({ default: m.TenantVaultPage })),
)
const TenantsPage = lazy(() =>
  import('@/features/tenants/TenantsPage').then((m) => ({ default: m.TenantsPage })),
)
const UnitDetailPage = lazy(() =>
  import('@/features/units/UnitDetailPage').then((m) => ({ default: m.UnitDetailPage })),
)
const UnitFormPage = lazy(() =>
  import('@/features/units/UnitFormPage').then((m) => ({ default: m.UnitFormPage })),
)
const UnitsPage = lazy(() => import('@/features/units/UnitsPage').then((m) => ({ default: m.UnitsPage })))

const STAFF_ROLES = [
  'owner',
  'agency_admin',
  'property_manager',
  'caretaker',
  'accountant',
  'owner_portal_user',
  'system_admin',
]

/** Shown while a route's chunk is fetched. Deliberately the same loader the
 *  screens themselves use, so a slow network looks like a slow query. */
function RouteFallback() {
  return <PageLoader />
}

function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        {/* Public */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/accept-invite" element={<AcceptInvitePage />} />
        <Route path="/portal/setup" element={<PortalSetupPage />} />
        {/* Public: a tenant signing in by link has no session yet. */}
        <Route path="/portal/login" element={<PortalLoginPage />} />
        {/* The renewal link is the tenant's whole authentication — no account. */}
        <Route path="/renew/:token" element={<RenewalPage />} />
        {/* Screening reaches three people who have no login: the applicant, their
            guarantor, and their previous landlord. */}
        <Route path="/apply/:unitId" element={<PublicApplyPage />} />
        {/* A vacancy listing is meant to be pasted into WhatsApp groups. */}
        <Route path="/listing/:slug" element={<PublicListingPage />} />
        <Route path="/guarantee/:token" element={<GuaranteeResponsePage />} />
        <Route path="/reference/:token" element={<ReferenceResponsePage />} />
        {/* The help centre is public on purpose: it has to be readable before
            there is an account, and by anyone stuck on the sign-in screen. */}
        <Route path="/help" element={<HelpCenterPage />} />
        <Route path="/help/:slug" element={<HelpArticlePage />} />
        <Route path="/legal/privacy" element={<PrivacyPolicyPage />} />
        <Route path="/legal/terms" element={<TermsOfServicePage />} />
        <Route path="/legal/cookies" element={<CookiePolicyPage />} />

        {/* Tenant portal */}
        <Route element={<ProtectedRoute allowRoles={['tenant']} />}>
          <Route element={<PortalShell />}>
            <Route path="/portal" element={<PortalHomePage />} />
            <Route path="/portal/payments" element={<PortalPaymentsPage />} />
            <Route path="/portal/documents" element={<PortalDocumentsPage />} />
            <Route path="/portal/maintenance" element={<PortalMaintenancePage />} />
            <Route path="/portal/privacy" element={<PortalPrivacyPage />} />
          </Route>
        </Route>

        {/* Staff app */}
        <Route element={<ProtectedRoute allowRoles={STAFF_ROLES} />}>
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<HomeRedirect />} />
            <Route path="/overview" element={<DashboardPage />} />
            <Route path="/today" element={<CaretakerHomePage />} />

            <Route path="/properties" element={<PropertiesPage />} />
            <Route path="/properties/new" element={<PropertyFormPage />} />
            <Route path="/properties/:propertyId" element={<PropertyDetailPage />} />
            <Route path="/properties/:propertyId/edit" element={<PropertyFormPage />} />
            <Route path="/properties/:propertyId/documents" element={<PropertyVaultPage />} />

            <Route path="/units" element={<UnitsPage />} />
            <Route path="/units/new" element={<UnitFormPage />} />
            <Route path="/units/bulk" element={<BulkUnitsPage />} />
            <Route path="/units/:unitId" element={<UnitDetailPage />} />
            <Route path="/units/:unitId/edit" element={<UnitFormPage />} />

            <Route path="/tenants" element={<TenantsPage />} />
            <Route path="/tenants/new" element={<TenantFormPage />} />
            <Route path="/tenants/:tenantId" element={<TenantDetailPage />} />
            <Route path="/tenants/:tenantId/edit" element={<TenantFormPage />} />
            <Route path="/tenants/:tenantId/documents" element={<TenantVaultPage />} />

            <Route path="/tenancies" element={<TenanciesPage />} />
            <Route path="/tenancies/new" element={<TenancyWizardPage />} />
            <Route path="/tenancies/:tenancyId" element={<TenancyDetailPage />} />
            <Route path="/lease-templates" element={<LeaseTemplatesPage />} />

            <Route path="/payments" element={<PaymentsPage />} />
            <Route path="/payments/new" element={<RecordPaymentPage />} />
            <Route path="/payments/bank-statements" element={<BankReconciliationPage />} />
            <Route path="/payments/bank-statements/:uploadId" element={<BankStatementDetailPage />} />
            <Route path="/payments/:paymentId" element={<PaymentDetailPage />} />

            <Route path="/invoices" element={<InvoicesPage />} />
            <Route path="/invoices/:invoiceId" element={<InvoiceDetailPage />} />

            <Route path="/arrears" element={<ArrearsPage />} />
            <Route path="/security/fraud-alerts" element={<FraudAlertsPage />} />
            <Route path="/approvals" element={<ApprovalsPage />} />
            <Route path="/finances" element={<DashboardPage />} />
            <Route path="/analytics" element={<AnalyticsPage />} />

            <Route path="/reports" element={<ReportsListPage />} />
            <Route path="/reports/new" element={<ReportBuilderPage />} />
            <Route path="/reports/:id/edit" element={<ReportBuilderPage />} />

            <Route path="/maintenance" element={<MaintenancePage />} />
            <Route path="/maintenance/new" element={<MaintenanceFormPage />} />
            <Route path="/maintenance/analytics" element={<MaintenanceAnalyticsPage />} />
            <Route path="/maintenance/:requestId" element={<MaintenanceDetailPage />} />

            {/* Phase 3 — vehicle and equipment hire */}
            <Route path="/fleet" element={<FleetPage />} />
            <Route path="/fleet/:assetId" element={<AssetDetailPage />} />

            {/* Phase 3 — facilities */}
            <Route path="/compliance" element={<CompliancePage />} />
            <Route path="/properties/:propertyId/facilities" element={<FacilitiesPage />} />

            {/* Phase 3 — vacancy marketing and export */}
            <Route path="/vacancies" element={<VacancyDeskPage />} />
            <Route path="/settings/exports" element={<DataExportPage />} />

            {/* Phase 3 — service charges and bulk actions */}
            <Route path="/properties/:propertyId/service-charge" element={<ServiceChargePage />} />
            <Route path="/bulk" element={<BulkOperationsPage />} />
            <Route path="/bulk/import" element={<TenantImportPage />} />

            {/* Phase 3 — tenant screening */}
            <Route path="/applications" element={<ApplicationsPage />} />
            <Route path="/applications/:applicationId" element={<ApplicationDetailPage />} />

            {/* Phase 3 — vendor registry */}
            <Route path="/vendors" element={<VendorsPage />} />
            <Route path="/vendors/:vendorId" element={<VendorDetailPage />} />

            <Route path="/inspections" element={<InspectionsPage />} />
            <Route path="/inspections/new" element={<InspectionCapturePage />} />
            <Route path="/inspections/:inspectionId" element={<InspectionDetailPage />} />
            <Route path="/inspections/:inspectionId/capture" element={<InspectionCapturePage />} />

            <Route path="/meter-readings" element={<MeterReadingsPage />} />
            <Route path="/meter-readings/new" element={<RecordMeterReadingPage />} />
            <Route path="/visitor-log" element={<VisitorLogPage />} />
            <Route path="/visitor-log/new" element={<LogVisitorPage />} />

            {/* Agency mode (Phase 2) */}
            <Route path="/agency" element={<AgencyDashboardPage />} />
            <Route path="/agency/owners" element={<OwnerProfilesPage />} />
            <Route path="/agency/owners/new" element={<OwnerProfileFormPage />} />
            <Route path="/agency/owners/:ownerId" element={<OwnerProfileDetailPage />} />
            <Route path="/agency/owners/:ownerId/edit" element={<OwnerProfileFormPage />} />
            <Route path="/agency/disbursements" element={<DisbursementsPage />} />

            {/* Mode 3 — read-only owner portal */}
            <Route path="/owner-portal" element={<OwnerPortalPage />} />

            <Route path="/team" element={<TeamPage />} />
            <Route path="/team/performance" element={<CaretakerPerformancePage />} />
            <Route path="/automation" element={<TaskMonitorPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/developer" element={<DeveloperPage />} />

            {/* Sprint 20 — customer success */}
            <Route path="/referrals" element={<ReferralPage />} />
            <Route path="/feedback" element={<FeatureBoardPage />} />
            <Route element={<ProtectedRoute requirePlatformStaff />}>
              <Route path="/internal/health" element={<CustomerHealthPage />} />
              <Route path="/internal/content" element={<InternalContentPage />} />
            </Route>

            <Route path="/settings" element={<SettingsLayout />}>
              <Route index element={<Navigate to="/settings/profile" replace />} />
              <Route path="profile" element={<ProfileSettings />} />
              <Route path="security" element={<SecuritySettings />} />
              <Route path="sessions" element={<SessionsSettings />} />
              <Route path="notifications" element={<NotificationSettings />} />
              <Route path="organization" element={<OrganizationSettings />} />
              <Route path="mpesa" element={<MpesaSettingsPage />} />
              <Route path="billing" element={<BillingSettingsPage />} />
              <Route path="messages" element={<MessageTemplatesPage />} />
              <Route path="etims" element={<EtimsSettingsPage />} />
              <Route path="portals" element={<PortalsSettingsPage />} />
              <Route path="accounting" element={<AccountingSettingsPage />} />
            </Route>
          </Route>
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  )
}

export default App
