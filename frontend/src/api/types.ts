/** Shapes returned by the RentFlow API. Kept in one file so a backend schema
 *  change surfaces as a single set of TypeScript errors. */

export type UnitStatus = 'vacant' | 'occupied' | 'under_maintenance' | 'reserved' | 'vacating'
export type TenancyStatus = 'active' | 'expiring_soon' | 'expired' | 'notice_given' | 'vacated'
export type InvoiceStatus = 'pending' | 'partially_paid' | 'paid' | 'overdue' | 'cancelled'
export type PaymentStatus = 'pending' | 'confirmed' | 'failed' | 'cancelled' | 'reversed'
export type PaymentMethod = 'mpesa' | 'cash' | 'bank_transfer' | 'cheque'
export type MeterType = 'water' | 'electricity'
export type MaintenanceStatus =
  | 'submitted'
  | 'under_review'
  | 'approved'
  | 'rejected'
  | 'assigned'
  | 'in_progress'
  | 'completed'
  | 'closed'
  | 'cancelled'
export type RejectionReason =
  | 'not_landlord_responsibility'
  | 'tenant_caused_damage'
  | 'duplicate_request'
  | 'cost_not_justified'
  | 'scheduled_for_later'
  | 'other'
export type VendorSpecialty =
  | 'plumbing'
  | 'electrical'
  | 'carpentry'
  | 'painting'
  | 'masonry'
  | 'roofing'
  | 'appliance'
  | 'cleaning'
  | 'pest_control'
  | 'security'
  | 'landscaping'
  | 'general'
export type MaintenancePriority = 'emergency' | 'urgent' | 'routine'
export type MaintenanceCategory =
  | 'plumbing'
  | 'electrical'
  | 'structural'
  | 'appliance'
  | 'security'
  | 'other'
export type PropertyType =
  | 'residential'
  | 'commercial'
  | 'mixed_use'
  | 'vehicle_fleet'
  | 'equipment'
  | 'event_space'
  | 'land'

export interface Photo {
  id: string
  url: string
  filename: string
}

export type LateFeeType = 'fixed' | 'percent' | 'daily'

export interface Property {
  id: string
  organization_id: string
  reference_code: string
  name: string
  property_type: PropertyType
  address: string
  county: string | null
  sub_county: string | null
  latitude: number | null
  longitude: number | null
  description: string | null
  amenities: string[]
  water_rate_per_unit: string | null
  electricity_rate_per_unit: string | null
  grace_period_days: number
  /** Null means this property charges no late fee at all. */
  late_fee_type: LateFeeType | null
  late_fee_amount: string | null
  late_fee_cap: string | null
  /** Monthly maintenance allowance, used for budget-vs-actual reporting. */
  maintenance_budget_monthly: string | null
  is_archived: boolean
  created_at: string
}

export interface PropertySummary extends Property {
  total_units: number
  occupied_units: number
  vacant_units: number
  maintenance_units: number
  reserved_units: number
  occupancy_rate: number
  monthly_rent_potential: string
  photos: Photo[]
}

export interface Unit {
  id: string
  organization_id: string
  property_id: string
  reference_code: string
  unit_number: string
  unit_type: string | null
  size_sqm: number | null
  floor: string | null
  bedrooms: number | null
  bathrooms: number | null
  monthly_rent: string
  deposit_amount: string
  features: string[]
  status: UnitStatus
  vacancy_date: string | null
  expected_vacancy_date: string | null
  is_archived: boolean
  created_at: string
}

export interface UnitDetail extends Unit {
  property_name: string | null
  photos: Photo[]
  current_tenant_name: string | null
  current_tenancy_id: string | null
}

export interface PortfolioStats {
  total_properties: number
  total_units: number
  occupied_units: number
  vacant_units: number
  maintenance_units: number
  reserved_units: number
  vacating_units: number
  occupancy_rate: number
  monthly_rent_potential: string
  monthly_rent_contracted: string
}

export interface PortfolioDashboard {
  stats: PortfolioStats
  properties: PropertySummary[]
}

export interface Tenant {
  id: string
  organization_id: string
  reference_code: string
  full_name: string
  phone_number: string
  email: string | null
  national_id: string | null
  employer_name: string | null
  occupation: string | null
  monthly_income: string | null
  emergency_contact_name: string | null
  emergency_contact_phone: string | null
  emergency_contact_relationship: string | null
  notes: string | null
  id_photo_front_id: string | null
  id_photo_back_id: string | null
  passport_photo_id: string | null
  portal_user_id: string | null
  is_archived: boolean
  created_at: string
}

export interface TenantListItem extends Tenant {
  unit_number: string | null
  property_name: string | null
  tenancy_id: string | null
  tenancy_status: TenancyStatus | null
  monthly_rent: string | null
  lease_end_date: string | null
  balance: string
  payment_status: string
}

export interface Tenancy {
  id: string
  organization_id: string
  reference_code: string
  tenant_id: string
  unit_id: string
  start_date: string
  end_date: string | null
  is_open_ended: boolean
  monthly_rent: string
  deposit_amount: string
  billing_day: number
  notice_period_days: number
  payment_method: string
  status: TenancyStatus
  notice_given_at: string | null
  move_out_date: string | null
  vacated_at: string | null
  lease_document_id: string | null
  created_at: string
}

export interface TenancyDetail extends Tenancy {
  tenant_name: string | null
  tenant_phone: string | null
  unit_number: string | null
  property_name: string | null
  property_id: string | null
  lease_url: string | null
  days_to_expiry: number | null
  balance: string
}

export interface LineItem {
  id: string
  kind: string
  description: string
  quantity: string
  unit_amount: string
  amount: string
}

export interface Invoice {
  id: string
  organization_id: string
  reference_code: string
  tenancy_id: string
  period_start: string
  period_end: string
  issue_date: string
  due_date: string
  total: string
  amount_paid: string
  status: InvoiceStatus
  document_id: string | null
  created_at: string
}

export interface InvoiceDetail extends Invoice {
  balance: string
  line_items: LineItem[]
  tenant_name: string | null
  unit_number: string | null
  property_name: string | null
  document_url: string | null
}

export interface Receipt {
  id: string
  reference_code: string
  issued_at: string
  signature: string
  balance_after: string
  document_id: string | null
}

export interface Payment {
  id: string
  organization_id: string
  reference_code: string
  tenancy_id: string
  invoice_id: string | null
  amount: string
  method: PaymentMethod
  status: PaymentStatus
  mpesa_receipt: string | null
  phone_number: string | null
  failure_reason: string | null
  paid_at: string | null
  payment_date: string | null
  notes: string | null
  created_at: string
}

export interface PaymentDetail extends Payment {
  tenant_name: string | null
  unit_number: string | null
  property_name: string | null
  receipt: Receipt | null
  receipt_url: string | null
  recorded_by_name: string | null
}

export interface AgingBuckets {
  current: string
  days_1_30: string
  days_31_60: string
  days_61_90: string
  days_90_plus: string
}

export interface ArrearsRow {
  tenant_id: string
  tenant_name: string
  tenant_phone: string
  tenancy_id: string
  tenancy_reference: string
  unit_number: string
  property_id: string
  property_name: string
  amount_owed: string
  days_overdue: number
  bucket: string
  oldest_due_date: string | null
  last_payment_date: string | null
  invoice_count: number
  aging: AgingBuckets
}

export interface ArrearsReport {
  total_arrears: string
  tenants_in_arrears: number
  aging: AgingBuckets
  rows: ArrearsRow[]
}

export interface MonthPoint {
  month: string
  expected: string
  collected: string
}

export interface Defaulter {
  tenant_id: string
  tenant_name: string
  tenancy_id: string
  unit_number: string
  property_name: string
  amount_owed: string
  days_overdue: number
}

export interface RecentPayment {
  id: string
  reference_code: string
  amount: string
  method: string
  paid_at: string | null
  tenant_name: string
  unit_number: string
  property_name: string
}

export interface FinancialDashboard {
  expected_rent: string
  collected: string
  collection_rate: number
  total_arrears: string
  tenants_in_arrears: number
  occupancy_rate: number
  total_units: number
  occupied_units: number
  vacant_units: number
  total_properties: number
  monthly_chart: MonthPoint[]
  top_defaulters: Defaulter[]
  recent_payments: RecentPayment[]
  aging: AgingBuckets
  attention: {
    vacant: number
    under_maintenance: number
    vacating: number
    leases_expiring: number
  }
}

export interface MeterContext {
  unit_id: string
  unit_number: string
  property_name: string
  meter_type: MeterType
  previous_reading: string
  previous_reading_date: string | null
  rate: string
  has_rate_configured: boolean
}

export interface MeterReading {
  id: string
  organization_id: string
  unit_id: string
  meter_type: MeterType
  previous_reading: string
  current_reading: string
  consumption: string
  rate: string
  amount: string
  reading_date: string
  photo_file_id: string | null
  billed_invoice_id: string | null
  notes: string | null
  created_at: string
  unit_number?: string | null
  property_name?: string | null
  photo_url?: string | null
  recorded_by_name?: string | null
}

export interface VendorSummary {
  id: string
  name: string
  phone_number: string
  average_rating: number | null
  jobs_completed: number
}

export interface MaintenanceTimelineEntry {
  action: string
  summary: string
  actor_name: string | null
  occurred_at: string
}

export interface MaintenanceRequest {
  id: string
  organization_id: string
  reference_code: string
  unit_id: string
  tenancy_id: string | null
  title: string
  description: string
  category: MaintenanceCategory
  priority: MaintenancePriority
  status: MaintenanceStatus
  photo_file_ids: string[]
  resolution_notes: string | null
  cost: string | null
  estimated_cost: string | null
  acknowledged_at: string | null
  completed_at: string | null
  created_at: string

  // Lifecycle (Sprint 13)
  vendor_id: string | null
  expected_completion_date: string | null
  is_overdue: boolean
  approved_at: string | null
  reviewed_at: string | null
  assigned_at: string | null
  started_at: string | null
  closed_at: string | null
  rejection_reason: RejectionReason | null
  rejection_note: string | null
  info_requested: string | null
  vendor_rating: number | null
  vendor_review: string | null
  tenant_rating: number | null
  tenant_feedback: string | null
  owner_expense_allocated: boolean

  unit_number?: string | null
  property_name?: string | null
  property_id?: string | null
  reported_by_name?: string | null
  approved_by_name?: string | null
  photo_urls?: string[]
  vendor?: VendorSummary | null
  cost_variance?: string | null
  days_open?: number | null
  timeline?: MaintenanceTimelineEntry[]
}

export interface VacateNotice {
  id: string
  organization_id: string
  tenancy_id: string
  move_out_date: string
  reason: string | null
  notice_days_given: number
  meets_notice_period: boolean
  status: string
  acknowledged_at: string | null
  document_id: string | null
  created_at: string
  tenant_name?: string | null
  unit_number?: string | null
  property_name?: string | null
  required_notice_days?: number
  document_url?: string | null
}

export interface ActivityEntry {
  id: string
  action: string
  entity_type: string
  entity_id: string | null
  summary: string | null
  actor_name: string | null
  user_id: string | null
  created_at: string
  gps_latitude: number | null
  gps_longitude: number | null
}

export interface CaretakerTaskList {
  readings_due: MeterContext[]
  open_maintenance: MaintenanceRequest[]
  units_vacant: number
  tenants_in_arrears: number
  recent_activity: ActivityEntry[]
}

export interface TeamMember {
  id: string
  full_name: string
  email: string
  phone_number: string
  role: string
  is_active: boolean
  is_phone_verified: boolean
  last_login_at: string | null
  assigned_property_ids: string[]
  cash_limit: number | null
}

export interface Invitation {
  id: string
  full_name: string
  phone_number: string
  email: string | null
  role: string
  status: string
  property_ids: string[]
  expires_at: string
  created_at: string
}

export interface SessionRow {
  id: string
  device_name: string
  ip_address: string | null
  location: string | null
  last_active_at: string
  created_at: string
  expires_at: string
  is_current: boolean
}

export interface NotificationRow {
  id: string
  channel: string
  notification_type: string
  title: string
  body: string
  link_path: string | null
  status: string
  error: string | null
  sent_at: string | null
  read_at: string | null
  created_at: string
  entity_type: string | null
  entity_id: string | null
}

export interface NotificationPreference {
  notification_type: string
  channel: string
  enabled: boolean
}

export interface StoredDocument {
  id: string
  filename: string
  category: string
  size_bytes?: number
  created_at: string
  url: string
}

export interface LeaseTemplate {
  id: string
  name: string
  body_html: string
  is_default: boolean
  version: number
  logo_file_id: string | null
  letterhead_text: string | null
  created_at: string
}

export interface PortalHome {
  tenant_id: string
  full_name: string
  reference_code: string
  phone_number: string
  tenancy_id: string | null
  tenancy_reference: string | null
  property_name: string | null
  unit_number: string | null
  monthly_rent: string | null
  balance: string
  next_due_date: string | null
  lease_end_date: string | null
  lease_document_id: string | null
  organization_name: string
}

// ------------------------------------------------------------- agency mode (Phase 2)

export interface OwnerProfile {
  id: string
  organization_id: string
  reference_code: string
  full_name: string
  phone_number: string
  email: string | null
  national_id: string | null
  kra_pin: string | null
  bank_name: string | null
  bank_account_number: string | null
  bank_account_name: string | null
  mpesa_phone: string | null
  management_fee_percent: string
  disbursement_day: number
  maintenance_auto_approve_limit: string
  maintenance_notify_limit: string
  portal_user_id: string | null
  portal_invited_at: string | null
  is_active: boolean
  notes: string | null
  created_at: string
}

export type DisbursementStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'processing'
  | 'completed'
  | 'failed'

export interface Disbursement {
  id: string
  organization_id: string
  reference_code: string
  owner_profile_id: string
  period_start: string
  period_end: string
  gross_rent: string
  management_fee: string
  maintenance_costs: string
  other_deductions: string
  net_amount: string
  status: DisbursementStatus
  payment_method: string | null
  payment_reference: string | null
  paid_at: string | null
  failure_reason: string | null
  statement_document_id: string | null
  approved_by_id: string | null
  approved_at: string | null
  rejection_reason: string | null
  payout_conversation_id: string | null
  payout_requested_at: string | null
  notes: string | null
  created_at: string
}

/** A signed, short-lived link to a rendered owner statement PDF. */
export interface DisbursementStatement {
  disbursement_id: string
  document_id: string
  filename: string
  url: string
}

/** Preview of what an owner is owed for a period, before a disbursement exists. */
export interface DisbursementPreview {
  owner_profile_id: string
  owner_name: string
  gross_rent: number
  management_fee: number
  maintenance_costs: number
  other_deductions: number
  net_amount: number
  payment_count: number
}

export interface AgencyDashboard {
  total_properties: number
  total_units: number
  occupied_units: number
  occupancy_rate: number
  collected_this_month: string
  pending_disbursements: number
  management_fees_this_month: string
  owner_count: number
}

/** One card on the agency dashboard — a single owner client at a glance. */
export interface OwnerSummary {
  owner_profile_id: string
  reference_code: string
  full_name: string
  phone_number: string
  email: string | null
  management_fee_percent: number
  disbursement_day: number
  portal_invited: boolean
  property_count: number
  unit_count: number
  occupied_units: number
  occupancy_rate: number
  collected_this_month: number
  billed_this_month: number
  collection_rate: number
  arrears: number
  last_disbursement: {
    id: string
    reference_code: string
    status: DisbursementStatus
    net_amount: number
    period_start: string
    period_end: string
    paid_at: string | null
  } | null
}

/** Read-only view an owner sees of their own properties inside an agency account. */
export interface OwnerPortalSummary {
  owner_profile: OwnerProfile
  properties: PropertySummary[]
  total_units: number
  occupied_units: number
  occupancy_rate: number
  collected_this_month: string
  recent_disbursements: Disbursement[]
}


// ------------------------------------------------------- document vault (Phase 2)

/** One document in a vault, with a signed URL valid for 60 minutes. */
export interface VaultDocument {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  category: string
  tags: string[]
  description: string | null
  version: number
  supersedes_id: string | null
  entity_type: string | null
  entity_id: string | null
  is_archived: boolean
  uploaded_at: string
  url: string
}

export interface VaultSection {
  category: string
  count: number
  documents: VaultDocument[]
}

export interface TenantVault {
  tenant_id: string
  tenant_name: string
  reference_code: string
  document_count: number
  total_bytes: number
  sections: VaultSection[]
}

export interface PropertyVault {
  property_id: string
  property_name: string
  reference_code: string
  unit_count: number
  document_count: number
  total_bytes: number
  sections: VaultSection[]
}

export interface VaultUsage {
  total_documents: number
  total_bytes: number
  by_category: { category: string; document_count: number; bytes: number }[]
}

export interface VaultCategories {
  uploadable: string[]
  tenant_order: string[]
  property_order: string[]
}

export interface DocumentDelivery {
  document_id: string
  filename: string
  recipient: string | null
  status: string
  error: string | null
}

/** The starter lease body plus every placeholder a template may reference. */
export interface LeaseTemplateStarter {
  body_html: string
  variables: string[]
  sample_values: Record<string, string | number>
}


// ---------------------------------------------------------- inspections (Phase 2)

export type InspectionKind = 'move_in' | 'move_out' | 'routine'
export type RoomCondition = 'excellent' | 'good' | 'fair' | 'poor'

export interface InspectionPhoto {
  id: string
  filename: string
  url: string
}

export interface InspectionRoom {
  name: string
  condition: RoomCondition | null
  notes: string | null
  photo_file_ids: string[]
  /** Present on hydrated reads — the ids above resolved to signed URLs. */
  photos?: InspectionPhoto[]
}

export interface InspectionSummary {
  id: string
  reference_code: string
  unit_id: string
  tenancy_id: string | null
  inspection_type: InspectionKind
  status: 'draft' | 'submitted'
  rooms_data: InspectionRoom[]
  inspector_name: string | null
  submitted_at: string | null
  notes: string | null
  deposit_deduction: string | null
  tenant_acknowledged: boolean
  created_at: string
}

export interface InspectionDetail extends InspectionSummary {
  rooms: InspectionRoom[]
  gps_latitude: number | null
  gps_longitude: number | null
  move_in_report_id: string | null
  deduction_notes: string | null
}

export type RoomChange = 'unchanged' | 'worse' | 'better' | 'not_inspected'

export interface ComparisonRow {
  name: string
  before: InspectionRoom | null
  after: InspectionRoom | null
  change: RoomChange
}

export interface InspectionComparison {
  move_out: {
    id: string
    reference_code: string
    submitted_at: string | null
    inspector_name: string | null
    notes: string | null
  }
  move_in: InspectionComparison['move_out'] | null
  unit_number: string
  tenant_name: string | null
  deposit_held: string | null
  deposit_deduction: string | null
  deduction_notes: string | null
  rooms_degraded: number
  rooms: ComparisonRow[]
}

export interface ComplianceRow {
  tenancy_id: string
  tenancy_reference: string
  unit_id: string
  unit_number: string
  property_id: string | null
  property_name: string
  tenant_name: string
  start_date: string
  last_inspected_at?: string | null
}

export interface InspectionCompliance {
  total_active_tenancies: number
  missing_move_in_inspection: number
  overdue_routine_inspection: number
  coverage_percent: number
  missing_move_in: ComplianceRow[]
  overdue_routine: ComplianceRow[]
}

export interface InspectionDocuments {
  report: InspectionPhoto | null
  comparison: InspectionPhoto | null
}


// --------------------------------------------------------- analytics (Phase 2)

export interface RevenuePoint {
  month: string
  month_start: string
  collected: number
  expected: number
  collection_rate: number
}

export interface PropertyPerformance {
  property_id: string
  property_name: string
  total_units: number
  occupied_units: number
  occupancy_rate: number
  collected_this_month: number
  expected_this_month: number
  collection_rate: number
  total_maintenance_cost: number
}

export interface CashFlowPoint {
  month: string
  projected_income: number
  collection_rate_assumption: number
  active_rent_roll: number
}

export interface ExpiringLeases {
  expiring_in_30_days: number
  expiring_in_60_days: number
  expiring_in_90_days: number
}

export interface MaintenanceAnalytics {
  this_month_cost: number
  avg_monthly_cost_3m: number
  spike_alert: boolean
}

// -------------------------------------------------------------- eTIMS (Phase 2)

export interface EtimsCredentials {
  configured: boolean
  kra_pin?: string
  branch_id?: string
  environment?: 'sandbox' | 'production'
  is_active?: boolean
  device_serial_hint?: string | null
  last_verified_at?: string | null
  last_error?: string | null
}

export interface EtimsFailure {
  submission_id: string
  receipt_reference: string | null
  status: 'pending' | 'submitted' | 'failed' | 'abandoned'
  attempts: number
  last_error: string | null
  next_attempt_at: string | null
}

export interface EtimsReport {
  total: number
  submitted: number
  pending: number
  failed: number
  abandoned: number
  success_rate: number
  recent_failures: EtimsFailure[]
}

/** A demand letter that has just been issued and filed. */
export interface DemandLetter {
  reference_code: string
  escalation: string
  total_owed: string
  days_overdue: number
  deadline: string
  document_id: string
  filename: string
  url: string
}


// ------------------------------------------------ scheduled tasks (Phase 2)

export type TaskHealth = 'healthy' | 'failing' | 'broken' | 'never_run'

export interface TaskRun {
  id: string
  task_name: string
  status: 'running' | 'succeeded' | 'failed'
  started_at: string
  finished_at: string | null
  duration_seconds: number | null
  result: Record<string, unknown> | null
  error: string | null
  triggered_manually: boolean
}

export interface ScheduledTask {
  task_name: string
  scheduled: boolean
  schedule: string | null
  last_status: 'running' | 'succeeded' | 'failed' | null
  last_run_at: string | null
  last_duration_seconds: number | null
  last_result: Record<string, unknown> | null
  last_error: string | null
  runs_7d: number
  failures_7d: number
  health: TaskHealth
}

export interface TaskOverview {
  tasks: ScheduledTask[]
  healthy: number
  failing: number
  never_run: number
  recent_runs: TaskRun[]
}

// -------------------------------------------- caretaker performance (Phase 2)

export type PerformanceBand = 'good' | 'watch' | 'poor' | 'no_data'

export interface CaretakerMetrics {
  meter_compliance: number | null
  inspection_completion: number | null
  maintenance_response: number | null
  cash_discipline: number | null
}

export interface CaretakerScore {
  user_id: string
  full_name: string
  phone_number: string | null
  last_login_at: string | null
  property_count: number
  unit_count: number
  window_days: number
  score: number | null
  band: PerformanceBand
  metrics: CaretakerMetrics
  detail: {
    readings_due: number
    readings_taken: number
    inspections_started: number
    inspections_submitted: number
    maintenance_requests: number
    average_response_hours: number | null
    cash_collected: number
    traceable_collected: number
  }
}

export interface CaretakerScoreDetail extends CaretakerScore {
  trend: {
    month: string
    score: number | null
    meter_compliance: number | null
    maintenance_response: number | null
  }[]
  properties: { id: string; name: string }[]
}

export interface CaretakerOpenJob {
  id: string
  reference_code: string
  title: string
  priority: string
  created_at: string
  hours_open: number
}

// ------------------------------------------------ lease renewals (Phase 2)

export type RenewalStatus = 'offered' | 'accepted' | 'declined' | 'lapsed'

export interface LeaseRenewal {
  id: string
  reference_code: string
  tenancy_id: string
  tenant_name: string | null
  unit_number: string | null
  status: RenewalStatus
  current_rent: string
  proposed_rent: string
  rent_increase_percent: string
  new_start_date: string
  new_end_date: string
  respond_by: string
  responded_at: string | null
  decline_reason: string | null
  escalated_at: string | null
  document_id: string | null
}

/** What the tenant sees on the public renewal link — no account required. */
export interface RenewalOffer {
  reference_code: string
  status: RenewalStatus
  tenant_name: string | null
  landlord_name: string | null
  unit_number: string | null
  property_name: string | null
  current_rent: string
  proposed_rent: string
  rent_increase_percent: string
  term_months: number
  current_end_date: string | null
  new_start_date: string
  new_end_date: string
  respond_by: string
  agreement_url: string | null
}

export interface ProposedTerms {
  current_rent: string
  proposed_rent: string
  rent_increase_percent: string
  term_months: number
  new_start_date: string
  new_end_date: string
}

// ------------------------------------------------------ vendors (Phase 3)

export interface Vendor {
  id: string
  organization_id: string
  name: string
  company_name: string | null
  specialties: VendorSpecialty[]
  phone_number: string
  email: string | null
  rate_notes: string | null
  notes: string | null
  is_active: boolean
  jobs_completed: number
  rating_count: number
  total_billed: string
  average_rating: number | null
  average_job_cost: string
  created_at: string
}

export interface VendorJobSummary {
  id: string
  reference_code: string
  title: string
  status: MaintenanceStatus
  completed_at: string | null
  cost: string | null
  rating: number | null
  property_name: string | null
  unit_number: string | null
}

export interface VendorDetail extends Vendor {
  open_jobs: number
  recent_jobs: VendorJobSummary[]
}

export interface MaintenancePropertyCost {
  property_id: string
  property_name: string
  jobs: number
  total_cost: number
  this_month_cost: number
  average_monthly_cost: number
  monthly_budget: number | null
  budget_variance: number | null
  over_budget: boolean
}

export interface MaintenanceCategoryCost {
  category: MaintenanceCategory
  jobs: number
  total_cost: number
  average_cost: number
}

export interface MaintenanceUnitCost {
  unit_id: string
  unit_number: string
  property_name: string
  monthly_rent: number
  total_cost: number
  jobs: number
  cost_to_rent_percent: number | null
  needs_attention: boolean
}

export interface MaintenanceVendorStat {
  vendor_id: string
  name: string
  specialties: VendorSpecialty[]
  jobs_completed: number
  total_billed: number
  average_cost: number
  average_rating: number | null
  is_active: boolean
}

export interface MaintenanceMonthPoint {
  month: string
  total_cost: number
  jobs: number
}

export interface MaintenanceOverview {
  window_months: number
  open_jobs: number
  awaiting_approval: number
  overdue_jobs: number
  this_month_cost: number
  window_cost: number
  average_monthly_cost: number
  monthly_budget: number | null
  budget_used_percent: number | null
  average_completion_days: number | null
  spike_alert: boolean
  by_property: MaintenancePropertyCost[]
  by_category: MaintenanceCategoryCost[]
  expensive_units: MaintenanceUnitCost[]
  top_vendors: MaintenanceVendorStat[]
  monthly_trend: MaintenanceMonthPoint[]
}
