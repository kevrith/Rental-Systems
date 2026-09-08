import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, GripVertical, Plus, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useNavigate, useParams } from 'react-router-dom'

import { reportsApi } from '@/api'
import type {
  ReportChartType,
  ReportDataset,
  ReportDefinitionInput,
  ReportFieldMeta,
  ReportSchedule,
} from '@/api/types'
import { PageHeader } from '@/components/PageHeader'
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Field,
  Input,
  PageLoader,
  Select,
  Table,
  Td,
  Th,
} from '@/components/ui'
import { apiClient } from '@/lib/api-client'
import { AXIS, SERIES, TOOLTIP_STYLE } from '@/features/analytics/chart-theme'
import { errorMessage } from '@/lib/format'
import { queryKeys } from '@/lib/query-client'

const CHART_TYPES: { value: ReportChartType; label: string }[] = [
  { value: 'table', label: 'Table' },
  { value: 'bar', label: 'Bar chart' },
  { value: 'line', label: 'Line chart' },
  { value: 'pie', label: 'Pie chart' },
]

const SCHEDULES: { value: ReportSchedule; label: string }[] = [
  { value: 'none', label: "Don't schedule" },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
]

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

const DELIVERY_CHANNELS: { value: string; label: string }[] = [
  { value: 'in_app', label: 'In-app notification' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'email', label: 'Email' },
]

// Only these field types get a checkbox filter — a number or date range editor
// per arbitrary field is a lot of UI for a builder most accounts will use for a
// handful of saved reports. Date range is covered separately below.
const FILTERABLE_TYPES = new Set(['string', 'enum', 'bool'])
const MAX_FILTER_OPTIONS = 30

const CHART_COLORS = [SERIES.collected, SERIES.forecast, SERIES.other]

function aggregateForChart(rows: Record<string, unknown>[], groupField: string, measureField: string) {
  const totals = new Map<string, number>()
  for (const row of rows) {
    const key = String(row[groupField] ?? '—')
    const value = Number(row[measureField]) || 0
    totals.set(key, (totals.get(key) ?? 0) + value)
  }
  const sorted = [...totals.entries()].sort((a, b) => b[1] - a[1])
  const top = sorted.slice(0, 2).map(([name, value]) => ({ name, value }))
  const rest = sorted.slice(2)
  if (rest.length > 0) {
    top.push({ name: 'Other', value: rest.reduce((sum, [, value]) => sum + value, 0) })
  }
  return top
}

export function ReportBuilderPage() {
  const { id } = useParams<{ id: string }>()
  const isEdit = Boolean(id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [dataset, setDataset] = useState<ReportDataset>('payments')
  const [selectedFields, setSelectedFields] = useState<string[]>([])
  const [filters, setFilters] = useState<Record<string, string[]>>({})
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [chartType, setChartType] = useState<ReportChartType>('table')
  const [groupByField, setGroupByField] = useState('')
  const [measureField, setMeasureField] = useState('')
  const [schedule, setSchedule] = useState<ReportSchedule>('none')
  const [scheduleDay, setScheduleDay] = useState(1)
  const [deliveryChannels, setDeliveryChannels] = useState<string[]>(['in_app'])
  const [dragIndex, setDragIndex] = useState<number | null>(null)

  const datasets = useQuery({ queryKey: queryKeys.reportDatasets, queryFn: reportsApi.datasets })
  const fields = useQuery({
    queryKey: queryKeys.reportFields(dataset),
    queryFn: () => reportsApi.fields(dataset),
  })
  const existing = useQuery({
    queryKey: queryKeys.reportDefinition(id ?? ''),
    queryFn: () => reportsApi.get(id as string),
    enabled: isEdit,
  })

  useEffect(() => {
    if (!existing.data) return
    const report = existing.data
    setName(report.name)
    setDataset(report.dataset)
    setSelectedFields(report.fields)
    setFilters(report.filters)
    setDateFrom(report.date_from ?? '')
    setDateTo(report.date_to ?? '')
    setChartType(report.chart_type)
    setGroupByField(report.group_by_field ?? '')
    setMeasureField(report.measure_field ?? '')
    setSchedule(report.schedule)
    setScheduleDay(report.schedule_day ?? 1)
    setDeliveryChannels(report.delivery_channels.length > 0 ? report.delivery_channels : ['in_app'])
  }, [existing.data])

  const fieldMeta = useMemo(
    () => new Map((fields.data ?? []).map((field) => [field.key, field])),
    [fields.data],
  )
  const numericFields = selectedFields.filter((key) => fieldMeta.get(key)?.type === 'number')

  const optionsPreview = useQuery({
    queryKey: ['reports', 'preview', 'options', dataset, selectedFields],
    queryFn: () => reportsApi.preview({ dataset, fields: selectedFields }),
    enabled: selectedFields.length > 0,
  })

  const filteredPreview = useQuery({
    queryKey: ['reports', 'preview', 'filtered', dataset, selectedFields, filters, dateFrom, dateTo],
    queryFn: () =>
      reportsApi.preview({
        dataset,
        fields: selectedFields,
        filters,
        date_from: dateFrom || null,
        date_to: dateTo || null,
      }),
    enabled: selectedFields.length > 0,
  })

  const optionsByField = useMemo(() => {
    const rows = optionsPreview.data?.rows ?? []
    const map = new Map<string, string[]>()
    for (const field of selectedFields) {
      const meta = fieldMeta.get(field)
      if (!meta || !FILTERABLE_TYPES.has(meta.type)) continue
      const values = new Set<string>()
      for (const row of rows) values.add(String(row[field] ?? '—'))
      if (values.size > 0 && values.size <= MAX_FILTER_OPTIONS) map.set(field, [...values].sort())
    }
    return map
  }, [optionsPreview.data, selectedFields, fieldMeta])

  const chartData = useMemo(() => {
    if (chartType === 'table' || !groupByField || !measureField || !filteredPreview.data) return []
    return aggregateForChart(filteredPreview.data.rows, groupByField, measureField)
  }, [chartType, groupByField, measureField, filteredPreview.data])

  function selectDataset(next: ReportDataset) {
    setDataset(next)
    setSelectedFields([])
    setFilters({})
    setGroupByField('')
    setMeasureField('')
  }

  function toggleField(key: string) {
    setSelectedFields((current) =>
      current.includes(key) ? current.filter((field) => field !== key) : [...current, key],
    )
  }

  function toggleFilterValue(field: string, value: string) {
    setFilters((current) => {
      const active = current[field] ?? []
      const next = active.includes(value) ? active.filter((v) => v !== value) : [...active, value]
      const updated = { ...current }
      if (next.length === 0) delete updated[field]
      else updated[field] = next
      return updated
    })
  }

  function reorderFields(from: number, to: number) {
    setSelectedFields((current) => {
      const next = [...current]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return next
    })
  }

  function buildPayload(): ReportDefinitionInput {
    return {
      name,
      dataset,
      fields: selectedFields,
      filters,
      date_from: dateFrom || null,
      date_to: dateTo || null,
      chart_type: chartType,
      group_by_field: chartType === 'table' ? null : groupByField || null,
      measure_field: chartType === 'table' ? null : measureField || null,
      schedule,
      schedule_day: schedule === 'none' ? null : scheduleDay,
      delivery_channels: schedule === 'none' ? [] : deliveryChannels,
    }
  }

  const save = useMutation({
    mutationFn: () =>
      isEdit ? reportsApi.update(id as string, buildPayload()) : reportsApi.create(buildPayload()),
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.reportDefinitions })
      setError(null)
      if (!isEdit) navigate(`/reports/${saved.id}/edit`, { replace: true })
    },
    onError: (saveError) => setError(errorMessage(saveError)),
  })

  const runExport = useMutation({
    mutationFn: async (format: 'csv' | 'excel' | 'pdf') => {
      const response = await apiClient.post(
        `/reports/definitions/${id}/run`,
        undefined,
        { params: { format }, responseType: 'blob' },
      )
      const disposition = String(response.headers['content-disposition'] ?? '')
      const match = disposition.match(/filename="?([^"]+)"?/)
      const url = URL.createObjectURL(response.data as Blob)
      const link = document.createElement('a')
      link.href = url
      link.download = match?.[1] ?? `${name || 'report'}.${format}`
      link.click()
      URL.revokeObjectURL(url)
    },
    onError: (runError) => setError(errorMessage(runError)),
  })

  if ((isEdit && existing.isPending) || datasets.isPending) return <PageLoader />

  const canSave = name.trim().length >= 2 && selectedFields.length > 0

  return (
    <div>
      <PageHeader
        title={isEdit ? 'Edit report' : 'New report'}
        description="Pick a dataset, choose your columns, filter, and optionally chart and schedule it."
        backTo="/reports"
        backLabel="Reports"
      />

      {error && (
        <Alert tone="danger" className="mb-4">
          {error}
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>1. Dataset and columns</CardTitle>
            </CardHeader>
            <CardBody className="space-y-4">
              <Field label="Dataset">
                <Select
                  value={dataset}
                  onChange={(event) => selectDataset(event.target.value as ReportDataset)}
                  disabled={isEdit}
                >
                  {(datasets.data ?? []).map((option) => (
                    <option key={option.dataset} value={option.dataset}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <p className="mb-1.5 text-sm font-medium text-slate-700">Available fields</p>
                  <div className="max-h-64 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2">
                    {(fields.data ?? []).map((field: ReportFieldMeta) => (
                      <button
                        key={field.key}
                        type="button"
                        onClick={() => toggleField(field.key)}
                        disabled={selectedFields.includes(field.key)}
                        className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {field.label}
                        <Plus className="h-3.5 w-3.5 text-slate-400" />
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="mb-1.5 text-sm font-medium text-slate-700">
                    Selected columns — drag to reorder
                  </p>
                  <div className="max-h-64 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2">
                    {selectedFields.length === 0 && (
                      <p className="px-2 py-1.5 text-sm text-slate-400">
                        Add fields from the left to build your report.
                      </p>
                    )}
                    {selectedFields.map((key, index) => (
                      <div
                        key={key}
                        draggable
                        onDragStart={() => setDragIndex(index)}
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={() => {
                          if (dragIndex !== null && dragIndex !== index) reorderFields(dragIndex, index)
                          setDragIndex(null)
                        }}
                        className="flex items-center gap-2 rounded-md bg-slate-50 px-2 py-1.5 text-sm text-slate-800"
                      >
                        <GripVertical className="h-3.5 w-3.5 shrink-0 cursor-grab text-slate-400" />
                        <span className="flex-1 truncate">{fieldMeta.get(key)?.label ?? key}</span>
                        <button
                          type="button"
                          onClick={() => toggleField(key)}
                          className="shrink-0 text-slate-400 hover:text-danger-600"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>2. Filters</CardTitle>
              <p className="mt-0.5 text-sm text-slate-500">
                Filters apply to whichever columns you've selected above.
              </p>
            </CardHeader>
            <CardBody className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="Date from">
                  <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
                </Field>
                <Field label="Date to">
                  <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
                </Field>
              </div>

              {optionsByField.size === 0 ? (
                <p className="text-sm text-slate-500">
                  Select a text or status column to filter by its values.
                </p>
              ) : (
                [...optionsByField.entries()].map(([field, values]) => (
                  <div key={field}>
                    <p className="mb-1.5 text-sm font-medium text-slate-700">
                      {fieldMeta.get(field)?.label ?? field}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {values.map((value) => {
                        const active = (filters[field] ?? []).includes(value)
                        return (
                          <button
                            key={value}
                            type="button"
                            onClick={() => toggleFilterValue(field, value)}
                            className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                              active
                                ? 'border-brand-600 bg-brand-50 text-brand-700'
                                : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                            }`}
                          >
                            {value}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>3. Chart</CardTitle>
            </CardHeader>
            <CardBody className="space-y-4">
              <Field label="Display as">
                <Select value={chartType} onChange={(e) => setChartType(e.target.value as ReportChartType)}>
                  {CHART_TYPES.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>
              {chartType !== 'table' && (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field label="Group by">
                    <Select value={groupByField} onChange={(e) => setGroupByField(e.target.value)}>
                      <option value="">Choose a column</option>
                      {selectedFields.map((key) => (
                        <option key={key} value={key}>
                          {fieldMeta.get(key)?.label ?? key}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Measure (sum of)">
                    <Select value={measureField} onChange={(e) => setMeasureField(e.target.value)}>
                      <option value="">Choose a number column</option>
                      {numericFields.map((key) => (
                        <option key={key} value={key}>
                          {fieldMeta.get(key)?.label ?? key}
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
              )}
            </CardBody>
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Save</CardTitle>
            </CardHeader>
            <CardBody className="space-y-4">
              <Field label="Report name">
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Rent by property" />
              </Field>
              <Field label="Schedule">
                <Select value={schedule} onChange={(e) => setSchedule(e.target.value as ReportSchedule)}>
                  {SCHEDULES.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>
              {schedule !== 'none' && (
                <>
                  <Field label={schedule === 'weekly' ? 'Day of week' : 'Day of month'}>
                    <Select value={scheduleDay} onChange={(e) => setScheduleDay(Number(e.target.value))}>
                      {schedule === 'weekly'
                        ? WEEKDAYS.map((day, index) => (
                            <option key={day} value={index}>
                              {day}
                            </option>
                          ))
                        : Array.from({ length: 28 }, (_, i) => i + 1).map((day) => (
                            <option key={day} value={day}>
                              {day}
                            </option>
                          ))}
                    </Select>
                  </Field>
                  <div>
                    <p className="mb-1.5 text-sm font-medium text-slate-700">Deliver via</p>
                    <div className="space-y-1.5">
                      {DELIVERY_CHANNELS.map((channel) => (
                        <label key={channel.value} className="flex items-center gap-2 text-sm text-slate-700">
                          <input
                            type="checkbox"
                            className="h-4 w-4 rounded border-slate-300"
                            checked={deliveryChannels.includes(channel.value)}
                            onChange={() =>
                              setDeliveryChannels((current) =>
                                current.includes(channel.value)
                                  ? current.filter((c) => c !== channel.value)
                                  : [...current, channel.value],
                              )
                            }
                          />
                          {channel.label}
                        </label>
                      ))}
                    </div>
                  </div>
                </>
              )}

              <Button onClick={() => save.mutate()} disabled={!canSave || save.isPending} className="w-full">
                {save.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Save report'}
              </Button>

              {isEdit && (
                <div className="border-t border-slate-100 pt-3">
                  <p className="mb-2 text-sm font-medium text-slate-700">Export now</p>
                  <div className="flex gap-2">
                    {(['csv', 'excel', 'pdf'] as const).map((format) => (
                      <Button
                        key={format}
                        variant="secondary"
                        size="sm"
                        onClick={() => runExport.mutate(format)}
                        disabled={runExport.isPending}
                        icon={<Download className="h-3.5 w-3.5" />}
                      >
                        {format.toUpperCase()}
                      </Button>
                    ))}
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      </div>

      <Card className="mt-5">
        <CardHeader>
          <CardTitle>Preview</CardTitle>
          <p className="mt-0.5 text-sm text-slate-500">
            {filteredPreview.data ? `${filteredPreview.data.row_count} row(s) matched` : 'Pick some columns to preview your report.'}
          </p>
        </CardHeader>
        <CardBody>
          {selectedFields.length === 0 ? (
            <p className="text-sm text-slate-500">Nothing to preview yet.</p>
          ) : chartType !== 'table' && groupByField && measureField ? (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                {chartType === 'pie' ? (
                  <PieChart>
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Pie data={chartData} dataKey="value" nameKey="name" outerRadius={100}>
                      {chartData.map((entry, index) => (
                        <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                  </PieChart>
                ) : chartType === 'line' ? (
                  <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={AXIS.grid} vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: AXIS.tick }} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: AXIS.tick }} tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Line type="monotone" dataKey="value" stroke={SERIES.collected} strokeWidth={2} />
                  </LineChart>
                ) : (
                  <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={AXIS.grid} vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 11, fill: AXIS.tick }} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: AXIS.tick }} tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                      {chartData.map((entry, index) => (
                        <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                )}
              </ResponsiveContainer>
            </div>
          ) : null}

          {selectedFields.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    {selectedFields.map((key) => (
                      <Th key={key}>{fieldMeta.get(key)?.label ?? key}</Th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(filteredPreview.data?.rows ?? []).slice(0, 20).map((row, index) => (
                    <tr key={index}>
                      {selectedFields.map((key) => (
                        <Td key={key}>{String(row[key] ?? '—')}</Td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  )
}
