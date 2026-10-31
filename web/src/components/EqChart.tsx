import { useEffect, useRef } from 'react'
import { DB_RANGES, F_MAX, F_MIN, curve, dbToRatio, freqToRatio, type EqBand } from '../domain/eq'

const TICKS = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
const LABELS: Record<number, string> = {
  20: '20',
  50: '50',
  100: '100',
  200: '200',
  500: '500',
  1000: '1k',
  2000: '2k',
  5000: '5k',
  10000: '10k',
  20000: '20k',
}

interface Props {
  bands: EqBand[]
  range: (typeof DB_RANGES)[number]
  height?: number
}

/** 只读曲线：网格 + 刻度 + 叠加曲线 + 每段锚点 */
export default function EqChart({ bands, range, height = 300 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const wrapRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return

    const draw = () => {
      const dpr = window.devicePixelRatio || 1
      const w = wrap.clientWidth
      const h = height
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`

      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)

      const padL = 34
      const padR = 12
      const padT = 10
      const padB = 22
      const plotW = w - padL - padR
      const plotH = h - padT - padB
      const x = (f: number) => padL + freqToRatio(f, F_MIN, F_MAX) * plotW
      const y = (db: number) => padT + dbToRatio(db, range) * plotH

      // 网格：竖向频率线
      ctx.strokeStyle = 'rgba(196,164,255,0.10)'
      ctx.lineWidth = 1
      for (const t of TICKS) {
        const px = Math.round(x(t)) + 0.5
        ctx.beginPath()
        ctx.moveTo(px, padT)
        ctx.lineTo(px, padT + plotH)
        ctx.stroke()
      }

      // 网格：横向 dB 线
      const step = range === 12 ? 6 : 3
      for (let db = -range; db <= range; db += step) {
        const py = Math.round(y(db)) + 0.5
        ctx.strokeStyle = db === 0 ? 'rgba(196,164,255,0.24)' : 'rgba(196,164,255,0.08)'
        ctx.beginPath()
        ctx.moveTo(padL, py)
        ctx.lineTo(padL + plotW, py)
        ctx.stroke()
      }

      // 刻度文字
      ctx.fillStyle = 'rgba(167,156,184,0.75)'
      ctx.font = '10px "Cascadia Mono", Consolas, monospace'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      for (const t of TICKS) ctx.fillText(LABELS[t], x(t), padT + plotH + 6)

      ctx.textAlign = 'right'
      ctx.textBaseline = 'middle'
      for (let db = -range; db <= range; db += step) {
        ctx.fillText(db > 0 ? `+${db}` : String(db), padL - 6, y(db))
      }

      // 曲线
      const { freqs, dbs } = curve(bands, 240)
      ctx.beginPath()
      freqs.forEach((f, i) => {
        const px = x(f)
        const py = y(dbs[i])
        if (i === 0) ctx.moveTo(px, py)
        else ctx.lineTo(px, py)
      })

      // 填充
      const fill = ctx.createLinearGradient(0, padT, 0, padT + plotH)
      fill.addColorStop(0, 'rgba(161,117,240,0.28)')
      fill.addColorStop(1, 'rgba(161,117,240,0)')
      ctx.save()
      ctx.lineTo(x(F_MAX), y(0))
      ctx.lineTo(x(F_MIN), y(0))
      ctx.closePath()
      ctx.fillStyle = fill
      ctx.fill()
      ctx.restore()

      ctx.save()
      ctx.beginPath()
      freqs.forEach((f, i) => {
        const px = x(f)
        const py = y(dbs[i])
        if (i === 0) ctx.moveTo(px, py)
        else ctx.lineTo(px, py)
      })
      ctx.strokeStyle = '#C9A6FF'
      ctx.lineWidth = 2
      ctx.shadowColor = 'rgba(201,166,255,0.75)'
      ctx.shadowBlur = 10
      ctx.stroke()
      ctx.restore()

      // 锚点
      bands.forEach((b, i) => {
        const px = x(b.freq)
        const py = y(b.gain)
        ctx.beginPath()
        ctx.arc(px, py, 5, 0, Math.PI * 2)
        ctx.fillStyle = '#0B0810'
        ctx.fill()
        ctx.strokeStyle = 'rgba(201,166,255,0.9)'
        ctx.lineWidth = 1.6
        ctx.stroke()

        ctx.fillStyle = 'rgba(242,236,250,0.85)'
        ctx.font = '9px "Cascadia Mono", Consolas, monospace'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'bottom'
        ctx.fillText(String(i + 1), px, py - 8)
      })
    }

    draw()
    const ro = new ResizeObserver(draw)
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [bands, range, height])

  return (
    <div ref={wrapRef} className="chart">
      <canvas ref={canvasRef} role="img" aria-label="参数均衡器频响曲线" />
    </div>
  )
}
