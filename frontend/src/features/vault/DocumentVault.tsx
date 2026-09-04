import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive,
  Download,
  FileText,
  History,
  Search,
  Send,
  Tag,
  Upload as UploadIcon,
} from 'lucide-react'
import { useState } from 'react'

import { filesApi, vaultApi } from '@/api'
import type { VaultDocument, VaultSection } from '@/api/types'
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
  Field,
  Input,
  PageLoader,
  Select,
  Textarea,
} from '@/components/ui'
import { fileSize } from '@/features/vault/file-size'
import { API_BASE_URL } from '@/lib/api-client'
import { dateTime, errorMessage, humanize } from '@/lib/format'

/** The three-step direct-to-storage upload, without the photo-grid chrome. */
async function uploadDocument(file: File, category: string): Promise<string> {
  const ticket = await filesApi.requestUpload({
    filename: file.name,
    content_type: file.type || 'application/octet-stream',
    size_bytes: file.size,
    category,
  })
  const destination = ticket.upload_url.startsWith('http')
    ? ticket.upload_url
    : `${API_BASE_URL.replace(/\/api\/v1$/, '')}${ticket.upload_url}`

  const response = await fetch(destination, {
    method: ticket.method,
    headers: ticket.headers,
    body: file,
  })
  if (!response.ok) throw new Error(`Upload failed (${response.status})`)

  await filesApi.confirm(ticket.file_id, file.size)
  return ticket.file_id
}

export interface VaultData {
  document_count: number
  total_bytes: number
  sections: VaultSection[]
}

/**
 * The document vault, shared by the tenant and property screens (US-045, US-046).
 *
 * Both vaults are the same shape — sections by category, a search box, and the
 * same actions on a row — so they are one component with a different owner.
 * Everything the server generates lands here without being filed by hand; only
 * an agency's own paperwork needs uploading.
 */
export function DocumentVault({
  title,
  subtitle,
  entityType,
  entityId,
  queryKey,
  fetcher,
  tenantIdForDelivery,
}: {
  title: string
  subtitle: string
  entityType: 'tenant' | 'property'
  entityId: string
  queryKey: readonly unknown[]
  fetcher: (params: {
    category?: string
    search?: string
    include_archived?: boolean
  }) => Promise<VaultData>
  /** When present, a document can be sent straight to this tenant on WhatsApp. */
  tenantIdForDelivery?: string
}) {
  const queryClient = useQueryClient()

  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [includeArchived, setIncludeArchived] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadCategory, setUploadCategory] = useState('title_deed')
  const [uploadTags, setUploadTags] = useState('')
  const [uploadDescription, setUploadDescription] = useState('')
  const [uploadFile, setUploadFile] = useState<File | null>(null)

  const [historyFor, setHistoryFor] = useState<VaultDocument | null>(null)
  const [replaceFor, setReplaceFor] = useState<VaultDocument | null>(null)
  const [replaceFile, setReplaceFile] = useState<File | null>(null)
  const [sendFor, setSendFor] = useState<VaultDocument | null>(null)
  const [sendPhone, setSendPhone] = useState('')

  const categories = useQuery({ queryKey: ['vault', 'categories'], queryFn: vaultApi.categories })
  const vault = useQuery({
    queryKey: [...queryKey, { search, category, includeArchived }],
    queryFn: () =>
      fetcher({
        search: search || undefined,
        category: category || undefined,
        include_archived: includeArchived || undefined,
      }),
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['vault'] })
    await queryClient.invalidateQueries({ queryKey })
  }

  const upload = useMutation({
    mutationFn: async () => {
      if (!uploadFile) throw new Error('Choose a file first.')
      const fileId = await uploadDocument(uploadFile, uploadCategory)
      return vaultApi.file({
        file_id: fileId,
        entity_type: entityType,
        entity_id: entityId,
        category: uploadCategory,
        tags: uploadTags
          .split(',')
          .map((tag) => tag.trim())
          .filter(Boolean),
        description: uploadDescription || null,
      })
    },
    onSuccess: async (document) => {
      setError(null)
      setNotice(`${document.filename} added to the vault.`)
      setUploadOpen(false)
      setUploadFile(null)
      setUploadTags('')
      setUploadDescription('')
      await refresh()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const replace = useMutation({
    mutationFn: async () => {
      if (!replaceFor || !replaceFile) throw new Error('Choose a replacement file.')
      const fileId = await uploadDocument(replaceFile, replaceFor.category)
      return vaultApi.addVersion(replaceFor.id, { file_id: fileId })
    },
    onSuccess: async (document) => {
      setError(null)
      setNotice(`Saved as version ${document.version}. The previous one is still in the history.`)
      setReplaceFor(null)
      setReplaceFile(null)
      await refresh()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const archive = useMutation({
    mutationFn: (id: string) => vaultApi.archive(id),
    onSuccess: async () => {
      setError(null)
      setNotice('Document archived. Nothing was deleted — tick "show archived" to see it.')
      await refresh()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const send = useMutation({
    mutationFn: () => {
      if (!sendFor) throw new Error('Nothing selected.')
      return vaultApi.send(sendFor.id, {
        tenant_id: tenantIdForDelivery,
        phone_number: tenantIdForDelivery ? undefined : sendPhone,
      })
    },
    onSuccess: async (delivery) => {
      setError(null)
      setNotice(
        delivery.error
          ? `WhatsApp could not deliver it: ${delivery.error}`
          : `Sent to ${delivery.recipient} on WhatsApp.`,
      )
      setSendFor(null)
      setSendPhone('')
      await refresh()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const history = useQuery({
    queryKey: ['vault', 'versions', historyFor?.id],
    queryFn: () => vaultApi.versions(historyFor!.id),
    enabled: historyFor !== null,
  })

  if (vault.isPending) return <PageLoader />
  if (vault.isError) return <Alert tone="danger">{errorMessage(vault.error)}</Alert>

  const data = vault.data
  const uploadable = categories.data?.uploadable ?? []
  const order =
    entityType === 'tenant' ? categories.data?.tenant_order : categories.data?.property_order

  return (
    <div className="space-y-4">
      {error && <Alert tone="danger">{error}</Alert>}
      {notice && <Alert tone="success">{notice}</Alert>}

      <Card>
        <CardHeader className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>{title}</CardTitle>
            <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>
          </div>
          <Button
            icon={<UploadIcon className="h-4 w-4" />}
            onClick={() => {
              setError(null)
              setUploadCategory(uploadable[0] ?? 'other')
              setUploadOpen(true)
            }}
          >
            Add a document
          </Button>
        </CardHeader>
        <CardBody className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto]">
            <Field label="Search">
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Name, description or tag"
                aria-label="Search documents"
              />
            </Field>
            <Field label="Type">
              <Select value={category} onChange={(event) => setCategory(event.target.value)}>
                <option value="">All types</option>
                {(order ?? []).map((name) => (
                  <option key={name} value={name}>
                    {humanize(name)}
                  </option>
                ))}
              </Select>
            </Field>
            <label className="flex items-end gap-2 pb-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={includeArchived}
                onChange={(event) => setIncludeArchived(event.target.checked)}
                className="h-4 w-4 rounded border-slate-300"
              />
              Show archived
            </label>
          </div>

          <p className="text-xs text-slate-500">
            <Search className="mr-1 inline h-3.5 w-3.5" />
            {data.document_count} document{data.document_count === 1 ? '' : 's'} ·{' '}
            {fileSize(data.total_bytes)} stored · download links expire after 60 minutes
          </p>
        </CardBody>
      </Card>

      {data.sections.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-6 w-6" />}
          title="Nothing here yet"
          description={
            search || category
              ? 'No document matches that filter.'
              : 'Documents appear here automatically as they are generated, and you can add your own.'
          }
        />
      ) : (
        data.sections.map((section) => (
          <Card key={section.category}>
            <CardHeader>
              <CardTitle className="text-base">
                {humanize(section.category)}
                <span className="ml-2 text-sm font-normal text-slate-400">{section.count}</span>
              </CardTitle>
            </CardHeader>
            <CardBody className="divide-y divide-slate-100">
              {section.documents.map((document) => (
                <div
                  key={document.id}
                  className="flex flex-wrap items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-900">
                      {document.filename}
                      {document.version > 1 && (
                        <span className="ml-2 text-xs font-normal text-slate-400">
                          v{document.version}
                        </span>
                      )}
                      {document.is_archived && (
                        <Badge tone="neutral" className="ml-2">
                          Archived
                        </Badge>
                      )}
                    </p>
                    {document.description && (
                      <p className="mt-0.5 text-sm text-slate-600">{document.description}</p>
                    )}
                    <p className="mt-0.5 text-xs text-slate-400">
                      {dateTime(document.uploaded_at)} · {fileSize(document.size_bytes)}
                    </p>
                    {document.tags.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {document.tags.map((tag) => (
                          <Badge key={tag} tone="neutral">
                            <Tag className="mr-1 inline h-3 w-3" />
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    <a
                      href={document.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-brand-700 hover:bg-brand-50"
                    >
                      <Download className="h-3.5 w-3.5" />
                      Download
                    </a>
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={<History className="h-3.5 w-3.5" />}
                      onClick={() => setHistoryFor(document)}
                    >
                      History
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      icon={<Send className="h-3.5 w-3.5" />}
                      onClick={() => {
                        setError(null)
                        setSendFor(document)
                      }}
                    >
                      Send
                    </Button>
                    {!document.is_archived && (
                      <>
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<UploadIcon className="h-3.5 w-3.5" />}
                          onClick={() => {
                            setError(null)
                            setReplaceFor(document)
                          }}
                        >
                          Replace
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<Archive className="h-3.5 w-3.5" />}
                          onClick={() => archive.mutate(document.id)}
                        >
                          Archive
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </CardBody>
          </Card>
        ))
      )}

      <Dialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        title="Add a document"
        description="It is stored encrypted and only reachable through a link that expires in an hour."
        footer={
          <>
            <Button variant="ghost" onClick={() => setUploadOpen(false)}>
              Cancel
            </Button>
            <Button
              loading={upload.isPending}
              disabled={!uploadFile}
              onClick={() => upload.mutate()}
            >
              Add to vault
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="File" required hint="JPG, PNG, PDF, DOC or DOCX · up to 10MB">
            <Input
              type="file"
              accept="image/jpeg,image/png,image/webp,application/pdf,.doc,.docx"
              onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
            />
          </Field>
          <Field label="Type" required>
            <Select
              value={uploadCategory}
              onChange={(event) => setUploadCategory(event.target.value)}
            >
              {uploadable.map((name) => (
                <option key={name} value={name}>
                  {humanize(name)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Tags" hint="Comma separated, e.g. original, LR 209/1234">
            <Input value={uploadTags} onChange={(event) => setUploadTags(event.target.value)} />
          </Field>
          <Field label="Description">
            <Textarea
              rows={2}
              value={uploadDescription}
              onChange={(event) => setUploadDescription(event.target.value)}
            />
          </Field>
        </div>
      </Dialog>

      <Dialog
        open={replaceFor !== null}
        onClose={() => setReplaceFor(null)}
        title="Replace this document"
        description={
          replaceFor
            ? `${replaceFor.filename} becomes version ${replaceFor.version + 1}. The current one is kept in the history.`
            : undefined
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setReplaceFor(null)}>
              Cancel
            </Button>
            <Button
              loading={replace.isPending}
              disabled={!replaceFile}
              onClick={() => replace.mutate()}
            >
              Save new version
            </Button>
          </>
        }
      >
        <Field label="Replacement file" required>
          <Input
            type="file"
            accept="image/jpeg,image/png,image/webp,application/pdf,.doc,.docx"
            onChange={(event) => setReplaceFile(event.target.files?.[0] ?? null)}
          />
        </Field>
      </Dialog>

      <Dialog
        open={historyFor !== null}
        onClose={() => setHistoryFor(null)}
        title="Version history"
        description={historyFor?.filename}
        footer={
          <Button variant="ghost" onClick={() => setHistoryFor(null)}>
            Close
          </Button>
        }
      >
        {history.isPending ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : (
          <ol className="space-y-3">
            {(history.data ?? []).map((version, index) => (
              <li key={version.id} className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-slate-900">
                    Version {version.version}
                    {index === 0 && (
                      <Badge tone="success" className="ml-2">
                        Current
                      </Badge>
                    )}
                  </p>
                  <p className="text-xs text-slate-500">{version.filename}</p>
                  <p className="text-xs text-slate-400">
                    {dateTime(version.uploaded_at)} · {fileSize(version.size_bytes)}
                  </p>
                </div>
                <a
                  href={version.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-sm text-brand-700 hover:underline"
                >
                  Download
                </a>
              </li>
            ))}
          </ol>
        )}
      </Dialog>

      <Dialog
        open={sendFor !== null}
        onClose={() => setSendFor(null)}
        title="Send on WhatsApp"
        description={sendFor ? `${sendFor.filename} goes out as a PDF attachment.` : undefined}
        footer={
          <>
            <Button variant="ghost" onClick={() => setSendFor(null)}>
              Cancel
            </Button>
            <Button
              loading={send.isPending}
              disabled={!tenantIdForDelivery && sendPhone.trim().length < 9}
              onClick={() => send.mutate()}
            >
              Send
            </Button>
          </>
        }
      >
        {tenantIdForDelivery ? (
          <p className="text-sm text-slate-600">
            It will be sent to the tenant's number on file and recorded against their name.
          </p>
        ) : (
          <Field label="WhatsApp number" required>
            <Input
              value={sendPhone}
              onChange={(event) => setSendPhone(event.target.value)}
              placeholder="+254 7XX XXX XXX"
            />
          </Field>
        )}
      </Dialog>
    </div>
  )
}
