import { useQuery } from '@tanstack/react-query'
import { HardDrive } from 'lucide-react'
import { useParams } from 'react-router-dom'

import { propertiesApi, tenantsApi, vaultApi } from '@/api'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardBody, CardHeader, CardTitle, PageLoader } from '@/components/ui'
import { DocumentVault } from '@/features/vault/DocumentVault'
import { fileSize } from '@/features/vault/file-size'
import { humanize } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

/** US-045 — everything filed against one tenant, in one place. */
export function TenantVaultPage() {
  const { tenantId = '' } = useParams()
  const tenant = useQuery({
    queryKey: queryKeys.tenant(tenantId),
    queryFn: () => tenantsApi.get(tenantId),
    enabled: Boolean(tenantId),
  })

  if (tenant.isPending) return <PageLoader />

  return (
    <div>
      <PageHeader
        title={`${tenant.data?.full_name ?? 'Tenant'} — documents`}
        description="Lease, receipts, inspections and notices, organised by type."
        backTo={`/tenants/${tenantId}`}
        backLabel="Tenant"
      />
      <DocumentVault
        title="Document vault"
        subtitle="Everything generated for this tenant lands here automatically."
        entityType="tenant"
        entityId={tenantId}
        queryKey={queryKeys.tenantVault(tenantId)}
        fetcher={(params) => vaultApi.tenant(tenantId, params)}
        tenantIdForDelivery={tenantId}
      />
    </div>
  )
}

/** US-046 — title deeds, insurance, compliance and every lease on a property. */
export function PropertyVaultPage() {
  const { propertyId = '' } = useParams()
  const property = useQuery({
    queryKey: queryKeys.property(propertyId),
    queryFn: () => propertiesApi.get(propertyId),
    enabled: Boolean(propertyId),
  })
  const usage = useQuery({ queryKey: queryKeys.vaultUsage, queryFn: vaultApi.usage })

  if (property.isPending) return <PageLoader />

  return (
    <div>
      <PageHeader
        title={`${property.data?.name ?? 'Property'} — documents`}
        description="Title deed, insurance, compliance certificates and every lease on file."
        backTo={`/properties/${propertyId}`}
        backLabel="Property"
      />

      <div className="mb-4">
        <DocumentVault
          title="Property vault"
          subtitle="Covers the property, all its units and every tenancy in them."
          entityType="property"
          entityId={propertyId}
          queryKey={queryKeys.propertyVault(propertyId)}
          fetcher={(params) => vaultApi.property(propertyId, params)}
        />
      </div>

      {usage.data && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              <HardDrive className="mr-1.5 inline h-4 w-4 text-slate-400" />
              Storage across the account
            </CardTitle>
          </CardHeader>
          <CardBody>
            <p className="mb-3 text-sm text-slate-600">
              {usage.data.total_documents} documents · {fileSize(usage.data.total_bytes)} in total
            </p>
            <ul className="space-y-1.5">
              {usage.data.by_category.slice(0, 8).map((row) => (
                <li key={row.category} className="flex items-center justify-between text-sm">
                  <span className="text-slate-600">{humanize(row.category)}</span>
                  <span className="text-slate-500">
                    {row.document_count} · {fileSize(row.bytes)}
                  </span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
