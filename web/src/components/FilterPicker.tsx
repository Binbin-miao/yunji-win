import { useEffect, useRef } from 'react'
import { FILTER_MAX_HZ, filterResponse, ringingOf } from '../domain/filterShape'
import { COPY } from '../copy'

interface Props {
  /** 设备当前档位 0~4 */
  value: number
  disabled?: boolean
  onChange: (mode: number) => void
}

const W = 104
const H = 60
/** 主图绘图区 */
const PAD_L = 4
const PAD_R = 8
const PAD_T = 6
const CURVE_BOTTOM = 40
const DB_MIN = -44
const DB_MAX = 2

/** 一张卡片里的小画布：上面频响示意，右下角画脉冲振铃（前拖尾 vs 后拖尾） */
function drawCard(canvas: HTMLCanvasElement, mode: number) {
  const dpr = window.devicePixelRatio || 1
  canvas.width = Math.round(W * dpr)
  canvas.height = Math.round(H * dpr)
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, W, H)

  const x = (f: number) => PAD_L + (f / FILTER_MAX_HZ) * (W - PAD_L - PAD_R)
  const y = (db: number) => {
    const t = (db - DB_MIN) / (DB_MAX - DB_MIN)
    return CURVE_BOTTOM - t * (CURVE_BOTTOM - PAD_T)
  }

  // 基线（0 dB）与 Nyquist 竖线
  ctx.strokeStyle = 'rgba(196,164,255,0.16)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(PAD_L, y(0))
  ctx.lineTo(W - PAD_R, y(0))
  ctx.stroke()

  const { freqs, dbs } = filterResponse(mode)
  ctx.beginPath()
  freqs.forEach((f, i) => (i === 0 ? ctx.moveTo(x(f), y(dbs[i])) : ctx.lineTo(x(f), y(dbs[i]))))
  // 曲线下方填一层淡紫，视觉上更像"响应图"而不是折线
  ctx.lineTo(x(FILTER_MAX_HZ), CURVE_BOTTOM)
  ctx.lineTo(x(0), CURVE_BOTTOM)
  ctx.closePath()
  ctx.fillStyle = 'rgba(161,117,240,0.16)'
  ctx.fill()

  ctx.beginPath()
  freqs.forEach((f, i) => (i === 0 ? ctx.moveTo(x(f), y(dbs[i])) : ctx.lineTo(x(f), y(dbs[i]))))
  ctx.strokeStyle = '#C9A6FF'
  ctx.lineWidth = 1.4
  ctx.lineJoin = 'round'
  ctx.stroke()

  // 左下角振铃示意（频响曲线右侧要留给滚降，别互相压）：
  // 低延迟 = 只在脉冲之后拖尾；相位补偿 = 脉冲前后对称拖尾
  const bw = 30
  const bh = 11
  const bx = 5
  const by = H - 4
  const impulseAt = ringingOf(mode) === 'both' ? bx + bw / 2 : bx + bw * 0.28
  ctx.strokeStyle = 'rgba(121,224,208,0.22)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(bx, by)
  ctx.lineTo(bx + bw, by)
  ctx.stroke()
  for (let i = 0; i <= 14; i++) {
    const px = bx + (i / 14) * bw
    const d = Math.abs(px - impulseAt)
    const amp = Math.exp(-Math.pow(d / 4.2, 2)) * (i % 2 === 0 ? 1 : -1)
    const h = Math.max(-0.6, Math.min(1, amp)) * bh
    ctx.strokeStyle = 'rgba(121,224,208,0.55)'
    ctx.beginPath()
    ctx.moveTo(px, by)
    ctx.lineTo(px, by - h)
    ctx.stroke()
  }
}

export default function FilterPicker({ value, disabled, onChange }: Props) {
  return (
    <>
      <div className="filter-cards" role="group" aria-label={COPY.param.filter.label}>
        {COPY.filters.map((f, i) => (
          <button
            key={f.name}
            type="button"
            className={`filter-card ${value === i ? 'on' : ''}`}
            aria-pressed={value === i}
            disabled={disabled}
            onClick={() => onChange(i)}
            title={`${f.name}：适合${f.fit}；代价 ${f.cost}`}
          >
            <FilterThumb mode={i} />
            <span className="filter-name">{f.name}</span>
            <span className="filter-fit">{f.fit}</span>
            <span className="filter-cost">{f.cost}</span>
          </button>
        ))}
      </div>
      <p className="hint filter-note">{COPY.filterNote}</p>
    </>
  )
}

function FilterThumb({ mode }: { mode: number }) {
  const ref = useRef<HTMLCanvasElement | null>(null)
  useEffect(() => {
    if (ref.current) drawCard(ref.current, mode)
  }, [mode])
  return <canvas ref={ref} className="filter-thumb" style={{ width: W, height: H }} aria-hidden="true" />
}
