import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive,
  ArchiveRestore,
  Building2,
  FolderOpen,
  Layers,
  MapPin,
  Pencil,
  Plus,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { propertiesApi } from '@/api'
import type { Unit } from '@/api/types'
import { PageHeader, StatCard } from '@/components/PageHeader'
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Dialog,
  EmptyState,
  PageLoader,
  Table,
  Td,
  Th,
  UNIT_STATUS_TONE,
  linkButtonClass,
} from '@/components/ui'
import { errorMessage, humanize, kes } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/store/auth-store'

export function PropertyDetailPage() {
  const { propertyId } = useParams<{ propertyId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [archiveError, setArchiveError] = useState<string | null>(null)

  const canManage = useAuthStore((state) => state.user?.permissions?.includes('property:manage'))
  const canManageUnits = useAuthStore((state) => state.user?.permissions?.includes('unit:manage'))

  const property = useQuery({
    queryKey: queryKeys.property(propertyId!),
    queryFn: () => propertiesApi.get(propertyId!),
    enabled: Boolean(propertyId),
  })

  const units = useQuery({
    queryKey: queryKeys.units({ property_id: propertyId }),
    queryFn: () => propertiesApi.units(propertyId!),
    enabled: Boolean(propertyId),
  })

  const archive = useMutation({
    mutationFn: () => propertiesApi.archive(propertyId!),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['properties'] })
      setArchiveOpen(false)
      navigate('/properties')
    },
    onError: (error) => setArchiveError(errorMessage(error)),
  })

  const restore = useMutation({
    mutationFn: () => propertiesApi.restore(propertyId!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['propert'] }),
  })

  if (property.isPending) return <PageLoader />
  if (property.isError) {
    return (
      <Alert tone="danger" title="Could not load this property">
        {errorMessage(property.error)}
      </Alert>
    )
  }

  const record = property.data

  return (
    <div>
      <PageHeader
        title={record.name}
        description={record.address}
        backTo="/properties"
        backLabel="All properties"
        actions={
          <>
            <Link to={`/properties/${propertyId}/documents`} className={linkButtonClass('outline')}>
              <FolderOpen className="h-4 w-4" />
              Documents
            </Link>
            {canManage && (
              <>
                <Link
                  to={`/properties/${propertyId}/edit`}
                  className={linkButtonClass('outline', 'md')}
                >
                  <Pencil className="h-4 w-4" />
                  Edit
                </Link>
                {record.is_archived ? (
                  <Button
                    variant="secondary"
                    icon={<ArchiveRestore className="h-4 w-4" />}
                    onClick={() => restore.mutate()}
                    loading={restore.isPending}
                  >
                    Restore
                  </Button>
                ) : (
                  <Button
                    variant="ghost"
                    icon={<Archive className="h-4 w-4" />}
                    onClick={() => setArchiveOpen(true)}
                  >
                    Archive
                  </Button>
                )}
              </>
            )}
          </>
        }
      />

      {record.is_archived && (
        <Alert tone="warn" className="mb-5" title="This property is archived">
          It stays in your history and reports, but is hidden from active views.
        </Alert>
      )}

      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Units" value={String(record.total_units)} />
        <StatCard
          label="Occupied"
          value={String(record.occupied_units)}
          tone="success"
          hint={`${record.occupancy_rate}% occupancy`}
        />
        <StatCard label="Vacant" value={String(record.vacant_units)} tone="warn" />
        <StatCard
          label="Monthly potential"
          value={kes(record.monthly_rent_potential, { compact: true })}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Units</CardTitle>
              {canManageUnits && !record.is_archived && (
                <div className="flex gap-2">
                  <Link
                    to={`/units/new?property_id=${propertyId}`}
                    className={linkButtonClass('outline', 'sm')}
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add unit
                  </Link>
                  <Link
                    to={`/units/bulk?property_id=${propertyId}`}
                    className={linkButtonClass('primary', 'sm')}
                  >
                    <Layers className="h-3.5 w-3.5" />
                    Add many
                  </Link>
                </div>
              )}
            </CardHeader>

            {units.data?.length ? (
              <Table>
                <thead>
                  <tr>
                    <Th>Unit</Th>
                    <Th>Type</Th>
                    <Th>Rent</Th>
                    <Th>Status</Th>
                  </tr>
                </thead>
                <tbody>
                  {units.data.map((unit: Unit) => (
                    <tr key={unit.id} className="hover:bg-slate-50">
                      <Td>
                        <Link
                          to={`/units/${unit.id}`}
                          className="font-medium text-brand-700 hover:underline"
                        >
                          {unit.unit_number}
                        </Link>
                        <span className="block text-xs text-slate-400">{unit.reference_code}</span>
                      </Td>
                      <Td className="text-slate-600">
                        {unit.unit_type ?? '—'}
                        {unit.bedrooms != null && (
                          <span className="block text-xs text-slate-400">
                            {unit.bedrooms} bed · {unit.bathrooms ?? 0} bath
                          </span>
                        )}
                      </Td>
                      <Td className="font-medium">{kes(unit.monthly_rent)}</Td>
                      <Td>
                        <Badge tone={UNIT_STATUS_TONE[unit.status] ?? 'neutral'}>
                          {humanize(unit.status)}
                        </Badge>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState
                icon={<Building2 className="h-6 w-6" />}
                title="No units yet"
                description="Add units one at a time, or create a whole block at once."
                action={
                  canManageUnits ? (
                    <Link
                      to={`/units/bulk?property_id=${propertyId}`}
                      className={linkButtonClass()}
                    >
                      <Layers className="h-4 w-4" />
                      Add units
                    </Link>
                  ) : undefined
                }
              />
            )}
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3 text-sm">
              <Detail label="Reference" value={record.reference_code} />
              <Detail label="Type" value={humanize(record.property_type)} />
              <Detail
                label="Location"
                value={
                  <span className="flex items-start gap-1">
                    <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                    <span>
                      {record.address}
                      {record.county && (
                        <span className="block text-slate-500">{record.county} County</span>
                      )}
                    </span>
                  </span>
                }
              />
              <Detail
                label="Water rate"
                value={record.water_rate_per_unit ? `${kes(record.water_rate_per_unit)} / unit` : 'Not metered'}
              />
              <Detail
                label="Electricity rate"
                value={
                  record.electricity_rate_per_unit
                    ? `${kes(record.electricity_rate_per_unit)} / unit`
                    : 'Not metered'
                }
              />
              <Detail label="Grace period" value={`${record.grace_period_days} days`} />
              {record.description && <Detail label="Notes" value={record.description} />}
            </CardBody>
          </Card>

          {record.amenities.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Amenities</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="flex flex-wrap gap-1.5">
                  {record.amenities.map((amenity) => (
                    <Badge key={amenity}>{amenity}</Badge>
                  ))}
                </div>
              </CardBody>
            </Card>
          )}

          {record.photos.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Photos</CardTitle>
              </CardHeader>
              <CardBody>
                <div className="grid grid-cols-3 gap-2">
                  {record.photos.map((photo) => (
                    <a
                      key={photo.id}
                      href={photo.url}
                      target="_blank"
                      rel="noreferrer"
                      className="aspect-square overflow-hidden rounded-lg border border-slate-200"
                    >
                      <img src={photo.url} alt="" className="h-full w-full object-cover" />
                    </a>
                  ))}
                </div>
              </CardBody>
            </Card>
          )}
        </div>
      </div>

      <Dialog
        open={archiveOpen}
        onClose={() => setArchiveOpen(false)}
        title={`Archive ${record.name}?`}
        description="Archived properties disappear from active views but keep all their history."
        footer={
          <>
            <Button variant="ghost" onClick={() => setArchiveOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" loading={archive.isPending} onClick={() => archive.mutate()}>
              Archive property
            </Button>
          </>
        }
      >
        <p className="text-sm text-slate-600">
          All {record.total_units} unit(s) under it are archived too. You can restore it at any time.
        </p>
        {archiveError && (
          <Alert tone="danger" className="mt-3">
            {archiveError}
          </Alert>
        )}
      </Dialog>
    </div>
  )
}

function Detail({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-slate-800">{value}</dd>
    </div>
  )
}
