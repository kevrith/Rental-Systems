/** Thin typed wrappers over the API. No React, no caching — just calls. */
import { apiClient } from '@/lib/api-client'

import type {
  ActivityEntry,
  AgencyDashboard,
  ArrearsReport,
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
  MaintenanceAnalytics,
  MaintenanceOverview,
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
  MeterContext,
  MeterReading,
  NotificationPreference,
  NotificationRow,
  OwnerPortalSummary,
  OwnerProfile,
  OwnerSummary,
  PaymentDetail,
  PortalHome,
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

// ---------------------------------------------------------------- tenant portal

export const portalApi = {
  home: () => get<PortalHome>('/portal/home'),
  pay: (body: { amount: string; phone_number?: string }) =>
    post<{ payment_id: string; reference_code: string; message: string }>('/portal/pay', body),
  paymentStatus: (id: string) => get<PaymentDetail>(`/portal/payments/${id}/status`),
  payments: () => get<PaymentDetail[]>('/portal/payments'),
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
