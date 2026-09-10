/** Thin typed wrappers over the API. No React, no caching — just calls. */
import { apiClient } from '@/lib/api-client'

import type {
  ActivityEntry,
  AgencyDashboard,
  ApiKey,
  ApiKeyCreated,
  ApiKeyUsage,
  ArrearsReport,
  AuditChainVerification,
  BreachRecord,
  BreachDashboard,
  OrganizationSuspensionState,
  CaretakerTaskList,
  Disbursement,
  DisbursementPreview,
  DisbursementStatement,
  CaretakerOpenJob,
  CaretakerScore,
  CaretakerScoreDetail,
  CashFlowPoint,
  DemandLetter,
  DocumentDelivery,
  EtimsCredentials,
  EtimsReport,
  ExpiringLeases,
  InspectionComparison,
  InspectionCompliance,
  InspectionDetail,
  InspectionDocuments,
  InspectionSummary,
  LeaseRenewal,
  LeaseTemplateStarter,
  BulkOperation,
  GuarantorInvite,
  ImportPreview,
  ImportResult,
  MaintenanceAnalytics,
  MaintenanceOverview,
  PublicUnitListing,
  ReferenceInvite,
  Amenity,
  AvailabilityRow,
  AmenityBooking,
  AmenityUsageRow,
  ComplianceDashboard,
  ComplianceItem,
  ConversionReport,
  FleetOverview,
  DataExportRow,
  InquiryRow,
  ParkingOverview,
  PublicListing,
  RentalAgreement,
  RentalAsset,
  ScreeningSummary,
  ServiceChargeExpense,
  ServiceChargeReconciliation,
  ServiceChargeScheme,
  SinkingFundEntry,
  TenantApplication,
  UtilityAccount,
  VacancyListingRow,
  VacancyReport,
  WaitingListEntry,
  ProposedTerms,
  RenewalOffer,
  PropertyPerformance,
  RevenuePoint,
  TaskOverview,
  TaskRun,
  PropertyVault,
  TenantVault,
  VaultCategories,
  VaultDocument,
  VaultUsage,
  FinancialDashboard,
  InvoiceDetail,
  Invitation,
  LeaseTemplate,
  MaintenanceRequest,
  CoTenant,
  DataRequest,
  MeterContext,
  MeterReading,
  NotificationPreference,
  NotificationRow,
  OwnerPortalSummary,
  OwnerProfile,
  OwnerSummary,
  PaymentDetail,
  PortalHome,
  MpesaSetupStatus,
  MpesaTestResult,
  PortalPaymentMethods,
  BillingInterval,
  PlanOption,
  Subscription,
  SubscriptionInvoice,
  PortfolioDashboard,
  Property,
  PropertySummary,
  StoredDocument,
  TeamMember,
  Vendor,
  VendorDetail,
  TenancyDetail,
  Tenant,
  TenantListItem,
  Unit,
  UnitDetail,
  VacateNotice,
  VisitorLog,
  WebhookDelivery,
  WebhookEndpoint,
  WebhookEndpointCreated,
  ChangelogEntry,
  FeatureRequest,
  HelpArticle,
  Milestone,
  NpsPending,
  OnboardingProgress,
  OrganizationHealthScorePoint,
  OrganizationHealthSummary,
  Referral,
  ReferralSummary,
  SupportRequest,
  MonthlyReport,
  RentReviewSuggestion,
  ReportDataset,
  ReportDatasetOption,
  ReportDefinition,
  ReportDefinitionInput,
  ReportFieldMeta,
  ReportPreviewRequest,
  ReportPreviewResult,
  VacancyRiskItem,
  LeaseAnalysis,
  LeaseSuggestion,
  FraudAlert,
  FraudAlertStatus,
  AccountingConnection,
  AccountingProvider,
  AccountingSyncReport,
  BankInstructions,
  BankStatementCommitResult,
  BankStatementCommitRow,
  BankStatementPreview,
  BankStatementUpload,
  BankStatementUploadDetail,
  PortalConnectionSummary,
  PortalListingSync,
  PortalName,
  DemoDataStatus,
  ManagementAgreement,
  MessageTemplate,
  MessageTemplatePreview,
  MessageTemplateType,
  MeterPhotoRead,
  PaymentBehaviour,
  TenantTurnover,
  UtilityAnalytics,
  SearchResult,
  SavedView,
  ApprovalRule,
  ApprovalRequest,
  ApprovalRequestDetail,
  ApprovalRequestStatus,
} from './types'

const get = async <T>(url: string, params?: unknown): Promise<T> =>
  (await apiClient.get<T>(url, { params: params as never })).data
const post = async <T>(url: string, body?: unknown): Promise<T> =>
  (await apiClient.post<T>(url, body)).data
const patch = async <T>(url: string, body?: unknown): Promise<T> =>
  (await apiClient.patch<T>(url, body)).data
const put = async <T>(url: string, body?: unknown): Promise<T> =>
  (await apiClient.put<T>(url, body)).data
const del = async <T>(url: string): Promise<T> => (await apiClient.delete<T>(url)).data
/** For endpoints that answer with a rendered file rather than JSON. */
const postBlob = async (url: string, body?: unknown): Promise<Blob> =>
  (await apiClient.post(url, body, { responseType: 'blob' })).data
const getBlob = async (url: string, params?: unknown): Promise<Blob> =>
  (await apiClient.get(url, { params: params as never, responseType: 'blob' })).data

// ------------------------------------------------------------------ properties

export const propertiesApi = {
  list: (params?: { search?: string; include_archived?: boolean }) =>
    get<PropertySummary[]>('/properties', params),
  get: (id: string) => get<PropertySummary>(`/properties/${id}`),
  create: (body: unknown) => post<Property>('/properties', body),
  update: (id: string, body: unknown) => patch<Property>(`/properties/${id}`, body),
  archive: (id: string) => del<Property>(`/properties/${id}`),
  restore: (id: string) => post<Property>(`/properties/${id}/restore`),
  units: (id: string, params?: { include_archived?: boolean }) =>
    get<Unit[]>(`/properties/${id}/units`, params),
}

export const unitsApi = {
  list: (params?: {
    property_id?: string
    unit_status?: string
    search?: string
    include_archived?: boolean
  }) => get<Unit[]>('/units', params),
  get: (id: string) => get<UnitDetail>(`/units/${id}`),
  create: (body: unknown) => post<Unit>('/units', body),
  bulkCreate: (body: unknown) => post<{ created: number; units: Unit[] }>('/units/bulk', body),
  update: (id: string, body: unknown) => patch<Unit>(`/units/${id}`, body),
  setStatus: (id: string, body: unknown) => patch<Unit>(`/units/${id}/status`, body),
  archive: (id: string) => del<Unit>(`/units/${id}`),
}

export const dashboardApi = {
  portfolio: () => get<PortfolioDashboard>('/dashboard/portfolio'),
  financial: (months_back = 6) => get<FinancialDashboard>('/dashboard/financial', { months_back }),
}

// --------------------------------------------------------------------- tenancy

export const tenantsApi = {
  list: (params?: {
    search?: string
    tenancy_status?: string
    property_id?: string
    include_archived?: boolean
  }) => get<TenantListItem[]>('/tenants', params),
  get: (id: string) => get<Tenant>(`/tenants/${id}`),
  create: (body: unknown) => post<Tenant>('/tenants', body),
  update: (id: string, body: unknown) => patch<Tenant>(`/tenants/${id}`, body),
  archive: (id: string) => del<Tenant>(`/tenants/${id}`),
  documents: (id: string) => get<StoredDocument[]>(`/tenants/${id}/documents`),
  exportCsvUrl: '/tenants/export.csv',
}

export const tenanciesApi = {
  list: (params?: {
    tenancy_status?: string
    unit_id?: string
    tenant_id?: string
    expiring_within_days?: number
  }) => get<TenancyDetail[]>('/tenancies', params),
  get: (id: string) => get<TenancyDetail>(`/tenancies/${id}`),
  create: (body: unknown) => post<TenancyDetail>('/tenancies', body),
  update: (id: string, body: unknown) => patch<TenancyDetail>(`/tenancies/${id}`, body),
  vacate: (id: string, body: unknown) => post<TenancyDetail>(`/tenancies/${id}/vacate`, body),
  regenerateLease: (id: string, templateId?: string) =>
    post<{ file_id: string; filename: string; url: string }>(
      `/tenancies/${id}/lease${templateId ? `?template_id=${templateId}` : ''}`,
    ),
  leasePreviewUrl: (id: string) => `/tenancies/${id}/lease/preview`,
}

export const leaseTemplatesApi = {
  list: () => get<LeaseTemplate[]>('/lease-templates'),
  starter: () => get<LeaseTemplateStarter>('/lease-templates/starter'),
  /** Renders sample data through a body — saved or not — and returns a PDF blob. */
  preview: (body: {
    body_html?: string
    letterhead_text?: string | null
    logo_file_id?: string | null
    template_id?: string
  }) => postBlob('/lease-templates/preview', body),
  create: (body: unknown) => post<LeaseTemplate>('/lease-templates', body),
  update: (id: string, body: unknown) => patch<LeaseTemplate>(`/lease-templates/${id}`, body),

  // AI lease analysis (Sprint 22, US-096)
  analyze: (id: string) => post<LeaseAnalysis>(`/lease-templates/${id}/analyze`),
  analyses: (id: string) => get<LeaseAnalysis[]>(`/lease-templates/${id}/analyses`),
  resolveSuggestion: (suggestionId: string, status: 'accepted' | 'dismissed') =>
    patch<LeaseSuggestion>(`/lease-templates/suggestions/${suggestionId}`, { status }),
}

// ----------------------------------------------------------------------- money

export const invoicesApi = {
  list: (params?: {
    tenancy_id?: string
    invoice_status?: string
    property_id?: string
    limit?: number
  }) => get<InvoiceDetail[]>('/invoices', params),
  get: (id: string) => get<InvoiceDetail>(`/invoices/${id}`),
  generate: (body: { tenancy_id: string; issue_date?: string }) =>
    post<InvoiceDetail>('/invoices/generate', body),
}

export const paymentsApi = {
  list: (params?: {
    tenancy_id?: string
    property_id?: string
    payment_status?: string
    limit?: number
  }) => get<PaymentDetail[]>('/payments', params),
  get: (id: string) => get<PaymentDetail>(`/payments/${id}`),
  record: (body: unknown) => post<PaymentDetail>('/payments', body),
  stkPush: (body: { tenancy_id: string; amount: string; phone_number?: string }) =>
    post<{ payment: PaymentDetail; message: string }>('/payments/stk-push', body),
  status: (id: string) => get<PaymentDetail>(`/payments/${id}/status`),

  // Dual approval for large cash (Sprint 26). A held payment is recorded
  // but not banked — nothing is allocated or receipted until it is approved.
  pendingApproval: () => get<PaymentDetail[]>('/payments/pending-approval'),
  approve: (id: string, note?: string) =>
    post<PaymentDetail>(`/payments/${id}/approve`, { note }),
  reject: (id: string, reason: string) =>
    post<PaymentDetail>(`/payments/${id}/reject`, { reason }),

  // Bank transfer (Sprint 23, US-101)
  bankInstructions: () => get<BankInstructions>('/payments/bank-instructions'),
  previewBankStatement: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient
      .post<BankStatementPreview>('/payments/bank-statements/preview', form)
      .then((response) => response.data)
  },
  commitBankStatement: (rows: BankStatementCommitRow[]) =>
    post<BankStatementCommitResult>('/payments/bank-statements/commit', { rows }),
  bankStatements: () => get<BankStatementUpload[]>('/payments/bank-statements'),
  bankStatement: (id: string) => get<BankStatementUploadDetail>(`/payments/bank-statements/${id}`),
}

export const arrearsApi = {
  report: (params?: { property_id?: string; min_amount?: string }) =>
    get<ArrearsReport>('/arrears', params),
  remind: (body: { tenancy_ids?: string[]; property_id?: string }) =>
    post<{ sent: number; message: string }>('/arrears/remind', body),
  exportCsvUrl: '/arrears/export.csv',
}

// ------------------------------------------------------------------ operations

export const metersApi = {
  context: (unit_id: string, meter_type: string) =>
    get<MeterContext>('/meter-readings/context', { unit_id, meter_type }),
  due: (limit = 25) => get<MeterContext[]>('/meter-readings/due', { limit }),
  list: (params?: {
    unit_id?: string
    property_id?: string
    meter_type?: string
    limit?: number
  }) => get<MeterReading[]>('/meter-readings', params),
  record: (body: unknown) => post<MeterReading>('/meter-readings', body),
  // Camera OCR (Sprint 26). A suggestion, never an answer — the caretaker
  // still confirms or corrects the figure before it becomes a bill.
  readPhoto: (body: { photo_file_id: string; meter_type?: string }) =>
    post<MeterPhotoRead>('/meter-readings/read-photo', body),
}

export const visitorLogsApi = {
  list: (params?: {
    unit_id?: string
    property_id?: string
    since?: string
    open_only?: boolean
    limit?: number
  }) => get<VisitorLog[]>('/visitor-logs', params),
  log: (body: unknown) => post<VisitorLog>('/visitor-logs', body),
  checkOut: (id: string) => post<VisitorLog>(`/visitor-logs/${id}/check-out`),
}

export const coTenantsApi = {
  list: (tenancyId: string) => get<CoTenant[]>(`/tenancies/${tenancyId}/co-tenants`),
  add: (tenancyId: string, tenant_id: string) =>
    post<CoTenant>(`/tenancies/${tenancyId}/co-tenants`, { tenant_id }),
  remove: (tenancyId: string, tenantId: string) =>
    del<void>(`/tenancies/${tenancyId}/co-tenants/${tenantId}`),
  promote: (tenancyId: string, tenantId: string) =>
    post<TenancyDetail>(`/tenancies/${tenancyId}/co-tenants/${tenantId}/promote`),
}

export const privacyApi = {
  list: (tenant_id?: string) => get<DataRequest[]>('/privacy/data-requests', { tenant_id }),
  requestExport: (tenantId: string) =>
    post<DataRequest>(`/privacy/tenants/${tenantId}/export`),
  requestErasure: (tenantId: string) =>
    post<DataRequest>(`/privacy/tenants/${tenantId}/erase`),
}

export const maintenanceApi = {
  list: (params?: {
    unit_id?: string
    property_id?: string
    request_status?: string
    priority?: string
    limit?: number
  }) => get<MaintenanceRequest[]>('/maintenance', params),
  get: (id: string) => get<MaintenanceRequest>(`/maintenance/${id}`),
  create: (body: unknown) => post<MaintenanceRequest>('/maintenance', body),
  update: (id: string, body: unknown) => patch<MaintenanceRequest>(`/maintenance/${id}`, body),
  unitHistory: (unitId: string) =>
    get<MaintenanceRequest[]>(`/maintenance/unit/${unitId}/history`),
  analytics: (months = 12) => get<MaintenanceOverview>('/maintenance/analytics', { months }),

  // Lifecycle actions (US-061) — one call per state change.
  review: (id: string) => post<MaintenanceRequest>(`/maintenance/${id}/review`),
  requestInfo: (id: string, question: string) =>
    post<MaintenanceRequest>(`/maintenance/${id}/request-info`, { question }),
  approve: (
    id: string,
    body: {
      estimated_cost?: string | null
      expected_completion_date?: string | null
      vendor_id?: string | null
    },
  ) => post<MaintenanceRequest>(`/maintenance/${id}/approve`, body),
  reject: (id: string, body: { reason: string; note?: string }) =>
    post<MaintenanceRequest>(`/maintenance/${id}/reject`, body),
  assign: (
    id: string,
    body: { vendor_id: string; estimated_cost?: string | null; expected_completion_date?: string | null },
  ) => post<MaintenanceRequest>(`/maintenance/${id}/assign`, body),
  start: (id: string) => post<MaintenanceRequest>(`/maintenance/${id}/start`),
  complete: (
    id: string,
    body: {
      actual_cost: string
      resolution_notes?: string
      vendor_rating?: number | null
      vendor_review?: string | null
    },
  ) => post<MaintenanceRequest>(`/maintenance/${id}/complete`, body),
  close: (id: string) => post<MaintenanceRequest>(`/maintenance/${id}/close`),
  cancel: (id: string, reason?: string) =>
    post<MaintenanceRequest>(`/maintenance/${id}/cancel`, { reason }),
}

export const assetsApi = {
  overview: () => get<FleetOverview>('/assets/overview'),
  list: (params?: {
    kind?: string
    asset_status?: string
    search?: string
    available_from?: string
    available_to?: string
  }) => get<RentalAsset[]>('/assets', params),
  get: (id: string) => get<RentalAsset>(`/assets/${id}`),
  create: (body: unknown) => post<RentalAsset>('/assets', body),
  update: (id: string, body: unknown) => patch<RentalAsset>(`/assets/${id}`, body),
  availability: (id: string, params?: { day_from?: string; day_to?: string }) =>
    get<AvailabilityRow[]>(`/assets/${id}/availability`, params),
}

export const rentalAgreementsApi = {
  list: (params?: {
    asset_id?: string
    tenant_id?: string
    agreement_status?: string
    overdue_only?: boolean
  }) => get<RentalAgreement[]>('/rental-agreements', params),
  get: (id: string) => get<RentalAgreement>(`/rental-agreements/${id}`),
  book: (body: unknown) => post<RentalAgreement>('/rental-agreements', body),
  checkOut: (id: string, body: unknown) =>
    post<RentalAgreement>(`/rental-agreements/${id}/check-out`, body),
  checkIn: (id: string, body: unknown) =>
    post<RentalAgreement>(`/rental-agreements/${id}/check-in`, body),
  cancel: (id: string, reason?: string) =>
    post<RentalAgreement>(`/rental-agreements/${id}/cancel`, { reason }),
}

export const complianceApi = {
  dashboard: () => get<ComplianceDashboard>('/compliance/dashboard'),
  list: (params?: { property_id?: string; item_status?: string }) =>
    get<ComplianceItem[]>('/compliance', params),
  create: (body: unknown) => post<ComplianceItem>('/compliance', body),
  update: (id: string, body: unknown) => patch<ComplianceItem>(`/compliance/${id}`, body),
  reportUrl: (propertyId?: string) =>
    propertyId ? `/compliance/report?property_id=${propertyId}` : '/compliance/report',
}

export const parkingApi = {
  overview: (propertyId: string) => get<ParkingOverview>(`/parking/property/${propertyId}`),
  createBay: (body: unknown) => post<{ id: string; bay_number: string }>('/parking/bays', body),
  allocate: (bayId: string, body: unknown) => post(`/parking/bays/${bayId}/allocate`, body),
  release: (allocationId: string) => post(`/parking/allocations/${allocationId}/release`),
}

export const amenitiesApi = {
  list: (propertyId?: string) =>
    get<Amenity[]>('/amenities', propertyId ? { property_id: propertyId } : undefined),
  create: (body: unknown) => post<Amenity>('/amenities', body),
  calendar: (amenityId: string, params?: { day_from?: string; day_to?: string }) =>
    get<AmenityBooking[]>(`/amenities/${amenityId}/calendar`, params),
  book: (amenityId: string, body: unknown) =>
    post<AmenityBooking>(`/amenities/${amenityId}/bookings`, body),
  block: (amenityId: string, body: unknown) =>
    post<AmenityBooking>(`/amenities/${amenityId}/block`, body),
  cancel: (bookingId: string) => post<AmenityBooking>(`/amenities/bookings/${bookingId}/cancel`),
  usage: (propertyId: string, months = 1) =>
    get<AmenityUsageRow[]>(`/amenities/usage/${propertyId}`, { months }),
}

export const utilitiesApi = {
  list: (propertyId?: string) =>
    get<UtilityAccount[]>('/utilities', propertyId ? { property_id: propertyId } : undefined),
  save: (body: unknown) => put<UtilityAccount>('/utilities', body),
  updateStatus: (accountId: string, body: unknown) =>
    post<UtilityAccount>(`/utilities/${accountId}/status`, body),
}

export const vacanciesApi = {
  desk: () => get<VacancyReport>('/vacancies'),
  conversion: () => get<ConversionReport>('/vacancies/conversion'),
  listingForUnit: (unitId: string) =>
    get<VacancyListingRow>(`/vacancies/units/${unitId}/listing`),
  updateListing: (listingId: string, body: unknown) =>
    patch<VacancyListingRow>(`/vacancies/listings/${listingId}`, body),
  rotateLink: (listingId: string) =>
    post<VacancyListingRow>(`/vacancies/listings/${listingId}/rotate-link`),
  inquiries: (params?: { unit_id?: string; stage?: string; stale_only?: boolean }) =>
    get<InquiryRow[]>('/vacancies/inquiries', params),
  updateInquiry: (id: string, body: unknown) =>
    patch<InquiryRow>(`/vacancies/inquiries/${id}`, body),
  exports: () => get<DataExportRow[]>('/vacancies/exports'),
}

/** The public advert and its enquiry form — no login anywhere in here. */
export const publicListingApi = {
  get: (slug: string) => get<PublicListing>(`/listings/${slug}`),
  inquire: (slug: string, body: unknown) =>
    post<{ status: string; message: string }>(`/listings/${slug}/inquire`, body),
}

/** The help centre, readable without an account. Same rows `customerSuccessApi`
 *  serves to the in-app HelpPanel — the knowledge base is platform-wide, so
 *  there is no per-organisation variant to keep in step. */
export const publicHelpApi = {
  search: (q?: string) => get<HelpArticle[]>('/help/articles', q ? { q } : undefined),
  article: (slug: string) => get<HelpArticle>(`/help/articles/${slug}`),
}

export const serviceChargesApi = {
  forProperty: (propertyId: string) =>
    get<ServiceChargeScheme | null>(`/service-charges/property/${propertyId}`),
  save: (propertyId: string, body: unknown) =>
    put<ServiceChargeScheme>(`/service-charges/property/${propertyId}`, body),
  reconciliation: (schemeId: string, params: { period_start: string; period_end: string }) =>
    get<ServiceChargeReconciliation>(`/service-charges/${schemeId}/reconciliation`, params),
  expenses: (schemeId: string, params?: { since?: string; until?: string }) =>
    get<ServiceChargeExpense[]>(`/service-charges/${schemeId}/expenses`, params),
  recordExpense: (schemeId: string, body: unknown) =>
    post<ServiceChargeExpense>(`/service-charges/${schemeId}/expenses`, body),
  sinkingFund: (schemeId: string) =>
    get<SinkingFundEntry[]>(`/service-charges/${schemeId}/sinking-fund`),
  recordSinkingFund: (schemeId: string, body: unknown) =>
    post<SinkingFundEntry>(`/service-charges/${schemeId}/sinking-fund`, body),
}

/** Every bulk action is preview-then-execute: nothing is sent on the preview. */
export const bulkApi = {
  list: (params?: { kind?: string; limit?: number }) => get<BulkOperation[]>('/bulk', params),
  get: (id: string) => get<BulkOperation>(`/bulk/${id}`),
  previewRentIncrease: (body: unknown) =>
    post<BulkOperation>('/bulk/rent-increase/preview', body),
  previewReminders: (body: unknown) => post<BulkOperation>('/bulk/reminders/preview', body),
  previewAnnouncement: (body: unknown) => post<BulkOperation>('/bulk/announcement/preview', body),
  previewInvoiceRun: (body: unknown) => post<BulkOperation>('/bulk/invoices/preview', body),
  previewRenewals: (body: unknown) => post<BulkOperation>('/bulk/renewals/preview', body),
  previewDocuments: (body: unknown) => post<BulkOperation>('/bulk/documents/preview', body),
  execute: (id: string) => post<BulkOperation>(`/bulk/${id}/execute`),
  cancel: (id: string) => post<BulkOperation>(`/bulk/${id}/cancel`),

  templateUrl: () => '/bulk/import/template',
  previewImport: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiClient
      .post<ImportPreview>('/bulk/import/preview', form)
      .then((response) => response.data)
  },
  commitImport: (rows: unknown[]) => post<ImportResult>('/bulk/import/commit', { rows }),
}

export const applicationsApi = {
  list: (params?: {
    unit_id?: string
    property_id?: string
    application_status?: string
    open_only?: boolean
    search?: string
    limit?: number
  }) => get<TenantApplication[]>('/applications', params),
  get: (id: string) => get<TenantApplication>(`/applications/${id}`),
  create: (body: unknown) => post<TenantApplication>('/applications', body),
  update: (id: string, body: unknown) => patch<TenantApplication>(`/applications/${id}`, body),
  summary: () => get<ScreeningSummary>('/applications/summary'),
  waitingList: (unitId: string) => get<WaitingListEntry[]>(`/applications/waiting-list/${unitId}`),

  review: (id: string) => post<TenantApplication>(`/applications/${id}/review`),
  interview: (id: string, body: { scheduled_for: string; note?: string }) =>
    post<TenantApplication>(`/applications/${id}/interview`, body),
  approve: (id: string, body: { note?: string; reject_others?: boolean }) =>
    post<TenantApplication>(`/applications/${id}/approve`, body),
  reject: (id: string, body: { reason: string; note?: string }) =>
    post<TenantApplication>(`/applications/${id}/reject`, body),
  withdraw: (id: string, reason?: string) =>
    post<TenantApplication>(`/applications/${id}/withdraw`, { reason }),
  addGuarantor: (id: string, body: unknown) =>
    post<TenantApplication>(`/applications/${id}/guarantors`, body),
  requestReference: (id: string, body: unknown) =>
    post<TenantApplication>(`/applications/${id}/references`, body),
  sendGuaranteeForSigning: (id: string, guarantorId: string) =>
    post<TenantApplication>(`/applications/${id}/guarantors/${guarantorId}/sign`),
}

/** The three unauthenticated screening flows: applicant, guarantor, referee. */
export const publicScreeningApi = {
  listing: (unitId: string) => get<PublicUnitListing>(`/apply/${unitId}`),
  apply: (unitId: string, body: unknown) =>
    post<{ reference_code: string; status: string; message: string }>(`/apply/${unitId}`, body),
  guarantee: (token: string) => get<GuarantorInvite>(`/guarantee/${token}`),
  respondToGuarantee: (token: string, body: { accepted: boolean; reason?: string }) =>
    post<{ status: string; message: string }>(`/guarantee/${token}`, body),
  reference: (token: string) => get<ReferenceInvite>(`/reference/${token}`),
  respondToReference: (
    token: string,
    body: { paid_on_time: boolean; would_rent_again: boolean; note?: string },
  ) => post<{ status: string; message: string }>(`/reference/${token}`, body),
}

export const vendorsApi = {
  list: (params?: {
    specialty?: string
    category?: string
    search?: string
    include_inactive?: boolean
  }) => get<Vendor[]>('/vendors', params),
  get: (id: string) => get<VendorDetail>(`/vendors/${id}`),
  create: (body: unknown) => post<Vendor>('/vendors', body),
  update: (id: string, body: unknown) => patch<Vendor>(`/vendors/${id}`, body),
  deactivate: (id: string) => post<Vendor>(`/vendors/${id}/deactivate`),
}

export const noticesApi = {
  list: (params?: { tenancy_id?: string }) => get<VacateNotice[]>('/vacate-notices', params),
  create: (body: unknown) => post<VacateNotice>('/vacate-notices', body),
  acknowledge: (id: string) => post<VacateNotice>(`/vacate-notices/${id}/acknowledge`),
}

export const caretakerApi = {
  today: () => get<CaretakerTaskList>('/caretaker/today'),
}

export const activityApi = {
  list: (params?: {
    user_id?: string
    entity_type?: string
    entity_id?: string
    action?: string
    limit?: number
  }) => get<ActivityEntry[]>('/activity', params),
  caretakers: (days = 30) => get<unknown[]>('/activity/caretakers', { days }),
}

// -------------------------------------------------------------------- org/team

export const organizationApi = {
  me: () => get<Record<string, unknown>>('/organizations/me'),
  update: (body: unknown) => patch<Record<string, unknown>>('/organizations/me', body),

  // How this landlord collects rent. Credentials are write-only — they go up
  // here and never come back down.
  mpesaSetup: () => get<MpesaSetupStatus>('/organizations/me/mpesa'),
  saveMpesaSetup: (body: unknown) => put<MpesaSetupStatus>('/organizations/me/mpesa', body),
  testMpesaSetup: () => post<MpesaTestResult>('/organizations/me/mpesa/test'),

  // Sample data (Sprint 26). Teardown deletes exactly the rows the seeding
  // created, so it can never take a real one with it.
  demoData: () => get<DemoDataStatus>('/organizations/demo-data'),
  loadDemoData: () => post<DemoDataStatus>('/organizations/demo-data'),
  removeDemoData: () => del<{ message: string }>('/organizations/demo-data'),
}

// --------------------------------------------------------- message templates

export const messageTemplatesApi = {
  types: () => get<MessageTemplateType[]>('/message-templates/types'),
  list: () => get<MessageTemplate[]>('/message-templates'),
  save: (body: {
    notification_type: string
    channel: string
    title?: string | null
    body: string
    is_active?: boolean
  }) => put<MessageTemplate>('/message-templates', body),
  preview: (body: { notification_type: string; title?: string | null; body: string }) =>
    post<MessageTemplatePreview>('/message-templates/preview', body),
  remove: (id: string) => del<{ message: string }>(`/message-templates/${id}`),
}

// ----------------------------------------------------- management agreements

export const managementAgreementsApi = {
  list: (params?: { owner_profile_id?: string; live_only?: boolean }) =>
    get<ManagementAgreement[]>('/agency/management-agreements', params),
  get: (id: string) => get<ManagementAgreement>(`/agency/management-agreements/${id}`),
  create: (body: unknown) => post<ManagementAgreement>('/agency/management-agreements', body),
  send: (id: string, body: { agency_signatory_name: string; agency_signatory_phone: string }) =>
    post<ManagementAgreement>(`/agency/management-agreements/${id}/send`, body),
  terminate: (
    id: string,
    body: { requested_by: 'owner' | 'agency'; reason?: string; effective_date?: string },
  ) => post<ManagementAgreement>(`/agency/management-agreements/${id}/terminate`, body),
  withdrawTermination: (id: string) =>
    post<ManagementAgreement>(`/agency/management-agreements/${id}/withdraw-termination`),
}

export const teamApi = {
  list: () => get<TeamMember[]>('/team'),
  invitations: () => get<Invitation[]>('/team/invitations'),
  invite: (body: unknown) => post<Invitation>('/team/invitations', body),
  revokeInvitation: (id: string) => del<{ message: string }>(`/team/invitations/${id}`),
  updateAccess: (id: string, body: unknown) => patch<TeamMember>(`/team/${id}/access`, body),
  previewInvitation: (token: string) =>
    get<{ full_name: string; organization_name: string; role: string; phone_number: string }>(
      '/invitations/preview',
      { token },
    ),
  acceptInvitation: (body: { token: string; password: string }) =>
    post<{ user: unknown; tokens: { access_token: string; refresh_token: string } }>(
      '/invitations/accept',
      body,
    ),
}

// ------------------------------------------------------------- notifications

export const notificationsApi = {
  list: (params?: { unread_only?: boolean; limit?: number }) =>
    get<NotificationRow[]>('/notifications', params),
  unreadCount: () => get<{ unread: number }>('/notifications/unread-count'),
  markRead: (id: string) => post<{ message: string }>(`/notifications/${id}/read`),
  markAllRead: () => post<{ message: string }>('/notifications/read-all'),
  preferences: () => get<NotificationPreference[]>('/notifications/preferences'),
  setPreferences: (preferences: NotificationPreference[]) =>
    put<{ message: string }>('/notifications/preferences', { preferences }),
}

export const pushApi = {
  vapidKey: () => get<{ public_key: string | null; configured: boolean }>('/push/vapid-key'),
  subscribe: (body: {
    endpoint: string
    p256dh_key: string
    auth_key: string
    user_agent?: string
  }) => post<{ message: string }>('/push/subscribe', body),
  unsubscribe: (endpoint: string) =>
    post<{ message: string }>(`/push/unsubscribe?endpoint=${encodeURIComponent(endpoint)}`),
}

// ----------------------------------------------------------------------- files

export interface UploadTicket {
  file_id: string
  storage_key: string
  upload_url: string
  method: string
  headers: Record<string, string>
  expires_in: number
}

export const filesApi = {
  requestUpload: (body: {
    filename: string
    content_type: string
    size_bytes: number
    category?: string
    entity_type?: string
    entity_id?: string
  }) => post<UploadTicket>('/files/upload-url', body),
  confirm: (id: string, size_bytes?: number) =>
    post<{ id: string; url: string }>(`/files/${id}/confirm`, { size_bytes }),
  get: (id: string) => get<{ id: string; url: string; filename: string }>(`/files/${id}`),
}

// ------------------------------------------------------------ scheduled tasks

export const tasksApi = {
  overview: () => get<TaskOverview>('/tasks'),
  history: (taskName: string) => get<TaskRun[]>(`/tasks/${taskName}/history`),
  /** System administrators only — these tasks act across every organisation. */
  run: (taskName: string) =>
    post<{ task_name: string; queued: boolean; task_id: string }>(`/tasks/${taskName}/run`),
}

// ------------------------------------------------------- caretaker performance

export const caretakerPerformanceApi = {
  list: (windowDays = 30) =>
    get<CaretakerScore[]>('/caretaker/performance', { window_days: windowDays }),
  detail: (userId: string, windowDays = 30) =>
    get<CaretakerScoreDetail>(`/caretaker/performance/${userId}`, { window_days: windowDays }),
  openJobs: (userId: string) =>
    get<CaretakerOpenJob[]>(`/caretaker/performance/${userId}/open-jobs`),
}

// ------------------------------------------------------------- lease renewals

export const renewalsApi = {
  list: (tenancyId?: string) =>
    get<LeaseRenewal[]>('/renewals', tenancyId ? { tenancy_id: tenancyId } : undefined),
  proposedTerms: (tenancyId: string) =>
    get<ProposedTerms>(`/renewals/tenancies/${tenancyId}/proposed-terms`),
  offer: (tenancyId: string, body?: { proposed_rent?: string; term_months?: number }) =>
    post<LeaseRenewal>(`/renewals/tenancies/${tenancyId}`, body ?? {}),

  // Public, token-authenticated — the tenant has no account.
  read: (token: string) => get<RenewalOffer>(`/renew/${token}`),
  accept: (token: string) =>
    post<{ status: string; reference_code: string; new_end_date: string; message: string }>(
      `/renew/${token}/accept`,
    ),
  decline: (token: string, reason?: string) =>
    post<{ status: string; reference_code: string; message: string }>(`/renew/${token}/decline`, {
      reason,
    }),
}

// ------------------------------------------------------------------- analytics

export const analyticsApi = {
  revenue: (months = 6) => get<RevenuePoint[]>('/analytics/revenue', { months }),
  propertyPerformance: () => get<PropertyPerformance[]>('/analytics/property-performance'),
  cashFlowForecast: (months_ahead = 3) =>
    get<CashFlowPoint[]>('/analytics/cash-flow-forecast', { months_ahead }),
  expiringLeases: () => get<ExpiringLeases>('/analytics/expiring-leases'),
  maintenance: () => get<MaintenanceAnalytics>('/analytics/maintenance'),
  vacancyRisk: (days_ahead = 90) =>
    get<VacancyRiskItem[]>('/analytics/vacancy-risk', { days_ahead }),
  rentReview: (min_months = 12) =>
    get<RentReviewSuggestion[]>('/analytics/rent-review', { min_months }),
  // Sprint 26 — the Module 12 metrics that had never been computed.
  utilities: (months = 6) => get<UtilityAnalytics>('/analytics/utilities', { months }),
  paymentBehaviour: (months = 6) =>
    get<PaymentBehaviour>('/analytics/payment-behaviour', { months }),
  turnover: (months = 12) => get<TenantTurnover>('/analytics/turnover', { months }),
}

// ----------------------------------------------------------------------- eTIMS

export const etimsApi = {
  credentials: () => get<EtimsCredentials>('/etims/credentials'),
  saveCredentials: (body: {
    kra_pin: string
    device_serial: string
    api_key: string
    branch_id?: string
    environment?: string
  }) => put<EtimsCredentials>('/etims/credentials', body),
  deleteCredentials: () => del<{ removed: boolean }>('/etims/credentials'),
  report: () => get<EtimsReport>('/etims/report'),
  retry: (submissionId: string) =>
    post<{ id: string; status: string; attempts: number; last_error: string | null }>(
      `/etims/submissions/${submissionId}/retry`,
    ),
}

// -------------------------------------------------------- partner integrations

export const portalsApi = {
  list: () => get<PortalConnectionSummary[]>('/integrations/portals'),
  save: (portal: PortalName, body: { api_key: string; account_id?: string }) =>
    put<PortalConnectionSummary>(`/integrations/portals/${portal}`, body),
  remove: (portal: PortalName) => del<{ removed: boolean }>(`/integrations/portals/${portal}`),
  listingStatus: (listingId: string) =>
    get<PortalListingSync[]>(`/integrations/portals/listings/${listingId}`),
}

export const accountingApi = {
  list: () => get<AccountingConnection[]>('/integrations/accounting'),
  connect: (provider: AccountingProvider, environment: 'sandbox' | 'production') =>
    get<{ authorize_url: string }>(`/integrations/accounting/${provider}/connect`, { environment }),
  disconnect: (provider: AccountingProvider) =>
    del<{ removed: boolean }>(`/integrations/accounting/${provider}`),
  report: (provider: AccountingProvider) =>
    get<AccountingSyncReport>(`/integrations/accounting/${provider}/report`),
  sync: (provider: AccountingProvider) =>
    post<AccountingSyncReport>(`/integrations/accounting/${provider}/sync`),
}

// --------------------------------------------------------------- demand letters

export const demandLettersApi = {
  issue: (tenancyId: string) => post<DemandLetter>(`/arrears/demand-letters/${tenancyId}`),
  preview: (tenancyId: string) => getBlob(`/arrears/demand-letters/${tenancyId}/preview`),
}

// ------------------------------------------------------------------ inspections

export const inspectionsApi = {
  list: (params?: { unit_id?: string; tenancy_id?: string; inspection_type?: string }) =>
    get<InspectionSummary[]>('/inspections', params),
  get: (id: string) => get<InspectionDetail>(`/inspections/${id}`),
  create: (body: {
    unit_id: string
    tenancy_id?: string | null
    inspection_type: string
    notes?: string
    gps_latitude?: number | null
    gps_longitude?: number | null
  }) => post<InspectionDetail>('/inspections', body),
  updateRooms: (id: string, body: { rooms_data: unknown[]; notes?: string | null }) =>
    patch<InspectionDetail>(`/inspections/${id}/rooms`, body),
  submit: (id: string) => post<InspectionDetail>(`/inspections/${id}/submit`),
  /** Move-out against move-in, room by room. */
  comparison: (id: string) => get<InspectionComparison>(`/inspections/${id}/comparison`),
  documents: (id: string) => get<InspectionDocuments>(`/inspections/${id}/documents`),
  setDeduction: (id: string, body: { deduction_amount: string; deduction_notes: string }) =>
    post<InspectionDetail>(`/inspections/${id}/deduction`, body),
  compliance: () => get<InspectionCompliance>('/inspections/compliance'),
}

// ------------------------------------------------------------------ vault

export const vaultApi = {
  tenant: (
    tenantId: string,
    params?: { category?: string; search?: string; include_archived?: boolean },
  ) => get<TenantVault>(`/vault/tenants/${tenantId}`, params),
  property: (
    propertyId: string,
    params?: { category?: string; search?: string; include_archived?: boolean },
  ) => get<PropertyVault>(`/vault/properties/${propertyId}`, params),
  usage: () => get<VaultUsage>('/vault/usage'),
  categories: () => get<VaultCategories>('/vault/categories'),

  file: (body: {
    file_id: string
    entity_type: string
    entity_id: string
    category: string
    tags?: string[]
    description?: string | null
  }) => post<VaultDocument>('/vault/documents', body),
  update: (
    id: string,
    body: { category?: string; tags?: string[]; description?: string | null; filename?: string },
  ) => patch<VaultDocument>(`/vault/documents/${id}`, body),
  /** Replace a document. The old version is archived, never deleted. */
  addVersion: (id: string, body: { file_id: string; description?: string | null }) =>
    post<VaultDocument>(`/vault/documents/${id}/versions`, body),
  versions: (id: string) => get<VaultDocument[]>(`/vault/documents/${id}/versions`),
  archive: (id: string) => del<VaultDocument>(`/vault/documents/${id}`),
  send: (id: string, body: { tenant_id?: string; phone_number?: string; message?: string }) =>
    post<DocumentDelivery>(`/vault/documents/${id}/send`, body),
}

// ------------------------------------------------------- RentFlow's own billing

export const subscriptionApi = {
  plans: () => get<PlanOption[]>('/billing/plans'),
  current: () => get<Subscription | null>('/billing/subscription'),
  checkout: (body: { plan: string; interval: BillingInterval }) =>
    post<{
      invoice_id: string
      reference_code: string
      amount: string
      authorization_url: string
    }>('/billing/subscription/checkout', body),
  cancel: () => post<Subscription>('/billing/subscription/cancel'),
  invoices: () => get<SubscriptionInvoice[]>('/billing/subscription/invoices'),
}

// ---------------------------------------------------------------- tenant portal

export const portalApi = {
  home: () => get<PortalHome>('/portal/home'),
  pay: (body: { amount: string; phone_number?: string }) =>
    post<{ payment_id: string; reference_code: string; message: string }>('/portal/pay', body),
  paymentMethods: () => get<PortalPaymentMethods>('/portal/payment-methods'),
  paymentStatus: (id: string) => get<PaymentDetail>(`/portal/payments/${id}/status`),
  payments: () => get<PaymentDetail[]>('/portal/payments'),
  bankInstructions: () => get<BankInstructions>('/portal/bank-instructions'),
  invoices: () => get<InvoiceDetail[]>('/portal/invoices'),
  documents: () => get<StoredDocument[]>('/portal/documents'),
  lease: () => get<StoredDocument>('/portal/lease'),
  maintenance: () => get<MaintenanceRequest[]>('/portal/maintenance'),
  createMaintenance: (body: unknown) => post<MaintenanceRequest>('/portal/maintenance', body),
  rateMaintenance: (id: string, body: { rating: number; feedback?: string }) =>
    post<MaintenanceRequest>(`/portal/maintenance/${id}/rate`, body),
  vacateNotice: (body: { move_out_date: string; reason?: string }) =>
    post<VacateNotice>('/portal/vacate-notice', body),
  updateProfile: (body: unknown) => patch<{ message: string }>('/portal/profile', body),
  invite: (tenant_id: string) => post<{ message: string }>('/portal/invite', { tenant_id }),
  previewSetup: (token: string, tenant_id: string) =>
    get<{ full_name: string; organization_name: string; phone_number: string }>(
      '/portal/setup/preview',
      { token, tenant_id },
    ),
  setup: (tenant_id: string, body: { token: string; password: string }) =>
    post<{
      tenant_id: string
      full_name: string
      tokens: { access_token: string; refresh_token: string }
    }>(`/portal/setup?tenant_id=${tenant_id}`, body),

  // Magic link (Sprint 26). The request always answers the same way, whether
  // or not the number is a tenant — otherwise the endpoint is a directory of
  // which numbers belong to which landlord's tenants.
  requestMagicLink: (phone_number: string) =>
    post<{ message: string }>('/portal/magic-link', { phone_number }),
  verifyMagicLink: (body: { token: string; tenant_id: string }) =>
    post<{
      tenant_id: string
      full_name: string
      tokens: { access_token: string; refresh_token: string }
    }>('/portal/magic-link/verify', body),
  requestDataExport: () => post<{ id: string; download_url: string | null }>('/portal/data-requests/export'),
  requestDataErasure: () => post<{ message: string }>('/portal/data-requests/erase'),
}

// ---------------------------------------------------------------- agency mode

export const agencyApi = {
  dashboard: () => get<AgencyDashboard>('/agency/dashboard'),
  /** Per-owner rollup behind the dashboard's owner cards. */
  ownerSummaries: () => get<OwnerSummary[]>('/agency/owner-summaries'),

  ownerProfiles: () => get<OwnerProfile[]>('/agency/owner-profiles'),
  ownerProfile: (id: string) => get<OwnerProfile>(`/agency/owner-profiles/${id}`),
  createOwnerProfile: (body: unknown) => post<OwnerProfile>('/agency/owner-profiles', body),
  updateOwnerProfile: (id: string, body: unknown) =>
    patch<OwnerProfile>(`/agency/owner-profiles/${id}`, body),
  invitePortal: (id: string) =>
    post<{ message: string }>(`/agency/owner-profiles/${id}/invite-portal`),

  disbursements: (params?: { owner_profile_id?: string }) =>
    get<Disbursement[]>('/agency/disbursements', params),
  previewDisbursement: (params: {
    owner_profile_id: string
    period_start: string
    period_end: string
  }) => get<DisbursementPreview>('/agency/disbursements/calculate', params),
  createDisbursement: (body: unknown) => post<Disbursement>('/agency/disbursements', body),
  markDisbursementPaid: (id: string, body: { payment_method: string; payment_reference: string }) =>
    post<Disbursement>(`/agency/disbursements/${id}/mark-paid`, body),
  approveDisbursement: (id: string, body?: { note?: string }) =>
    post<Disbursement>(`/agency/disbursements/${id}/approve`, body ?? {}),
  rejectDisbursement: (id: string, body: { reason: string }) =>
    post<Disbursement>(`/agency/disbursements/${id}/reject`, body),
  /** Daraja B2C payout — only an approved disbursement can be sent. */
  payDisbursementViaMpesa: (id: string) =>
    post<Disbursement>(`/agency/disbursements/${id}/pay-mpesa`),
  disbursementStatement: (id: string, params?: { regenerate?: boolean }) =>
    get<DisbursementStatement>(`/agency/disbursements/${id}/statement`, params),

  /** What an owner-portal user sees — their own properties only. */
  ownerPortal: () => get<OwnerPortalSummary>('/agency/owner-portal/summary'),
}

export const apiKeysApi = {
  list: () => get<ApiKey[]>('/developer/api-keys'),
  create: (body: { name: string; scopes: string[]; expires_at?: string | null }) =>
    post<ApiKeyCreated>('/developer/api-keys', body),
  usage: (id: string) => get<ApiKeyUsage>(`/developer/api-keys/${id}/usage`),
  revoke: (id: string) => post<ApiKey>(`/developer/api-keys/${id}/revoke`),
}

export const webhooksApi = {
  list: () => get<WebhookEndpoint[]>('/developer/webhooks'),
  create: (body: { url: string; description?: string | null; event_types: string[] }) =>
    post<WebhookEndpointCreated>('/developer/webhooks', body),
  update: (id: string, body: unknown) => patch<WebhookEndpoint>(`/developer/webhooks/${id}`, body),
  archive: (id: string) => post<WebhookEndpoint>(`/developer/webhooks/${id}/archive`),
  secret: (id: string) => get<{ secret: string }>(`/developer/webhooks/${id}/secret`),
  deliveries: (id: string) => get<WebhookDelivery[]>(`/developer/webhooks/${id}/deliveries`),
}

// ------------------------------------------------------------ customer success

export const customerSuccessApi = {
  onboarding: () => get<OnboardingProgress>('/customer-success/onboarding'),
  markOnboardingStep: (step: string) =>
    patch<OnboardingProgress>('/customer-success/onboarding', { step }),
  dismissOnboarding: () => post<OnboardingProgress>('/customer-success/onboarding/dismiss'),

  searchHelp: (q?: string) => get<HelpArticle[]>('/customer-success/help/articles', q ? { q } : undefined),
  helpArticle: (slug: string) => get<HelpArticle>(`/customer-success/help/articles/${slug}`),

  createSupportRequest: (body: { subject: string; message: string }) =>
    post<SupportRequest>('/customer-success/support', body),

  referralSummary: () => get<ReferralSummary>('/customer-success/referral'),
  createReferral: (body: { referred_email: string }) =>
    post<Referral>('/customer-success/referral', body),

  pendingNps: () => get<NpsPending | null>('/customer-success/nps/pending'),
  respondToNps: (id: string, body: { score: number; comment?: string }) =>
    post<NpsPending>(`/customer-success/nps/${id}/respond`, body),

  pendingMilestones: () => get<Milestone[]>('/customer-success/milestones/pending'),
  acknowledgeMilestone: (key: string) =>
    post<void>(`/customer-success/milestones/${key}/acknowledge`),

  featureBoard: () => get<FeatureRequest[]>('/customer-success/feature-board'),
  createFeatureRequest: (body: { title: string; description: string }) =>
    post<{ id: string }>('/customer-success/feature-board', body),
  voteFeatureRequest: (id: string) =>
    post<{ voted: boolean }>(`/customer-success/feature-board/${id}/vote`),

  changelog: () => get<ChangelogEntry[]>('/customer-success/changelog'),
  changelogUnseenCount: () => get<{ count: number }>('/customer-success/changelog/unseen-count'),
}

// ------------------------------------------------------------------- internal

export const internalApi = {
  organizations: () => get<OrganizationHealthSummary[]>('/internal/organizations'),
  organizationHealthHistory: (organizationId: string) =>
    get<OrganizationHealthScorePoint[]>(`/internal/organizations/${organizationId}/health-history`),
  acknowledgeAlert: (id: string) => post<void>(`/internal/alerts/${id}/acknowledge`),
  updateOrganizationPlan: (organizationId: string, plan: string) =>
    patch<{ organization_id: string; plan: string }>(`/internal/organizations/${organizationId}/plan`, {
      plan,
    }),

  suspensionState: (organizationId: string) =>
    get<OrganizationSuspensionState>(`/internal/organizations/${organizationId}/suspension`),
  suspendOrganization: (organizationId: string, body: { reason: string; notify_account: boolean }) =>
    post<OrganizationSuspensionState>(`/internal/organizations/${organizationId}/suspend`, body),
  reactivateOrganization: (organizationId: string) =>
    post<OrganizationSuspensionState>(`/internal/organizations/${organizationId}/reactivate`),

  breachDashboard: () => get<BreachDashboard>('/internal/breaches/dashboard'),
  breaches: (open_only?: boolean) =>
    get<BreachRecord[]>('/internal/breaches', open_only !== undefined ? { open_only } : undefined),
  getBreach: (id: string) => get<BreachRecord>(`/internal/breaches/${id}`),
  reportBreach: (body: {
    category: string
    severity: string
    summary: string
    detail?: string | null
    detected_at?: string | null
    occurred_at?: string | null
    affected_organization_ids?: string[]
    affected_subject_count?: number | null
    data_categories?: string[]
  }) => post<BreachRecord>('/internal/breaches', body),
  advanceBreach: (id: string, body: { new_status: string; note?: string | null; regulator_reference?: string | null }) =>
    post<BreachRecord>(`/internal/breaches/${id}/advance`, body),
  notifyBreachCustomers: (id: string, message: string) =>
    post<{ contacts_notified: number }>(`/internal/breaches/${id}/notify-customers`, { message }),

  helpArticles: () => get<HelpArticle[]>('/internal/help-articles'),
  createHelpArticle: (body: {
    slug: string
    title: string
    body: string
    category: string
    is_published: boolean
  }) => post<HelpArticle>('/internal/help-articles', body),
  updateHelpArticle: (
    id: string,
    body: { slug: string; title: string; body: string; category: string; is_published: boolean },
  ) => patch<HelpArticle>(`/internal/help-articles/${id}`, body),

  changelogEntries: () => get<ChangelogEntry[]>('/internal/changelog-entries'),
  createChangelogEntry: (body: { title: string; body: string; is_published: boolean }) =>
    post<ChangelogEntry>('/internal/changelog-entries', body),
  updateChangelogEntry: (id: string, body: { title: string; body: string; is_published: boolean }) =>
    patch<ChangelogEntry>(`/internal/changelog-entries/${id}`, body),
}

// ------------------------------------------------------------------- reports

export const reportsApi = {
  datasets: () => get<ReportDatasetOption[]>('/reports/datasets'),
  fields: (dataset: ReportDataset) => get<ReportFieldMeta[]>(`/reports/datasets/${dataset}/fields`),
  preview: (body: ReportPreviewRequest) => post<ReportPreviewResult>('/reports/preview', body),

  list: () => get<ReportDefinition[]>('/reports/definitions'),
  get: (id: string) => get<ReportDefinition>(`/reports/definitions/${id}`),
  create: (body: ReportDefinitionInput) => post<ReportDefinition>('/reports/definitions', body),
  update: (id: string, body: Partial<ReportDefinitionInput>) =>
    patch<ReportDefinition>(`/reports/definitions/${id}`, body),
  remove: (id: string) => del<void>(`/reports/definitions/${id}`),

  monthly: () => get<MonthlyReport[]>('/reports/monthly'),
}

// -------------------------------------------------------------------- security

export const securityApi = {
  fraudAlerts: (status?: FraudAlertStatus) => get<FraudAlert[]>('/security/fraud-alerts', { status }),
  resolveFraudAlert: (id: string, status: 'suppressed' | 'resolved') =>
    patch<FraudAlert>(`/security/fraud-alerts/${id}`, { status }),
  exportAuditLog: (params: { format: 'csv' | 'pdf'; date_from?: string; date_to?: string }) =>
    getBlob('/security/audit-log/export', params),
  verifyAuditLog: () => get<AuditChainVerification>('/security/audit-log/verify'),
}

// ---------------------------------------------------------------------- search

export const searchApi = {
  query: (q: string) => get<SearchResult[]>('/search', { q }),
}

// ------------------------------------------------------------------ saved views

export const savedViewsApi = {
  list: (entityType: string) => get<SavedView[]>('/saved-views', { entity_type: entityType }),
  create: (body: {
    entity_type: string
    name: string
    filters: Record<string, unknown>
    is_shared?: boolean
    is_default?: boolean
  }) => post<SavedView>('/saved-views', body),
  update: (id: string, body: Partial<{ name: string; filters: Record<string, unknown>; is_shared: boolean; is_default: boolean }>) =>
    patch<SavedView>(`/saved-views/${id}`, body),
  remove: (id: string) => del<void>(`/saved-views/${id}`),
}

// ---------------------------------------------------------------------- approvals

export const approvalsApi = {
  listRules: () => get<ApprovalRule[]>('/approvals/rules'),
  createRule: (body: {
    entity_type: string
    name: string
    threshold?: string | null
    required_approver_roles?: string[]
    required_approvals?: number
    is_active?: boolean
  }) => post<ApprovalRule>('/approvals/rules', body),
  updateRule: (id: string, body: Partial<{ name: string; threshold: string | null; required_approver_roles: string[]; required_approvals: number; is_active: boolean }>) =>
    patch<ApprovalRule>(`/approvals/rules/${id}`, body),
  removeRule: (id: string) => del<void>(`/approvals/rules/${id}`),

  list: (params?: { entity_type?: string; status?: ApprovalRequestStatus }) =>
    get<ApprovalRequest[]>('/approvals', params),
  get: (id: string) => get<ApprovalRequestDetail>(`/approvals/${id}`),
  approve: (id: string, note?: string) => post<ApprovalRequest>(`/approvals/${id}/approve`, { note }),
  reject: (id: string, note?: string) => post<ApprovalRequest>(`/approvals/${id}/reject`, { note }),
}
