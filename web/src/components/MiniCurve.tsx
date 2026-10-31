import { useEffect, useRef } from 'react'
import { F_MAX, F_MIN, curve, dbToRatio, freqToRatio, type EqBand } from '../domain/eq'

interface Props {
  bands?: EqBand[]
  /** 直接给一条曲线（拟合预览用），优先于 bands */
  series?: { freqs: number[]; dbs: number[] }
  width?: number
  height?: number
  /** 曲线颜色，默认主色 */
  color?: string
}

/** 缩略曲线：预设列表与拟合预览共用 */
export default function MiniCurve({ bands, series, width = 96, height = 40, color = '#C9A6FF' }: Props) {
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

    ctx.strokeStyle = 'rgba(196,164,255,0.16)'
    ctx.beginPath()
    ctx.moveTo(0, height / 2)
    ctx.lineTo(width, height / 2)
    ctx.stroke()

    const data = series ?? (bands ? curve(bands, 80) : { freqs: [], dbs: [] })
    const range = 12
    ctx.beginPath()
    data.freqs.forEach((f, i) => {
      const x = freqToRatio(f, F_MIN, F_MAX) * width
      const y = dbToRatio(data.dbs[i], range) * height
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.strokeStyle = color
    ctx.lineWidth = 1.4
    ctx.stroke()
  }, [bands, series, width, height, color])

  return <canvas ref={ref} className="mini-curve" aria-hidden="true" />
}
