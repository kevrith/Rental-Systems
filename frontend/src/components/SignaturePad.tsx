/**
 * SignaturePad — touch and mouse-friendly canvas for capturing a digital
 * signature as a base64 PNG data URL.
 *
 * Usage:
 *   <SignaturePad value={sig} onChange={setSig} />
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui'

interface SignaturePadProps {
  value: string | null
  onChange: (value: string | null) => void
  className?: string
  height?: number
  disabled?: boolean
}

export function SignaturePad({
  value,
  onChange,
  className = '',
  height = 180,
  disabled = false,
}: SignaturePadProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const drawing = useRef(false)
  const lastPos = useRef<{ x: number; y: number } | null>(null)
  const [isEmpty, setIsEmpty] = useState(!value)

  // Set up the canvas backing store once, sized to the rendered element.
  // useLayoutEffect runs synchronously after the DOM is painted so
  // getBoundingClientRect() returns the real dimensions.
  useLayoutEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    const cssWidth = canvas.offsetWidth
    const cssHeight = height

    canvas.width = cssWidth * dpr
    canvas.height = cssHeight * dpr

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.strokeStyle = '#1e293b'
    ctx.lineWidth = 1.8
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    // Restore saved signature after resize.
    if (value) {
      const img = new Image()
      img.onload = () => ctx.drawImage(img, 0, 0, cssWidth, cssHeight)
      img.src = value
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [height]) // intentionally excludes `value` — only re-init on height change

  // When a saved value is passed in from outside (initial load / clear),
  // draw it onto the already-scaled canvas.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const dpr = window.devicePixelRatio || 1

    if (value) {
      const img = new Image()
      img.onload = () => {
        ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr)
        ctx.drawImage(img, 0, 0, canvas.width / dpr, canvas.height / dpr)
        setIsEmpty(false)
      }
      img.src = value
    } else {
      ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr)
      setIsEmpty(true)
    }
  }, [value])

  const getPos = (e: React.MouseEvent | React.TouchEvent): { x: number; y: number } | null => {
    const canvas = canvasRef.current
    if (!canvas) return null
    const rect = canvas.getBoundingClientRect()
    if ('touches' in e) {
      if (e.touches.length === 0) return null
      return {
        x: e.touches[0].clientX - rect.left,
        y: e.touches[0].clientY - rect.top,
      }
    }
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  const startDrawing = useCallback(
    (e: React.MouseEvent | React.TouchEvent) => {
      if (disabled) return
      e.preventDefault()
      drawing.current = true
      lastPos.current = getPos(e)
    },
    [disabled],
  )

  const draw = useCallback(
    (e: React.MouseEvent | React.TouchEvent) => {
      if (!drawing.current || disabled) return
      e.preventDefault()
      const canvas = canvasRef.current
      const ctx = canvas?.getContext('2d')
      if (!canvas || !ctx) return
      const pos = getPos(e)
      if (!pos || !lastPos.current) return

      // Quadratic curve through the midpoint gives smooth, natural strokes
      // instead of jagged straight-line segments.
      const mid = {
        x: (lastPos.current.x + pos.x) / 2,
        y: (lastPos.current.y + pos.y) / 2,
      }
      ctx.beginPath()
      ctx.moveTo(lastPos.current.x, lastPos.current.y)
      ctx.quadraticCurveTo(lastPos.current.x, lastPos.current.y, mid.x, mid.y)
      ctx.stroke()

      lastPos.current = pos
      setIsEmpty(false)
    },
    [disabled],
  )

  const endDrawing = useCallback(
    (e: React.MouseEvent | React.TouchEvent) => {
      if (!drawing.current) return
      e.preventDefault()
      drawing.current = false
      lastPos.current = null
      const canvas = canvasRef.current
      if (!canvas) return

      // Export at CSS dimensions so the saved PNG matches what was drawn.
      const dpr = window.devicePixelRatio || 1
      const cssWidth = canvas.width / dpr
      const cssHeight = canvas.height / dpr
      const out = document.createElement('canvas')
      out.width = cssWidth
      out.height = cssHeight
      const outCtx = out.getContext('2d')
      outCtx?.drawImage(canvas, 0, 0, canvas.width, canvas.height, 0, 0, cssWidth, cssHeight)
      onChange(out.toDataURL('image/png'))
    },
    [onChange],
  )

  const clear = useCallback(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    const dpr = window.devicePixelRatio || 1
    ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr)
    setIsEmpty(true)
    onChange(null)
  }, [onChange])

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <div
        className={`relative overflow-hidden rounded-lg border-2 ${
          disabled
            ? 'border-slate-200 bg-slate-50'
            : 'border-slate-300 bg-white hover:border-brand-400'
        }`}
        style={{ height }}
      >
        <canvas
          ref={canvasRef}
          style={{ width: '100%', height: '100%', display: 'block', touchAction: 'none' }}
          onMouseDown={startDrawing}
          onMouseMove={draw}
          onMouseUp={endDrawing}
          onMouseLeave={endDrawing}
          onTouchStart={startDrawing}
          onTouchMove={draw}
          onTouchEnd={endDrawing}
        />
        {isEmpty && !disabled && (
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-slate-400 select-none">
            Draw your signature here
          </span>
        )}
        {disabled && value && (
          <img
            src={value}
            alt="Saved signature"
            className="absolute inset-0 h-full w-full object-contain p-2"
          />
        )}
      </div>
      {!disabled && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-400">
            {isEmpty ? 'Use your mouse or finger to sign' : 'Clear and redraw if needed'}
          </p>
          <Button type="button" variant="ghost" size="sm" onClick={clear} disabled={isEmpty}>
            Clear
          </Button>
        </div>
      )}
    </div>
  )
}
