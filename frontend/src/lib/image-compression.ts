/**
 * Photo compression in the browser, before a byte leaves the device.
 *
 * A current phone writes 4–12MB per shot, and the storage an agency pays for is
 * capped in gigabytes: a caretaker photographing forty meters on the first of
 * the month would spend a fifth of a Starter plan's allowance in one morning.
 * Nearly all of it is resolution nobody ever looks at — a meter reading, a
 * cracked tile, a title deed are all legible well below 12 megapixels — so an
 * image is decoded, downscaled and re-encoded here first. A phone photo
 * normally leaves at 3–8% of what came off the camera, which the field
 * connection feels as much as the storage bill does.
 *
 * Nothing in here throws. A file the browser cannot decode (a HEIC where there
 * is no HEIC decoder, something truncated) is passed through untouched for the
 * server to accept or refuse: a failed compression must never be the reason a
 * caretaker cannot record a reading.
 */

export interface CompressOptions {
  /** Longest edge, in pixels, after downscaling. */
  maxEdge?: number
  /** Encoder quality to start at, 0–1. */
  quality?: number
  /** Re-encode at a lower quality while the result is still above this. */
  targetBytes?: number
  /** An image needing no downscale and already under this is left alone. */
  skipUnderBytes?: number
}

export interface CompressedImage {
  /** What to upload — the re-encoded image, or the original file untouched. */
  blob: Blob
  /** `filename` and `contentType` always describe `blob`, not the input. */
  filename: string
  contentType: string
  originalBytes: number
  bytes: number
  compressed: boolean
}

/**
 * Field photos: meters, faults, inspections, ID pages. 1600px is roughly twice
 * what a phone screen shows and comfortably enough to read a meter dial off.
 */
export const PHOTO_COMPRESSION: Required<CompressOptions> = {
  maxEdge: 1600,
  quality: 0.82,
  targetBytes: 600 * 1024,
  skipUnderBytes: 400 * 1024,
}

/**
 * Photographed paperwork — title deeds, signed leases — going into the vault.
 * A longer edge and a higher quality than a field photo, because these are read
 * rather than glanced at and the small print has to survive.
 */
export const SCAN_COMPRESSION: Required<CompressOptions> = {
  maxEdge: 2400,
  quality: 0.88,
  targetBytes: 1200 * 1024,
  skipUnderBytes: 700 * 1024,
}

/** Types worth handing to a decoder. HEIC is here because Safari can decode it,
 *  and re-encoding turns a file the API would reject into one it accepts. */
const DECODABLE = new Set(['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'])

/** Types the API already accepts, so a small one can be left exactly as it is. */
const STORABLE_AS_IS = new Set(['image/jpeg', 'image/png', 'image/webp'])

const EXTENSIONS: Record<string, string> = {
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/webp': '.webp',
}

/**
 * The name has to describe the bytes: the API builds the storage key's
 * extension from it, and the vault hangs its download link off it. A PNG
 * re-encoded as WebP that is still called `deed.png` downloads as a file
 * Windows refuses to open.
 */
export function renameForType(filename: string, contentType: string): string {
  const extension = EXTENSIONS[contentType]
  if (!extension) return filename
  const dot = filename.lastIndexOf('.')
  const stem = dot > 0 ? filename.slice(0, dot) : filename
  return `${stem}${extension}`
}

function untouched(file: File): CompressedImage {
  return {
    blob: file,
    filename: file.name,
    contentType: file.type || 'application/octet-stream',
    originalBytes: file.size,
    bytes: file.size,
    compressed: false,
  }
}

function encode(canvas: HTMLCanvasElement, type: string, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => {
    try {
      canvas.toBlob(resolve, type, quality)
    } catch {
      resolve(null)
    }
  })
}

let webpProbe: Promise<boolean> | null = null

/** WebP is ~30% smaller than JPEG at the same quality and keeps transparency,
 *  so it is the default output wherever the browser can actually produce it. */
function canEncodeWebp(): Promise<boolean> {
  webpProbe ??= (async () => {
    try {
      const canvas = document.createElement('canvas')
      canvas.width = 1
      canvas.height = 1
      const blob = await encode(canvas, 'image/webp', 0.8)
      return blob?.type === 'image/webp'
    } catch {
      return false
    }
  })()
  return webpProbe
}

interface Decoded {
  source: CanvasImageSource
  width: number
  height: number
  release: () => void
}

/** `imageOrientation` is what keeps a portrait phone photo upright: the camera
 *  records rotation in EXIF, and a canvas that ignores it saves it sideways. */
async function decode(file: File): Promise<Decoded | null> {
  if (typeof createImageBitmap === 'function') {
    try {
      const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
      return {
        source: bitmap,
        width: bitmap.width,
        height: bitmap.height,
        release: () => bitmap.close(),
      }
    } catch {
      // Falls through to the element path, which is the only one that decodes
      // HEIC on Safari and the only one older browsers implement at all.
    }
  }
  return decodeViaElement(file)
}

function decodeViaElement(file: File): Promise<Decoded | null> {
  if (typeof URL?.createObjectURL !== 'function') return Promise.resolve(null)

  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () =>
      resolve({
        source: image,
        width: image.naturalWidth || image.width,
        height: image.naturalHeight || image.height,
        release: () => URL.revokeObjectURL(url),
      })
    image.onerror = () => {
      URL.revokeObjectURL(url)
      resolve(null)
    }
    image.src = url
  })
}

/** Three passes at most. An image still over target at the bottom of the ladder
 *  is detail-heavy, and grinding lower costs visible quality for a few KB. */
function qualityLadder(start: number): number[] {
  const steps = [start, start - 0.15, start - 0.3].map(
    (quality) => Math.round(Math.min(0.95, Math.max(0.4, quality)) * 100) / 100,
  )
  return [...new Set(steps)]
}

/**
 * Shrink an image for upload. Anything that is not a decodable image — a PDF, a
 * Word document, a file type nobody here knows — comes back untouched, so this
 * is safe to put in front of every upload rather than only the photo ones.
 */
export async function compressImage(file: File, options: CompressOptions = {}): Promise<CompressedImage> {
  const { maxEdge, quality, targetBytes, skipUnderBytes } = { ...PHOTO_COMPRESSION, ...options }
  if (!DECODABLE.has(file.type)) return untouched(file)

  const decoded = await decode(file)
  if (!decoded) return untouched(file)

  try {
    const { width, height } = decoded
    if (!width || !height) return untouched(file)

    const scale = Math.min(1, maxEdge / Math.max(width, height))
    // Already small in both senses: re-encoding would cost more quality than
    // the handful of bytes it saves. HEIC never qualifies — the API rejects it,
    // so it has to be re-encoded whatever its size.
    if (scale === 1 && file.size <= skipUnderBytes && STORABLE_AS_IS.has(file.type)) {
      return untouched(file)
    }

    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(width * scale))
    canvas.height = Math.max(1, Math.round(height * scale))
    const context = canvas.getContext('2d')
    if (!context) return untouched(file)

    const type = (await canEncodeWebp()) ? 'image/webp' : 'image/jpeg'
    if (type === 'image/jpeg') {
      // JPEG has no alpha channel, and an unpainted canvas is transparent — a
      // scan saved as a transparent PNG would come out on solid black.
      context.fillStyle = '#ffffff'
      context.fillRect(0, 0, canvas.width, canvas.height)
    }
    context.drawImage(decoded.source, 0, 0, canvas.width, canvas.height)

    let best: Blob | null = null
    for (const step of qualityLadder(quality)) {
      const blob = await encode(canvas, type, step)
      if (!blob) break
      if (!best || blob.size < best.size) best = blob
      if (blob.size <= targetBytes) break
    }

    // A small PNG of flat colour can encode larger than it started; keep
    // whichever is actually smaller.
    if (!best || best.size >= file.size) return untouched(file)

    const contentType = best.type || type
    return {
      blob: best,
      filename: renameForType(file.name, contentType),
      contentType,
      originalBytes: file.size,
      bytes: best.size,
      compressed: true,
    }
  } catch {
    // Any surprise from the canvas — a tainted source, an out-of-memory on a
    // very large image — leaves the upload to proceed with the original.
    return untouched(file)
  } finally {
    decoded.release()
  }
}
