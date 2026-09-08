import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * jsdom has no canvas and no image decoder, so both are stood up here: a
 * `toBlob` that reports a size per quality step and a `createImageBitmap` that
 * reports dimensions. That is enough to pin down the decisions this module
 * actually makes — when to downscale, when to step quality down, when to give
 * up and upload the original — without needing real pixels.
 */

/** The module caches its WebP probe, so each test imports a fresh copy. */
async function freshModule() {
  vi.resetModules()
  return import('@/lib/image-compression')
}

function fileOf(name: string, type: string, size: number): File {
  const file = new File(['x'], name, { type })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

function blobOf(type: string, size: number): Blob {
  const blob = new Blob(['x'], { type })
  Object.defineProperty(blob, 'size', { value: size })
  return blob
}

let supportsWebp = true
let sizeAtQuality: (quality: number) => number | null
let encodes: { type: string; quality: number; width: number }[]
let painted: string[]
let drawnAt: { width: number; height: number } | null
let bitmapOptions: ImageBitmapOptions | undefined

beforeEach(() => {
  supportsWebp = true
  sizeAtQuality = () => 300 * 1024
  encodes = []
  painted = []
  drawnAt = null
  bitmapOptions = undefined

  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    fillStyle: '',
    fillRect: () => painted.push('filled'),
    drawImage: (_source: unknown, _x: number, _y: number, width: number, height: number) => {
      drawnAt = { width, height }
    },
  } as unknown as CanvasRenderingContext2D)

  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function (
    this: HTMLCanvasElement,
    callback: BlobCallback,
    type?: string,
    quality?: number,
  ) {
    // A browser without a WebP encoder silently hands back a PNG instead.
    const produced = type === 'image/webp' && !supportsWebp ? 'image/png' : (type ?? 'image/png')
    encodes.push({ type: produced, quality: quality ?? 0.92, width: this.width })
    const size = sizeAtQuality(quality ?? 0.92)
    callback(size === null ? null : blobOf(produced, size))
  })
})

/** The module probes WebP support by encoding a 1x1 canvas; that pass is not
 *  one of the image's own encodes and would otherwise skew every assertion. */
function imageEncodes() {
  return encodes.filter((call) => call.width > 1)
}

function stubBitmap(width: number, height: number) {
  vi.stubGlobal(
    'createImageBitmap',
    vi.fn(async (_file: Blob, options?: ImageBitmapOptions) => {
      bitmapOptions = options
      return { width, height, close: vi.fn() } as unknown as ImageBitmap
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('compressImage', () => {
  it('downscales a phone photo and re-encodes it as WebP', async () => {
    const { compressImage } = await freshModule()
    stubBitmap(4032, 3024)
    sizeAtQuality = () => 280 * 1024

    const result = await compressImage(fileOf('meter.jpg', 'image/jpeg', 5 * 1024 * 1024))

    expect(result.compressed).toBe(true)
    expect(result.contentType).toBe('image/webp')
    expect(result.filename).toBe('meter.webp')
    expect(result.originalBytes).toBe(5 * 1024 * 1024)
    expect(result.bytes).toBe(280 * 1024)
    // 4032x3024 fits inside a 1600px longest edge at 0.397, so 1600x1200.
    expect(drawnAt).toEqual({ width: 1600, height: 1200 })
  })

  it('asks the decoder to honour EXIF, so portrait photos stay upright', async () => {
    const { compressImage } = await freshModule()
    stubBitmap(3024, 4032)

    await compressImage(fileOf('fault.jpg', 'image/jpeg', 4 * 1024 * 1024))

    expect(bitmapOptions).toEqual({ imageOrientation: 'from-image' })
    expect(drawnAt).toEqual({ width: 1200, height: 1600 })
  })

  it('steps the quality down until the result is under target', async () => {
    const { compressImage } = await freshModule()
    stubBitmap(4032, 3024)
    // Only the third rung comes in under the 600KB photo target.
    sizeAtQuality = (quality) => (quality > 0.7 ? 900 * 1024 : quality > 0.55 ? 700 * 1024 : 480 * 1024)

    const result = await compressImage(fileOf('wall.jpg', 'image/jpeg', 6 * 1024 * 1024))

    expect(imageEncodes().map((call) => call.quality)).toEqual([0.82, 0.67, 0.52])
    expect(result.bytes).toBe(480 * 1024)
  })

  it('leaves a PDF alone rather than trying to decode it', async () => {
    const { compressImage } = await freshModule()
    stubBitmap(1000, 1000)

    const pdf = fileOf('lease.pdf', 'application/pdf', 2 * 1024 * 1024)
    const result = await compressImage(pdf)

    expect(result.compressed).toBe(false)
    expect(result.blob).toBe(pdf)
    expect(result.filename).toBe('lease.pdf')
    expect(imageEncodes()).toHaveLength(0)
  })

  it('leaves an image that is already small and in-spec exactly as it is', async () => {
    const { compressImage } = await freshModule()
    stubBitmap(1200, 900)

    const small = fileOf('receipt.png', 'image/png', 120 * 1024)
    const result = await compressImage(small)

    expect(result.compressed).toBe(false)
    expect(result.blob).toBe(small)
    expect(imageEncodes()).toHaveLength(0)
  })

  it('re-encodes a small HEIC anyway, because the API will not store one', async () => {
    const { compressImage } = await freshModule()
    stubBitmap(1200, 900)
    sizeAtQuality = () => 90 * 1024

    const result = await compressImage(fileOf('IMG_0421.heic', 'image/heic', 110 * 1024))

    expect(result.compressed).toBe(true)
    expect(result.contentType).toBe('image/webp')
    expect(result.filename).toBe('IMG_0421.webp')
  })

  it('paints a white ground and falls back to JPEG where WebP cannot be encoded', async () => {
    const { compressImage } = await freshModule()
    stubBitmap(2000, 1500)
    supportsWebp = false
    sizeAtQuality = () => 200 * 1024

    const result = await compressImage(fileOf('signed.png', 'image/png', 3 * 1024 * 1024))

    expect(result.contentType).toBe('image/jpeg')
    expect(result.filename).toBe('signed.jpg')
    // Without this a transparent PNG would be saved on solid black.
    expect(painted).toContain('filled')
  })

  it('keeps the original when the re-encode comes out no smaller', async () => {
    const { compressImage } = await freshModule()
    stubBitmap(1800, 1400)
    sizeAtQuality = () => 900 * 1024

    const original = fileOf('flat.png', 'image/png', 800 * 1024)
    const result = await compressImage(original)

    expect(result.compressed).toBe(false)
    expect(result.blob).toBe(original)
  })

  it('uploads the original untouched when nothing can decode the file', async () => {
    const { compressImage } = await freshModule()
    vi.stubGlobal(
      'createImageBitmap',
      vi.fn(async () => {
        throw new Error('The source image cannot be decoded')
      }),
    )
    // No object URLs either, so the <img> fallback cannot run: a caretaker must
    // still be able to upload, and the server has the final say on the file.
    const objectUrl = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
    Object.defineProperty(URL, 'createObjectURL', { value: undefined, configurable: true })

    const original = fileOf('IMG_0500.heic', 'image/heic', 4 * 1024 * 1024)
    await expect(compressImage(original)).resolves.toMatchObject({
      blob: original,
      compressed: false,
      bytes: 4 * 1024 * 1024,
    })

    if (objectUrl) Object.defineProperty(URL, 'createObjectURL', objectUrl)
  })

  it('falls back to an image element when createImageBitmap is unavailable', async () => {
    const { compressImage } = await freshModule()
    vi.stubGlobal('createImageBitmap', undefined)
    vi.stubGlobal(
      'Image',
      class {
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        naturalWidth = 3000
        naturalHeight = 2000
        width = 3000
        height = 2000
        set src(_value: string) {
          queueMicrotask(() => this.onload?.())
        }
      },
    )
    const revoke = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:photo', configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: revoke, configurable: true })
    sizeAtQuality = () => 250 * 1024

    const result = await compressImage(fileOf('unit.jpg', 'image/jpeg', 4 * 1024 * 1024))

    expect(result.compressed).toBe(true)
    expect(drawnAt).toEqual({ width: 1600, height: 1067 })
    // The object URL is released either way, or a long capture session leaks.
    expect(revoke).toHaveBeenCalled()
  })

  it('gives scans a longer edge than field photos, so small print survives', async () => {
    const { compressImage, SCAN_COMPRESSION } = await freshModule()
    stubBitmap(4000, 3000)
    sizeAtQuality = () => 400 * 1024

    await compressImage(fileOf('deed.jpg', 'image/jpeg', 5 * 1024 * 1024), SCAN_COMPRESSION)

    expect(drawnAt).toEqual({ width: 2400, height: 1800 })
    expect(imageEncodes()[0].quality).toBe(0.88)
  })
})

describe('renameForType', () => {
  it('swaps the extension to match the bytes that were actually encoded', async () => {
    const { renameForType } = await freshModule()

    expect(renameForType('deed.png', 'image/webp')).toBe('deed.webp')
    expect(renameForType('scan.JPEG', 'image/jpeg')).toBe('scan.jpg')
    expect(renameForType('no-extension', 'image/webp')).toBe('no-extension.webp')
    expect(renameForType('lease.v2.png', 'image/jpeg')).toBe('lease.v2.jpg')
  })

  it('leaves the name alone for a type it does not encode', async () => {
    const { renameForType } = await freshModule()

    expect(renameForType('lease.pdf', 'application/pdf')).toBe('lease.pdf')
  })
})
