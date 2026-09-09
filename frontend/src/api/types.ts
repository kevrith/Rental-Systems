/** Shapes returned by the RentFlow API. Kept in one file so a backend schema
 *  change surfaces as a single set of TypeScript errors. */

export type UnitStatus = 'vacant' | 'occupied' | 'under_maintenance' | 'reserved' | 'vacating'
export type TenancyStatus = 'active' | 'expiring_soon' | 'expired' | 'notice_given' | 'vacated'
export type InvoiceStatus = 'pending' | 'partially_paid' | 'paid' | 'overdue' | 'cancelled'
export type PaymentStatus = 'pending' | 'confirmed' | 'failed' | 'cancelled' | 'reversed'
export type PaymentMethod = 'mpesa' | 'cash' | 'bank_transfer' | 'cheque' | 'card'
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
  /** Commercial lettings; `size_sqm` above is the floor area. */
  use_class: UseClass | null
  car_bays: number
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
  erased_at: string | null
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
  bank_reference: string | null
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

export interface VisitorLog {
  id: string
  organization_id: string
  property_id: string
  unit_id: string
  visitor_name: string
  visitor_phone: string | null
  purpose: string | null
  checked_in_at: string
  checked_out_at: string | null
  created_at: string
  unit_number?: string | null
  property_name?: string | null
  recorded_by_name?: string | null
}

export interface CoTenant {
  id: string
  tenancy_id: string
  tenant_id: string
  created_at: string
  tenant_name: string | null
  tenant_phone: string | null
}

export interface DataRequest {
  id: string
  tenant_id: string
  request_type: 'export' | 'erasure'
  status: 'completed' | 'failed'
  resolution_notes: string | null
  resolved_at: string | null
  created_at: string
  tenant_name?: string | null
  export_url?: string | null
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
  auto_disburse_daily: boolean
  auto_disburse_minimum: string
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
  limit_bytes: number | null
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

// ------------------------------------------------------- predictive (Sprint 21)

export interface VacancyRiskItem {
  tenancy_id: string
  tenant_name: string
  property_name: string
  unit_number: string
  end_date: string
  days_until_expiry: number
  monthly_rent: number
  renewal_state: 'none' | 'declined' | 'lapsed'
}

export interface RentReviewSuggestion {
  tenancy_id: string
  tenant_name: string
  property_name: string
  unit_number: string
  monthly_rent: number
  months_since_last_change: number
  last_change_date: string
  portfolio_avg_rent_same_type: number
  percent_vs_portfolio_average: number
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

// ------------------------------------------- tenant screening (Sprint 14)

export type ApplicationStatus =
  | 'submitted'
  | 'under_review'
  | 'interview_scheduled'
  | 'approved'
  | 'rejected'
  | 'withdrawn'
export type EmploymentStatus =
  | 'employed'
  | 'self_employed'
  | 'business_owner'
  | 'student'
  | 'retired'
  | 'unemployed'
export type ApplicationRejectionReason =
  | 'insufficient_income'
  | 'failed_reference_check'
  | 'incomplete_application'
  | 'no_guarantor'
  | 'unit_taken'
  | 'other'
export type GuarantorStatus = 'pending' | 'acknowledged' | 'declined' | 'expired'
export type ReferenceStatus = 'sent' | 'positive' | 'negative' | 'no_response'
export type ScoreBand = 'green' | 'amber' | 'red'

export interface ScoreComponent {
  label: string
  points: number
  max: number
  note: string
}

export interface ScoreBreakdown {
  score: number
  band: ScoreBand
  income_ratio: number | null
  income_ratio_exceeded: boolean
  employment_status: EmploymentStatus
  monthly_rent: number
  components: ScoreComponent[]
}

export interface GuarantorRow {
  id: string
  full_name: string
  relationship_to_applicant: string
  phone_number: string
  email: string | null
  national_id: string | null
  employer_name: string | null
  occupation: string | null
  monthly_income: string | null
  status: GuarantorStatus
  acknowledged_at: string | null
  declined_reason: string | null
  signature_id: string | null
  id_document_url: string | null
}

export interface ReferenceCheckRow {
  id: string
  landlord_name: string
  landlord_phone: string
  property_reference: string | null
  status: ReferenceStatus
  sent_at: string
  responded_at: string | null
  paid_on_time: boolean | null
  would_rent_again: boolean | null
  response_note: string | null
}

export interface TenantApplication {
  id: string
  organization_id: string
  reference_code: string
  unit_id: string

  full_name: string
  phone_number: string
  email: string | null
  national_id: string | null
  date_of_birth: string | null

  current_address: string | null
  current_landlord_name: string | null
  current_landlord_phone: string | null
  years_at_current_address: string | null
  reason_for_moving: string | null

  employment_status: EmploymentStatus
  employer_name: string | null
  employer_phone: string | null
  job_title: string | null
  monthly_income: string | null
  months_in_employment: number | null

  occupants: number
  intended_move_in: string | null
  notes: string | null

  score: number
  score_breakdown: ScoreBreakdown
  status: ApplicationStatus
  reviewed_at: string | null
  interview_at: string | null
  interview_notes: string | null
  decided_at: string | null
  rejection_reason: ApplicationRejectionReason | null
  decision_note: string | null
  tenant_id: string | null
  tenancy_id: string | null
  submitted_online: boolean
  created_at: string

  unit_number: string | null
  property_name: string | null
  property_id: string | null
  monthly_rent: string | null
  decided_by_name: string | null
  band: ScoreBand
  id_document_url: string | null
  passport_photo_url: string | null
  payslip_urls: string[]
  guarantors: GuarantorRow[]
  references: ReferenceCheckRow[]
}

export interface ScreeningSummary {
  open: number
  awaiting_review: number
  approved: number
  rejected: number
  last_30_days: number
  awaiting_guarantor: number
  awaiting_reference: number
}

export interface WaitingListEntry {
  rank: number
  application_id: string
  reference_code: string
  full_name: string
  phone_number: string
  score: number
  band: ScoreBand
  status: ApplicationStatus
  applied_at: string
}

export interface PublicUnitListing {
  unit_id: string
  unit_number: string
  property_name: string
  property_address: string
  monthly_rent: string
  deposit_amount: string
  bedrooms: number | null
  unit_type: string | null
  description: string | null
  photo_urls: string[]
  accepting_applications: boolean
}

export interface GuarantorInvite {
  guarantor_name: string
  applicant_name: string
  relationship_to_applicant: string
  unit_number: string
  property_name: string
  monthly_rent: string
  status: GuarantorStatus
  already_answered: boolean
}

export interface ReferenceInvite {
  landlord_name: string
  applicant_name: string
  property_reference: string | null
  already_answered: boolean
}

// ------------------------------- service charges & bulk ops (Sprint 15)

export type UseClass =
  | 'office'
  | 'retail'
  | 'warehouse'
  | 'industrial'
  | 'restaurant'
  | 'medical'
  | 'other'
export type Apportionment = 'fixed_per_unit' | 'by_floor_area' | 'by_occupied_unit'
export type ServiceChargeCategory =
  | 'security'
  | 'cleaning'
  | 'common_area_maintenance'
  | 'generator'
  | 'lift'
  | 'water'
  | 'landscaping'
  | 'insurance'
  | 'management'
  | 'other'
export type SinkingFundMovement = 'contribution' | 'withdrawal'

export interface BudgetLine {
  category: ServiceChargeCategory
  monthly_budget: string
  notes: string | null
}

export interface UnitCharge {
  unit_id: string
  unit_number: string
  size_sqm: number | null
  occupied: boolean
  monthly_charge: number
}

export interface ServiceChargeScheme {
  id: string
  organization_id: string
  property_id: string
  name: string
  apportionment: Apportionment
  fixed_amount: string
  monthly_pool: string
  sinking_fund_percent: string
  is_active: boolean
  bill_with_rent: boolean
  notes: string | null
  created_at: string
  property_name: string | null
  budgets: BudgetLine[]
  monthly_total: number
  sinking_fund_balance: number
  units: UnitCharge[]
}

export interface ServiceChargeExpense {
  id: string
  category: ServiceChargeCategory
  amount: string
  incurred_on: string
  description: string
  vendor_id: string | null
  receipt_file_id: string | null
  created_at: string
}

export interface SinkingFundEntry {
  id: string
  movement: SinkingFundMovement
  amount: string
  entry_date: string
  description: string
  billing_period: string | null
  created_at: string
}

export interface ReconciliationLine {
  category: ServiceChargeCategory
  budgeted: number
  spent: number
  variance: number
  over_budget: boolean
}

export interface ServiceChargeReconciliation {
  scheme_id: string
  property_name: string | null
  period_start: string
  period_end: string
  months: number
  total_budgeted: number
  total_charged: number
  total_spent: number
  surplus_or_deficit: number
  sinking_fund_balance: number
  lines: ReconciliationLine[]
}

export type BulkOperationKind =
  | 'rent_increase'
  | 'payment_reminder'
  | 'announcement'
  | 'generate_invoices'
  | 'renewal_notices'
  | 'document_distribution'
  | 'tenant_import'
export type BulkOperationStatus =
  | 'previewed'
  | 'running'
  | 'completed'
  | 'partial'
  | 'failed'
  | 'cancelled'

export interface BulkTarget {
  tenancy_id: string
  tenant_id: string
  tenant_name: string
  phone_number: string
  unit_id: string
  unit_number: string
  property_name: string
  current_rent: number
  new_rent?: number
  increase?: number
  increase_percent?: number | null
}

export interface BulkFailure {
  tenant_name: string | null
  unit_number: string | null
  reason: string
}

export interface BulkOperation {
  id: string
  organization_id: string
  kind: BulkOperationKind
  status: BulkOperationStatus
  parameters: Record<string, unknown>
  targets: BulkTarget[]
  total: number
  succeeded: number
  failed: number
  failures: BulkFailure[]
  property_id: string | null
  effective_date: string | null
  started_at: string | null
  finished_at: string | null
  summary: string | null
  error: string | null
  created_at: string
}

export interface ImportRow {
  row: number
  full_name: string
  phone_number: string
  email: string | null
  national_id: string | null
  property_name: string
  unit_number: string
  monthly_rent: string
  deposit_amount: string
  start_date: string
  end_date: string | null
  billing_day: number
  opening_balance: string
  notes: string | null
  property_id: string
  unit_exists: boolean
  unit_id: string | null
}

export interface ImportPreview {
  ready: ImportRow[]
  errors: { row: number; reason: string }[]
  total_rows: number
  ready_count: number
  error_count: number
}

export interface ImportResult {
  created: number
  failed: number
  failures: { row: number; reason: string }[]
}

// ----------------------------- vacancy marketing & export (Sprint 16)

export type ListingStatus = 'draft' | 'published' | 'closed'
export type LeadStage =
  | 'inquired'
  | 'applied'
  | 'under_review'
  | 'approved'
  | 'rejected'
  | 'lost'
export type ExportKind =
  | 'tenants'
  | 'tenancies'
  | 'payments'
  | 'properties'
  | 'units'
  | 'invoices'
export type ExportFormat = 'csv' | 'excel'

export interface VacancyListingRow {
  id: string
  organization_id: string
  unit_id: string
  slug: string
  headline: string | null
  description: string | null
  contact_name: string | null
  contact_phone: string | null
  status: ListingStatus
  vacant_since: string | null
  published_at: string | null
  closed_at: string | null
  view_count: number
  days_vacant: number | null
  created_at: string
}

export interface PublicListing {
  slug: string
  unit_id: string
  unit_number: string
  unit_type: string | null
  bedrooms: number | null
  bathrooms: number | null
  size_sqm: number | null
  features: string[]
  monthly_rent: number
  deposit_amount: number
  headline: string | null
  description: string | null
  property_name: string
  property_address: string
  county: string | null
  latitude: number | null
  longitude: number | null
  amenities: string[]
  contact_name: string | null
  contact_phone: string | null
  photo_urls: string[]
}

export interface InquiryRow {
  id: string
  unit_id: string
  full_name: string
  phone_number: string
  email: string | null
  message: string | null
  stage: LeadStage
  application_id: string | null
  last_contacted_at: string | null
  notes: string | null
  is_stale: boolean
  created_at: string
  unit_number: string | null
  property_name: string | null
}

export interface VacancyRow {
  unit_id: string
  unit_number: string
  property_name: string
  status: string
  monthly_rent: number
  vacant_since: string | null
  days_vacant: number | null
  revenue_lost: number
  listing_slug: string | null
  listing_status: string | null
  views: number
  open_leads: number
  applications: number
}

export interface VacancyReport {
  vacant_units: number
  total_revenue_lost: number
  monthly_revenue_at_risk: number
  units: VacancyRow[]
}

export interface ConversionReport {
  inquiries: number
  applications: number
  approvals: number
  stale_leads: number
  inquiry_to_application_percent: number | null
  application_to_approval_percent: number | null
}

export interface DataExportRow {
  id: string
  kind: ExportKind
  export_format: ExportFormat
  date_from: string | null
  date_to: string | null
  row_count: number
  file_id: string | null
  is_scheduled: boolean
  error: string | null
  created_at: string
  download_url: string | null
  requested_by_name: string | null
}

// ------------------------------------------ facilities (Sprint 17)

export type ComplianceType =
  | 'fire_safety'
  | 'health_inspection'
  | 'nema'
  | 'lift_inspection'
  | 'electrical_inspection'
  | 'water_safety'
  | 'insurance'
  | 'business_permit'
  | 'structural_survey'
  | 'other'
export type ComplianceStatus = 'valid' | 'expiring_soon' | 'expired' | 'missing'
export type BayType = 'covered' | 'open' | 'reserved' | 'visitor' | 'disabled'
export type AmenityKind =
  | 'gym'
  | 'meeting_room'
  | 'rooftop'
  | 'pool'
  | 'clubhouse'
  | 'playground'
  | 'laundry'
  | 'other'
export type BookingStatus = 'confirmed' | 'cancelled' | 'blocked'
export type UtilityAccountType = 'kplc' | 'water' | 'internet' | 'garbage' | 'other'
export type UtilityPaymentStatus = 'paid' | 'unpaid' | 'unknown'

export interface ComplianceItem {
  id: string
  property_id: string
  compliance_type: ComplianceType
  name: string
  reference_number: string | null
  issued_on: string | null
  expires_on: string | null
  issuing_authority: string | null
  responsible_party: string | null
  responsible_phone: string | null
  document_id: string | null
  insurer_name: string | null
  insurer_contact: string | null
  coverage_amount: string | null
  premium_amount: string | null
  premium_due_on: string | null
  notes: string | null
  status: ComplianceStatus
  days_until_expiry: number | null
  created_at: string
  property_name: string | null
  document_url: string | null
}

export interface CompliancePropertyRow {
  property_id: string
  property_name: string
  worst: ComplianceStatus
  items: {
    id: string
    name: string
    type: ComplianceType
    expires_on: string | null
    days_until_expiry: number | null
    status: ComplianceStatus
  }[]
}

export interface ComplianceDashboard {
  total_items: number
  counts: Record<ComplianceStatus, number>
  needs_attention: number
  properties: CompliancePropertyRow[]
}

export interface BayRow {
  bay_id: string
  bay_number: string
  bay_type: BayType
  level: string | null
  monthly_fee: number
  is_active: boolean
  allocation_id: string | null
  holder: string | null
  vehicle_registration: string | null
  allocated_until: string | null
}

export interface ParkingOverview {
  total_bays: number
  allocated: number
  available: number
  monthly_parking_income: number
  bays: BayRow[]
}

export interface Amenity {
  id: string
  property_id: string
  name: string
  kind: AmenityKind
  description: string | null
  max_hours_per_booking: number
  min_notice_hours: number
  max_bookings_per_week: number
  opens_at_hour: number
  closes_at_hour: number
  is_bookable: boolean
  booking_fee: string
  created_at: string
}

export interface AmenityBooking {
  id: string
  amenity_id: string
  tenancy_id: string | null
  tenant_id: string | null
  starts_at: string
  ends_at: string
  status: BookingStatus
  purpose: string | null
  guests: number
  created_at: string
  tenant_name: string | null
  amenity_name: string | null
}

export interface AmenityUsageRow {
  amenity_id: string
  name: string
  kind: AmenityKind
  bookings: number
  hours_booked: number
  distinct_tenants: number
}

export interface UtilityAccount {
  id: string
  property_id: string
  account_type: UtilityAccountType
  account_number: string
  account_name: string | null
  provider: string | null
  payment_status: UtilityPaymentStatus
  last_paid_on: string | null
  last_amount: string | null
  next_due_on: string | null
  status_updated_at: string | null
  notes: string | null
  is_overdue: boolean
  created_at: string
}

// ------------------------------ vehicle & equipment hire (Sprint 18)

export type AssetKind = 'vehicle' | 'equipment'
export type AssetStatus = 'available' | 'on_hire' | 'maintenance' | 'retired'
export type FuelPolicy = 'full_to_full' | 'same_to_same' | 'prepaid'
export type RateBasis = 'daily' | 'weekly' | 'monthly'
export type AgreementStatus = 'booked' | 'out' | 'returned' | 'cancelled'

export interface RentalAsset {
  id: string
  organization_id: string
  reference_code: string
  kind: AssetKind
  name: string
  property_id: string | null
  status: AssetStatus
  daily_rate: string
  weekly_rate: string | null
  monthly_rate: string | null
  deposit_amount: string
  notes: string | null
  registration_number: string | null
  make: string | null
  model: string | null
  year: number | null
  colour: string | null
  mileage: number | null
  fuel_policy: FuelPolicy
  daily_mileage_limit: number | null
  excess_mileage_rate: string | null
  insurance_expiry: string | null
  inspection_expiry: string | null
  road_licence_expiry: string | null
  serial_number: string | null
  category: string | null
  service_interval_days: number | null
  last_serviced_on: string | null
  service_due_on: string | null
  compliance_warnings: string[]
  created_at: string
  photo_urls: string[]
  current_hire: string | null
  current_hirer: string | null
}

export interface RentalAgreement {
  id: string
  organization_id: string
  reference_code: string
  asset_id: string
  tenant_id: string
  start_date: string
  end_date: string
  rate_basis: RateBasis
  rate: string
  deposit_amount: string
  deposit_refunded: string | null
  status: AgreementStatus
  checked_out_at: string | null
  mileage_out: number | null
  fuel_out_eighths: number | null
  condition_out: string | null
  checked_in_at: string | null
  mileage_in: number | null
  fuel_in_eighths: number | null
  condition_in: string | null
  hire_charge: string
  excess_mileage_charge: string
  damage_charge: string
  fuel_charge: string
  late_charge: string
  total_charge: string
  notes: string | null
  cancelled_reason: string | null
  hire_days: number
  mileage_covered: number | null
  is_overdue: boolean
  created_at: string
  asset_name: string | null
  asset_kind: AssetKind | null
  registration_number: string | null
  hirer_name: string | null
  hirer_phone: string | null
  photos_out_urls: string[]
  photos_in_urls: string[]
}

export interface AvailabilityRow {
  agreement_id: string
  reference_code: string
  start_date: string
  end_date: string
  status: AgreementStatus
  hirer: string | null
}

export interface FleetOverview {
  total_assets: number
  vehicles: number
  equipment: number
  on_hire: number
  available: number
  in_maintenance: number
  overdue_returns: number
  revenue_this_month: number
  compliance_warnings: {
    asset_id: string
    name: string
    reference_code: string
    kind: AssetKind
    warnings: string[]
  }[]
}

// --------------------------------------------------------- developer platform

export type ApiKeyScope = 'properties:read' | 'units:read' | 'tenants:read' | 'payments:read' | 'invoices:read'

export interface ApiKey {
  id: string
  name: string
  key_prefix: string
  scopes: ApiKeyScope[]
  expires_at: string | null
  last_used_at: string | null
  revoked_at: string | null
  created_at: string
}

export interface ApiKeyCreated extends ApiKey {
  api_key: string
}

export interface ApiKeyUsage {
  requests_today: number
  requests_last_7_days: number
  endpoints_hit: Record<string, number>
}

export type WebhookEvent =
  | 'payment.received'
  | 'tenant.created'
  | 'lease.signed'
  | 'inspection.completed'
  | 'maintenance.status_changed'
  | 'invoice.generated'

export interface WebhookEndpoint {
  id: string
  url: string
  description: string | null
  event_types: WebhookEvent[]
  is_active: boolean
  consecutive_failures: number
  last_triggered_at: string | null
  last_success_at: string | null
  created_at: string
}

export interface WebhookEndpointCreated extends WebhookEndpoint {
  secret: string
}

export interface WebhookDelivery {
  id: string
  event_type: string
  status: 'pending' | 'success' | 'failed'
  attempt_count: number
  response_status_code: number | null
  response_body: string | null
  delivered_at: string | null
  next_retry_at: string | null
  created_at: string
}

// ---------------------------------------------------------- customer success

export interface OnboardingProgress {
  added_property: boolean
  added_units: boolean
  invited_caretaker: boolean
  added_tenant: boolean
  setup_payment: boolean
  dismissed_at: string | null
  completed_at: string | null
}

export interface HelpArticle {
  id: string
  slug: string
  title: string
  body: string
  category: string
  is_published: boolean
  // Reading order across the whole knowledge base. Articles in a category are
  // contiguous in the numbering, so the server's ordering carries both the
  // category order and the order within it.
  sort_order: number
  // Video tutorial (Sprint 26, Module 24). `body` stays required either way:
  // text is searchable and works on a metered connection, which most of this
  // product's audience is on.
  video_url: string | null
  video_duration_seconds: number | null
  video_thumbnail_url: string | null
  video_provider: string | null
  has_video: boolean
  created_at: string
}

export interface SupportRequest {
  id: string
  subject: string
  message: string
  status: 'open' | 'resolved'
  created_at: string
}

export interface Referral {
  id: string
  referred_email: string
  status: 'pending' | 'signed_up' | 'converted'
  credit_granted_at: string | null
  created_at: string
}

export interface ReferralSummary {
  code: string
  referral_link: string
  credit_months: number
  referrals: Referral[]
}

export type NpsTrigger = 'first_payment' | 'first_inspection' | 'first_month'

export interface NpsPending {
  id: string
  trigger_event: NpsTrigger
}

export type MilestoneKey = 'payments_100' | 'tenants_50' | 'first_etims_receipt'

export interface Milestone {
  id: string
  milestone_key: MilestoneKey
  reached_at: string
  acknowledged_at: string | null
}

export interface FeatureRequest {
  id: string
  title: string
  description: string
  status: 'open' | 'planned' | 'shipped' | 'declined'
  vote_count: number
  voted_by_me: boolean
  created_at: string
}

export interface ChangelogEntry {
  id: string
  title: string
  body: string
  published_at: string
}

export type HealthTrend = 'improving' | 'declining' | 'stable'

export interface OrganizationHealthSummary {
  organization_id: string
  organization_name: string
  latest_score: number | null
  trend: HealthTrend | null
  week_of: string | null
  is_at_risk: boolean
}

export interface OrganizationHealthScorePoint {
  week_of: string
  score: number
  login_score: number
  payment_score: number
  adoption_score: number
  caretaker_score: number
  portal_score: number
  support_score: number
  trend: HealthTrend
}

// -------------------------------------------------------- reporting (Sprint 21)

export type ReportDataset = 'tenants' | 'tenancies' | 'payments' | 'properties' | 'units' | 'invoices'

export interface ReportDatasetOption {
  dataset: ReportDataset
  label: string
}

export interface ReportFieldMeta {
  key: string
  label: string
  type: 'string' | 'number' | 'date' | 'enum' | 'bool'
}

export type ReportChartType = 'table' | 'bar' | 'line' | 'pie'
export type ReportSchedule = 'none' | 'weekly' | 'monthly'
export type ReportExportFormat = 'csv' | 'excel' | 'pdf'
export type ReportDeliveryChannel = 'whatsapp' | 'email' | 'both'

export interface ReportDefinition {
  id: string
  name: string
  dataset: ReportDataset
  fields: string[]
  filters: Record<string, string[]>
  date_from: string | null
  date_to: string | null
  chart_type: ReportChartType
  group_by_field: string | null
  measure_field: string | null
  export_format: ReportExportFormat
  schedule: ReportSchedule
  schedule_day: number | null
  delivery_channels: string[]
  created_by_id: string | null
  last_run_at: string | null
  created_at: string
  updated_at: string
}

export interface ReportDefinitionInput {
  name: string
  dataset: ReportDataset
  fields: string[]
  filters?: Record<string, string[]>
  date_from?: string | null
  date_to?: string | null
  chart_type?: ReportChartType
  group_by_field?: string | null
  measure_field?: string | null
  export_format?: ReportExportFormat
  schedule?: ReportSchedule
  schedule_day?: number | null
  delivery_channels?: string[]
}

export interface ReportPreviewRequest {
  dataset: ReportDataset
  fields: string[]
  filters?: Record<string, string[]>
  date_from?: string | null
  date_to?: string | null
}

export interface ReportPreviewResult {
  rows: Record<string, unknown>[]
  row_count: number
}

export interface MonthlyReport {
  id: string
  period_start: string
  period_end: string
  delivered_channels: string[]
  delivered_at: string | null
  created_at: string
  download_url: string | null
}

// ------------------------------------------------------ AI lease analysis (Sprint 22)

export type LeaseSuggestionCategory = 'missing_clause' | 'problematic_term' | 'unclear_language'
export type LeaseSuggestionStatus = 'pending' | 'accepted' | 'dismissed'

export interface LeaseSuggestion {
  id: string
  category: LeaseSuggestionCategory
  title: string
  issue: string
  suggested_text: string | null
  status: LeaseSuggestionStatus
  created_at: string
}

export interface LeaseAnalysis {
  id: string
  lease_template_id: string
  model_used: string
  summary: string
  created_at: string
  suggestions: LeaseSuggestion[]
}

// ------------------------------------------------ fraud detection & security (Sprint 22)

export type FraudAlertType =
  | 'rapid_cash_payments'
  | 'off_hours_activity'
  | 'unusual_amount'
  | 'velocity_duplicate'
export type FraudAlertStatus = 'open' | 'suppressed' | 'resolved'

export interface FraudAlert {
  id: string
  alert_type: FraudAlertType
  entity_type: string
  entity_id: string
  summary: string
  details: Record<string, unknown>
  status: FraudAlertStatus
  resolved_at: string | null
  created_at: string
}

// -------------------------------------------------- partner integrations (Sprint 23)

export type PortalName = 'buyrentkenya' | 'pigiame'
export type PortalSyncStatus = 'pending' | 'published' | 'deactivated' | 'failed'

export interface PortalConnectionSummary {
  configured: boolean
  portal?: PortalName
  account_id?: string | null
  is_active?: boolean
  last_synced_at?: string | null
  last_error?: string | null
}

export interface PortalListingSync {
  id: string
  listing_id: string
  portal: PortalName
  external_listing_id: string | null
  status: PortalSyncStatus
  attempts: number
  last_attempt_at: string | null
  last_error: string | null
}

export type AccountingProvider = 'quickbooks' | 'xero'

export interface AccountingConnection {
  id: string
  provider: AccountingProvider
  external_account_id: string
  environment: string
  is_active: boolean
  last_synced_at: string | null
  last_error: string | null
}

export interface AccountingSyncRecord {
  id: string
  entity_type: string
  entity_id: string
  external_id: string | null
  status: string
  attempts: number
  last_error: string | null
  synced_at: string | null
  created_at: string
}

export interface AccountingSyncReport {
  synced: number
  failed: number
  pending: number
  recent_failures: AccountingSyncRecord[]
}

// ---------------------------------------------------- bank transfer (Sprint 23)

export interface BankInstructions {
  configured: boolean
  bank_name: string | null
  account_name: string | null
  account_number: string | null
  branch: string | null
}

export type BillingInterval = 'monthly' | 'annual'
export type SubscriptionStatus = 'active' | 'past_due' | 'lapsed' | 'cancelled'
export type SubscriptionInvoiceStatus = 'pending' | 'paid' | 'failed'

export interface PlanOption {
  id: 'starter' | 'professional' | 'business'
  monthly: string
  annual: string
}

export interface Subscription {
  id: string
  plan: string
  interval: BillingInterval
  status: SubscriptionStatus
  amount: string
  current_period_start: string
  current_period_end: string
  next_billing_date: string
  card_last4: string | null
  card_brand: string | null
  failed_attempts: number
  grace_ends_at: string | null
  cancelled_at: string | null
}

export interface SubscriptionInvoice {
  id: string
  reference_code: string
  period_start: string
  period_end: string
  amount: string
  status: SubscriptionInvoiceStatus
  attempts: number
  paid_at: string | null
  failure_reason: string | null
  created_at: string
}

export type MpesaCollectionMode = 'automated' | 'paybill' | 'manual'

export interface MpesaSetupStatus {
  mode: MpesaCollectionMode
  shortcode: string | null
  phone_number: string | null
  account_label: string | null
  daraja_environment: string
  has_api_credentials: boolean
  can_send_payouts: boolean
  verified_at: string | null
}

export interface MpesaTestResult {
  ok: boolean
  message: string
  verified_at: string | null
}

export interface PortalPaymentMethods {
  mpesa: boolean
  bank_transfer: boolean
}

export interface BankStatementRow {
  row: number
  entry_date: string
  description: string
  amount: string
  reference_guess: string | null
  matched_tenancy_id: string | null
}

export interface BankStatementPreview {
  rows: BankStatementRow[]
  errors: { row: number; reason: string }[]
  matched_count: number
  unmatched_count: number
}

export interface BankStatementCommitRow {
  row: number
  entry_date: string
  description: string
  amount: string
  tenancy_id: string | null
  record_payment: boolean
}

export interface BankStatementEntry {
  id: string
  entry_date: string
  description: string
  amount: string
  matched_tenancy_id: string | null
  matched_payment_id: string | null
  is_matched: boolean
}

export interface BankStatementUpload {
  id: string
  row_count: number
  matched_count: number
  unmatched_count: number
  created_at: string
}

export interface BankStatementUploadDetail extends BankStatementUpload {
  entries: BankStatementEntry[]
}

export interface BankStatementCommitResult {
  upload: BankStatementUpload
  payment_failures: { row: number; reason: string }[]
}

// ------------------------------------------------- Sprint 26 — masterplan gaps

export interface UtilityTrendPoint {
  month: string
  month_start: string
  water_consumption: number
  water_amount: number
  electricity_consumption: number
  electricity_amount: number
}

export interface HighConsumptionUnit {
  unit_id: string
  unit_number: string
  property_name: string
  meter_type: 'water' | 'electricity'
  reading_date: string
  consumption: number
  peer_average: number
  /** Whether the average compared against is this property's or the whole portfolio's. */
  peer_scope: 'property' | 'portfolio'
  percent_above_average: number
  amount: number
}

export interface UtilityAnalytics {
  months: number
  trend: UtilityTrendPoint[]
  billing_efficiency: {
    readings_taken: number
    readings_billed: number
    billed_percent: number
    amount_read: number
    amount_billed: number
    /** Consumption measured and never charged — where utility revenue leaks. */
    amount_unbilled: number
  }
  high_consumption_units: HighConsumptionUnit[]
  above_average_multiplier: number
}

export type PaymentSegment =
  | 'on_time'
  | 'occasionally_late'
  | 'chronically_late'
  | 'non_paying'
  | 'no_history'

export interface PaymentBehaviourRow {
  tenancy_id: string
  tenant_name: string
  property_name: string
  unit_number: string
  segment: PaymentSegment
  invoices_assessed: number
  paid_on_time: number
  paid_late: number
  still_unpaid: number
  average_days_late: number
  worst_days_late: number
  outstanding_balance: number
  monthly_rent: number
}

export interface PaymentBehaviour {
  months: number
  segments: Record<PaymentSegment, number>
  tenancies: PaymentBehaviourRow[]
}

export interface TurnoverProperty {
  property_id: string
  property_name: string
  active_tenancies: number
  moved_out: number
  turnover_rate_percent: number
  average_tenancy_months: number | null
}

export interface TenantTurnover {
  window_months: number
  active_tenancies: number
  moved_out: number
  tenancies_held: number
  turnover_rate_percent: number
  average_tenancy_months: number | null
  average_tenancy_months_all_time: number | null
  tenancies_ever_ended: number
  properties: TurnoverProperty[]
}

export type TemplateChannel = 'any' | 'whatsapp' | 'sms' | 'email' | 'in_app' | 'push'

export interface MessageTemplate {
  id: string
  notification_type: string
  channel: TemplateChannel
  title: string | null
  body: string
  is_active: boolean
  known_variables: string[]
  last_used_at: string | null
  updated_at: string
}

export interface MessageTemplateType {
  notification_type: string
  label: string
  available_variables: string[]
}

export interface MessageTemplatePreview {
  title: string | null
  body: string | null
  variables_used: string[]
  available_variables: string[]
  character_count: number
  sms_segments: number
}

export interface DemoDataStatus {
  loaded: boolean
  row_count: number
  recipe: string | null
  loaded_at: string | null
}

export interface MeterPhotoRead {
  reading: string | null
  confidence: string | null
  meter_kind: 'water' | 'electricity' | null
  message: string | null
  /** False when the reader is unsure enough that the form must not pre-fill. */
  high_confidence: boolean
}

export type ManagementAgreementStatus =
  | 'draft'
  | 'pending_signatures'
  | 'active'
  | 'termination_notice'
  | 'terminated'
  | 'expired'
  | 'cancelled'

export interface ManagementAgreement {
  id: string
  reference_code: string
  owner_profile_id: string
  status: ManagementAgreementStatus
  management_fee_percent: string
  disbursement_day: number
  maintenance_auto_approve_limit: string
  maintenance_notify_limit: string
  scope_of_management: string | null
  property_ids: string[]
  start_date: string
  term_months: number
  end_date: string | null
  notice_period_days: number
  document_id: string | null
  owner_signature_id: string | null
  agency_signature_id: string | null
  activated_at: string | null
  termination_requested_at: string | null
  termination_requested_by: 'owner' | 'agency' | null
  termination_reason: string | null
  termination_effective_date: string | null
  terminated_at: string | null
  created_at: string
}

export interface SearchResult {
  type: string
  id: string
  title: string
  subtitle: string
  url: string
}

export interface AuditChainVerification {
  total: number
  verified: number
  unchained: number
  intact: boolean
  broken_at_id: string | null
  broken_at_created_at: string | null
}

export interface SavedView {
  id: string
  entity_type: string
  name: string
  filters: Record<string, unknown>
  is_shared: boolean
  is_default: boolean
  user_id: string
  created_at: string
}

export interface ApprovalRule {
  id: string
  entity_type: string
  name: string
  threshold: string | null
  required_approver_roles: string[]
  required_approvals: number
  is_active: boolean
  created_at: string
}

export type ApprovalRequestStatus = 'pending' | 'approved' | 'rejected' | 'cancelled'

export interface ApprovalAction {
  id: string
  actor_name: string | null
  action: 'approve' | 'reject'
  note: string | null
  created_at: string
}

export interface ApprovalRequest {
  id: string
  entity_type: string
  entity_id: string
  requested_by_name: string | null
  trigger_value: string | null
  note: string | null
  required_approvals: number
  required_approver_roles: string[]
  status: ApprovalRequestStatus
  resolved_at: string | null
  context: Record<string, unknown> | null
  created_at: string
}

export interface ApprovalRequestDetail extends ApprovalRequest {
  actions: ApprovalAction[]
}
