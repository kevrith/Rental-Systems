/**
 * SignaturePad — a touch and mouse-friendly canvas for capturing a digital
 * signature as a base64 PNG data URL.
 *
 * Usage:
 *   <SignaturePad value={sig} onChange={setSig} />
 *
 * `value` is a base64 data URL or null. When the user draws, `onChange` is
 * called with the new data URL after each stroke ends. Passing a non-null
 * `value` renders the existing signature; the user can clear and redraw.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui'

interface SignaturePadProps {
  /** Current value — base64 PNG data URL or null. */
  value: string | null
  /** Called with the new data URL after each stroke, or null after clear. */
  onChange: (value: string | null) => void
  /** Tailwind class appended to the outer wrapper. */
  className?: string
  /** Width in pixels. Defaults to the element's rendered width (fluid). */
  width?: number
  /** Height in pixels. Defaults to 180. */
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

  // When a saved value is passed in, draw it onto the canvas.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    if (value) {
      const img = new Image()
      img.onload = () => {
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
        setIsEmpty(false)
      }
      img.src = value
    } else {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      setIsEmpty(true)
    }
  }, [value])

  // Scale the canvas backing store to the device pixel ratio so strokes are
  // crisp on high-DPI screens (retina, etc.).
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = rect.width * dpr
    canvas.height = height * dpr
    const ctx = canvas.getContext('2d')
    if (ctx) {
      ctx.scale(dpr, dpr)
      ctx.strokeStyle = '#1e293b' // slate-800
      ctx.lineWidth = 2
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
    }
    // Re-draw saved value after resize.
    if (value) {
      const img = new Image()
      img.onload = () => ctx?.drawImage(img, 0, 0, rect.width, height)
      img.src = value
    }
  }, [height, value])

  const getPos = (
    e: React.MouseEvent | React.TouchEvent,
  ): { x: number; y: number } | null => {
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
      ctx.beginPath()
      ctx.moveTo(lastPos.current.x, lastPos.current.y)
      ctx.lineTo(pos.x, pos.y)
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
      if (canvas) {
        onChange(canvas.toDataURL('image/png'))
      }
    },
    [onChange],
  )

  const clear = () => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    setIsEmpty(true)
    onChange(null)
  }

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
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={clear}
            disabled={isEmpty}
          >
            Clear
          </Button>
        </div>
      )}
    </div>
  )
}
