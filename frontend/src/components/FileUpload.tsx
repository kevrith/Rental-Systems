import { Camera, ImagePlus, Loader2, Upload, X } from 'lucide-react'
import { useCallback, useId, useRef, useState } from 'react'

import { filesApi } from '@/api'
import { API_BASE_URL } from '@/lib/api-client'
import { cn } from '@/lib/cn'
import { errorMessage } from '@/lib/format'

export interface UploadedFile {
  id: string
  url: string
  filename: string
}

const ACCEPTED = 'image/jpeg,image/png,image/webp,application/pdf'
const MAX_BYTES = 10 * 1024 * 1024
/** Photos are downscaled in the browser: a 12MP phone shot is ~5MB, and a
 *  caretaker on 3G should not be uploading that to record a meter reading. */
const MAX_IMAGE_EDGE = 1600
const JPEG_QUALITY = 0.82

async function compressImage(file: File): Promise<Blob> {
  if (!file.type.startsWith('image/') || file.type === 'image/webp') return file

  const bitmap = await createImageBitmap(file)
  const scale = Math.min(1, MAX_IMAGE_EDGE / Math.max(bitmap.width, bitmap.height))
  if (scale === 1 && file.size <= 1_500_000) return file

  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  const context = canvas.getContext('2d')
  if (!context) return file
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)

  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY),
  )
  bitmap.close()
  return blob && blob.size < file.size ? blob : file
}

/**
 * Direct-to-storage upload (US-012).
 *
 * The API only ever issues a pre-signed URL and records the result — the bytes
 * go straight from the browser to Cloudflare R2. In development the same three
 * steps run against the local storage endpoint, so this component behaves
 * identically offline of R2.
 */
export function FileUpload({
  value,
  onChange,
  category = 'other',
  max = 5,
  label,
  hint,
  capture,
  className,
}: {
  value: UploadedFile[]
  onChange: (files: UploadedFile[]) => void
  category?: string
  max?: number
  label?: string
  hint?: string
  /** Opens the rear camera directly — used for meter photos and fault photos. */
  capture?: boolean
  className?: string
}) {
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const uploadOne = useCallback(
    async (file: File): Promise<UploadedFile | null> => {
      const payload = await compressImage(file)
      if (payload.size > MAX_BYTES) {
        setError(`${file.name} is larger than 10MB.`)
        return null
      }

      const contentType = payload.type || file.type || 'application/octet-stream'
      const ticket = await filesApi.requestUpload({
        filename: file.name,
        content_type: contentType,
        size_bytes: payload.size,
        category,
      })

      // Local development returns an app-relative path; R2 returns an absolute URL.
      const destination = ticket.upload_url.startsWith('http')
        ? ticket.upload_url
        : `${API_BASE_URL.replace(/\/api\/v1$/, '')}${ticket.upload_url}`

      const response = await fetch(destination, {
        method: ticket.method,
        headers: ticket.headers,
        body: payload,
      })
      if (!response.ok) throw new Error(`Upload failed (${response.status})`)

      const confirmed = await filesApi.confirm(ticket.file_id, payload.size)
      return { id: ticket.file_id, url: confirmed.url, filename: file.name }
    },
    [category],
  )

  const handleFiles = async (fileList: FileList | null) => {
    if (!fileList?.length) return
    setError(null)

    const room = max - value.length
    const files = Array.from(fileList).slice(0, Math.max(0, room))
    if (files.length < fileList.length) {
      setError(`You can attach at most ${max} file(s).`)
    }

    setUploading(files.length)
    const uploaded: UploadedFile[] = []
    for (const file of files) {
      try {
        const result = await uploadOne(file)
        if (result) uploaded.push(result)
      } catch (uploadError) {
        setError(errorMessage(uploadError, `Could not upload ${file.name}.`))
      } finally {
        setUploading((count) => count - 1)
      }
    }

    if (uploaded.length) onChange([...value, ...uploaded])
    if (inputRef.current) inputRef.current.value = ''
  }

  const remove = (id: string) => onChange(value.filter((file) => file.id !== id))
  const full = value.length >= max

  return (
    <div className={cn('space-y-2', className)}>
      {label && <p className="text-sm font-medium text-slate-700">{label}</p>}

      <div className="flex flex-wrap gap-2">
        {value.map((file) => (
          <div
            key={file.id}
            className="group relative h-20 w-20 overflow-hidden rounded-lg border border-slate-200 bg-slate-50"
          >
            {file.filename.toLowerCase().endsWith('.pdf') ? (
              <div className="flex h-full w-full items-center justify-center text-[10px] text-slate-500">
                PDF
              </div>
            ) : (
              <img src={file.url} alt={file.filename} className="h-full w-full object-cover" />
            )}
            <button
              type="button"
              onClick={() => remove(file.id)}
              aria-label={`Remove ${file.filename}`}
              className="absolute right-1 top-1 rounded-full bg-slate-900/70 p-0.5 text-white opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}

        {uploading > 0 &&
          Array.from({ length: uploading }).map((_, index) => (
            <div
              key={`uploading-${index}`}
              className="flex h-20 w-20 items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50"
            >
              <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
            </div>
          ))}

        {!full && (
          <label
            htmlFor={inputId}
            data-touch-target
            className="flex h-20 w-20 cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-slate-300 text-slate-400 transition-colors hover:border-brand-400 hover:text-brand-500"
          >
            {capture ? <Camera className="h-5 w-5" /> : <ImagePlus className="h-5 w-5" />}
            <span className="text-[10px]">{capture ? 'Take photo' : 'Add'}</span>
          </label>
        )}
      </div>

      <input
        id={inputId}
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        multiple={max > 1 && !capture}
        capture={capture ? 'environment' : undefined}
        className="sr-only"
        onChange={(event) => void handleFiles(event.target.files)}
      />

      {error ? (
        <p className="text-sm text-danger-600">{error}</p>
      ) : hint ? (
        <p className="text-xs text-slate-500">{hint}</p>
      ) : (
        <p className="text-xs text-slate-400">
          JPG, PNG or PDF · up to 10MB each · {value.length}/{max} attached
        </p>
      )}
    </div>
  )
}

/** Single-file variant for the required meter photo. */
export function SinglePhotoUpload({
  value,
  onChange,
  category,
  label,
  hint,
  required,
}: {
  value: UploadedFile | null
  onChange: (file: UploadedFile | null) => void
  category?: string
  label?: string
  hint?: string
  required?: boolean
}) {
  return (
    <div>
      {label && (
        <p className="mb-2 text-sm font-medium text-slate-700">
          {label}
          {required && <span className="ml-0.5 text-danger-600">*</span>}
        </p>
      )}
      <FileUpload
        value={value ? [value] : []}
        onChange={(files) => onChange(files[0] ?? null)}
        category={category}
        max={1}
        capture
        hint={hint}
      />
    </div>
  )
}

export { Upload }
