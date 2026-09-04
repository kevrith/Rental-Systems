import { QueryClient } from '@tanstack/react-query'
import { AxiosError } from 'axios'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        // 4xx responses are decisions, not blips — retrying them just delays the
        // error the user needs to see.
        const status = (error as AxiosError)?.response?.status
        if (status && status >= 400 && status < 500) return false
        return failureCount < 2
      },
    },
    mutations: { retry: false },
  },
})

/** Query keys, centralised so invalidation after a mutation stays honest. */
export const queryKeys = {
  me: ['me'] as const,
  organization: ['organization'] as const,
  properties: (filters?: unknown) => ['properties', filters ?? {}] as const,
  property: (id: string) => ['property', id] as const,
  units: (filters?: unknown) => ['units', filters ?? {}] as const,
  unit: (id: string) => ['unit', id] as const,
  tenants: (filters?: unknown) => ['tenants', filters ?? {}] as const,
  tenant: (id: string) => ['tenant', id] as const,
  tenantDocuments: (id: string) => ['tenant', id, 'documents'] as const,
  tenancies: (filters?: unknown) => ['tenancies', filters ?? {}] as const,
  tenancy: (id: string) => ['tenancy', id] as const,
  invoices: (filters?: unknown) => ['invoices', filters ?? {}] as const,
  invoice: (id: string) => ['invoice', id] as const,
  payments: (filters?: unknown) => ['payments', filters ?? {}] as const,
  payment: (id: string) => ['payment', id] as const,
  arrears: (filters?: unknown) => ['arrears', filters ?? {}] as const,
  portfolio: ['dashboard', 'portfolio'] as const,
  financial: (months?: number) => ['dashboard', 'financial', months ?? 6] as const,
  maintenance: (filters?: unknown) => ['maintenance', filters ?? {}] as const,
  maintenanceRequest: (id: string) => ['maintenance', id] as const,
  meterReadings: (filters?: unknown) => ['meter-readings', filters ?? {}] as const,
  meterContext: (unitId: string, meterType: string) =>
    ['meter-readings', 'context', unitId, meterType] as const,
  readingsDue: ['meter-readings', 'due'] as const,
  caretakerToday: ['caretaker', 'today'] as const,
  team: ['team'] as const,
  invitations: ['team', 'invitations'] as const,
  sessions: ['auth', 'sessions'] as const,
  notifications: (filters?: unknown) => ['notifications', filters ?? {}] as const,
  unreadCount: ['notifications', 'unread'] as const,
  preferences: ['notifications', 'preferences'] as const,
  activity: (filters?: unknown) => ['activity', filters ?? {}] as const,
  vacateNotices: (filters?: unknown) => ['vacate-notices', filters ?? {}] as const,
  leaseTemplates: ['lease-templates'] as const,
  portalHome: ['portal', 'home'] as const,
  portalPayments: ['portal', 'payments'] as const,
  portalInvoices: ['portal', 'invoices'] as const,
  portalDocuments: ['portal', 'documents'] as const,
  portalMaintenance: ['portal', 'maintenance'] as const,

  // Automation and accountability (Phase 2)
  scheduledTasks: ['tasks', 'overview'] as const,
  taskHistory: (name: string) => ['tasks', name, 'history'] as const,
  caretakerScores: (windowDays: number) => ['caretaker', 'performance', windowDays] as const,
  caretakerScore: (id: string, windowDays: number) =>
    ['caretaker', 'performance', id, windowDays] as const,
  renewals: (tenancyId?: string) => ['renewals', tenancyId ?? 'all'] as const,

  // Analytics (Phase 2)
  analyticsRevenue: (months: number) => ['analytics', 'revenue', months] as const,
  analyticsPerformance: ['analytics', 'property-performance'] as const,
  analyticsForecast: (months: number) => ['analytics', 'forecast', months] as const,
  analyticsExpiring: ['analytics', 'expiring-leases'] as const,
  analyticsMaintenance: ['analytics', 'maintenance'] as const,
  etimsCredentials: ['etims', 'credentials'] as const,
  etimsReport: ['etims', 'report'] as const,

  // Inspections (Phase 2)
  inspections: (filters?: unknown) => ['inspections', filters ?? {}] as const,
  inspection: (id: string) => ['inspections', id] as const,
  inspectionComparison: (id: string) => ['inspections', id, 'comparison'] as const,
  inspectionCompliance: ['inspections', 'compliance'] as const,

  // Document vault (Phase 2)
  tenantVault: (id: string) => ['vault', 'tenant', id] as const,
  propertyVault: (id: string) => ['vault', 'property', id] as const,
  vaultUsage: ['vault', 'usage'] as const,

  // Agency mode (Phase 2)
  // Vendors and the maintenance lifecycle (Phase 3)
  vendors: (filters?: unknown) => ['vendors', filters ?? {}] as const,
  vendor: (id: string) => ['vendors', id] as const,
  maintenanceAnalytics: (months: number) => ['maintenance', 'analytics', months] as const,
  unitMaintenance: (unitId: string) => ['maintenance', 'unit', unitId] as const,

  agencyDashboard: ['agency', 'dashboard'] as const,
  ownerSummaries: ['agency', 'owner-summaries'] as const,
  ownerProfiles: ['agency', 'owner-profiles'] as const,
  ownerProfile: (id: string) => ['agency', 'owner-profile', id] as const,
  disbursements: (filters?: unknown) => ['agency', 'disbursements', filters ?? {}] as const,
  ownerPortalSummary: ['agency', 'owner-portal'] as const,
}
