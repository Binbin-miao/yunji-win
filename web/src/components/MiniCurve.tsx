import { useEffect, useRef } from 'react'
import { F_MAX, F_MIN, curve, dbToRatio, freqToRatio, type EqBand } from '../domain/eq'

/** 预设列表里的缩略曲线，只画曲线本身 */
export default function MiniCurve({ bands, width = 96, height = 40 }: { bands: EqBand[]; width?: number; height?: number }) {
  const ref = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, width, height)

    // 0 dB 基线
    ctx.strokeStyle = 'rgba(196,164,255,0.16)'
    ctx.beginPath()
    ctx.moveTo(0, height / 2)
    ctx.lineTo(width, height / 2)
    ctx.stroke()

    const { freqs, dbs } = curve(bands, 80)
    const range = 12
    ctx.beginPath()
    freqs.forEach((f, i) => {
      const x = freqToRatio(f, F_MIN, F_MAX) * width
      const y = dbToRatio(dbs[i], range) * height
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.strokeStyle = '#C9A6FF'
    ctx.lineWidth = 1.4
    ctx.stroke()
  }, [bands, width, height])

  return <canvas ref={ref} className="mini-curve" aria-hidden="true" />
}
