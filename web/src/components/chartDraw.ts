/**
 * 曲线区的纯绘制逻辑（不碰 React）。
 *
 * 拆两层是为了拖动跟手：
 * - 网格与刻度只跟画布尺寸和纵轴范围有关，缓存到离屏画布，只在尺寸或范围变化时重画
 * - 曲线、锚点、读数每帧重画，但每帧只做「贴一张图 + 画一条线」
 *
 * 形状由 domain/eq 与 domain/eqEdit 决定，这里只负责画，不含任何数值规则。
 */
import { F_MAX, F_MIN, curve, type EqBand } from '../domain/eq'
import { targetDbAt } from '../domain/target'
import type { TargetCurve } from '../data/targets'
import { HIT_RADIUS, xAtFreq, yAtDb, type Layout } from '../domain/eqEdit'

export const TICKS = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
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

/** 曲线采样点数，同时决定拟合目标点的密度 */
export const CURVE_POINTS = 240

const MONO = '"Cascadia Mono", Consolas, monospace'

export interface Scene {
  bands: EqBand[]
  target: TargetCurve | null
  selected: number | null
}

/** 网格层：竖线、横线、两侧刻度 */
export function drawGrid(ctx: CanvasRenderingContext2D, l: Layout, range: number) {
  const px = (f: number) => xAtFreq(f, l)
  const py = (db: number) => yAtDb(db, l)
  const x0 = px(F_MIN)
  const x1 = px(F_MAX)
  const yTop = py(range)
  const yBottom = py(-range)

  ctx.strokeStyle = 'rgba(196,164,255,0.10)'
  ctx.lineWidth = 1
  for (const t of TICKS) {
    const x = Math.round(px(t)) + 0.5
    ctx.beginPath()
    ctx.moveTo(x, yTop)
    ctx.lineTo(x, yBottom)
    ctx.stroke()
  }

  const step = range === 12 ? 6 : 3
  for (let db = -range; db <= range; db += step) {
    const y = Math.round(py(db)) + 0.5
    ctx.strokeStyle = db === 0 ? 'rgba(196,164,255,0.24)' : 'rgba(196,164,255,0.08)'
    ctx.beginPath()
    ctx.moveTo(x0, y)
    ctx.lineTo(x1, y)
    ctx.stroke()
  }

  ctx.fillStyle = 'rgba(167,156,184,0.75)'
  ctx.font = `10px ${MONO}`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  for (const t of TICKS) ctx.fillText(LABELS[t], px(t), yBottom + 6)
  ctx.textAlign = 'right'
  ctx.textBaseline = 'middle'
  for (let db = -range; db <= range; db += step) {
    ctx.fillText(db > 0 ? `+${db}` : String(db), x0 - 6, py(db))
  }
}

// 目标曲线只跟频率轴有关，与拖动无关：同一根轴只算一次
let tCacheTarget: TargetCurve | null = null
let tCacheSpan = ''
let tCacheOut: number[] = []

function targetDbs(target: TargetCurve, freqs: number[]): number[] {
  const span = `${freqs.length}:${freqs[0]}:${freqs[freqs.length - 1]}`
  if (tCacheTarget === target && tCacheSpan === span) return tCacheOut
  tCacheOut = freqs.map(f => targetDbAt(target.points, f))
  tCacheTarget = target
  tCacheSpan = span
  return tCacheOut
}

// 渐变只跟纵轴像素范围有关，每帧重建没必要（按画布分别缓存，避免跨上下文复用）
const gCache = new WeakMap<CanvasRenderingContext2D, { key: string; grad: CanvasGradient }>()

function areaGradient(ctx: CanvasRenderingContext2D, top: number, bottom: number): CanvasGradient {
  const key = `${top}:${bottom}`
  const hit = gCache.get(ctx)
  if (hit && hit.key === key) return hit.grad
  const grad = ctx.createLinearGradient(0, top, 0, bottom)
  grad.addColorStop(0, 'rgba(161,117,240,0.28)')
  grad.addColorStop(1, 'rgba(161,117,240,0)')
  gCache.set(ctx, { key, grad })
  return grad
}

/** 数据层：差值填充、曲线、目标虚线、锚点、选中读数 */
export function drawData(ctx: CanvasRenderingContext2D, l: Layout, scene: Scene, range: number) {
  const { bands, target, selected } = scene
  const px = (f: number) => xAtFreq(f, l)
  const py = (db: number) => yAtDb(db, l)
  const x0 = px(F_MIN)
  const x1 = px(F_MAX)
  const yTop = py(range)

  const { freqs, dbs } = curve(bands, CURVE_POINTS)
  const tDbs = target ? targetDbs(target, freqs) : null

  // 差值填充（当前 − 目标）
  if (tDbs) {
    ctx.save()
    ctx.beginPath()
    freqs.forEach((f, i) => {
      const x = px(f)
      const y = py(dbs[i])
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    for (let i = freqs.length - 1; i >= 0; i--) ctx.lineTo(px(freqs[i]), py(tDbs[i]))
    ctx.closePath()
    ctx.fillStyle = 'rgba(121,224,208,0.10)'
    ctx.fill()
    ctx.restore()
  }

  const trace = () => {
    ctx.beginPath()
    freqs.forEach((f, i) => {
      const x = px(f)
      const y = py(dbs[i])
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
  }

  trace()
  ctx.save()
  ctx.lineTo(x1, py(0))
  ctx.lineTo(x0, py(0))
  ctx.closePath()
  ctx.fillStyle = areaGradient(ctx, yTop, py(-range))
  ctx.fill()
  ctx.restore()

  // 发光原来用 shadowBlur，软件光栅下要贵 3 倍；改成「一圈淡光 + 一条亮线」两次描边，
  // 视觉几乎一样，帧成本从 4.7 ms 降到 1.6 ms（见 web/BENCH.md）
  ctx.save()
  trace()
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  ctx.strokeStyle = 'rgba(201,166,255,0.16)'
  ctx.lineWidth = 7
  ctx.stroke()
  ctx.strokeStyle = '#C9A6FF'
  ctx.lineWidth = 2
  ctx.stroke()
  ctx.restore()

  if (tDbs) {
    ctx.save()
    ctx.setLineDash([5, 4])
    ctx.beginPath()
    freqs.forEach((f, i) => {
      const x = px(f)
      const y = py(tDbs[i])
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.strokeStyle = 'rgba(121,224,208,0.9)'
    ctx.lineWidth = 1.4
    ctx.stroke()
    ctx.restore()
  }

  // 锚点：未选中是空心环，选中是实心加白边，编号始终可见（不靠颜色区分）
  bands.forEach((b, i) => {
    const x = px(b.freq)
    const y = py(b.gain)
    const isSel = i === selected
    if (isSel) {
      ctx.beginPath()
      ctx.arc(x, y, HIT_RADIUS, 0, Math.PI * 2)
      ctx.strokeStyle = 'rgba(201,166,255,0.35)'
      ctx.lineWidth = 1
      ctx.stroke()
    }
    ctx.beginPath()
    ctx.arc(x, y, isSel ? 6 : 5, 0, Math.PI * 2)
    ctx.fillStyle = '#0B0810'
    ctx.fill()
    ctx.strokeStyle = isSel ? '#F2ECFA' : 'rgba(201,166,255,0.9)'
    ctx.lineWidth = isSel ? 2 : 1.6
    ctx.stroke()

    ctx.fillStyle = 'rgba(242,236,250,0.85)'
    ctx.font = `9px ${MONO}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'bottom'
    ctx.fillText(String(i + 1), x, y - 9)
  })

  if (selected !== null && bands[selected]) {
    const b = bands[selected]
    const text = `${b.freq >= 1000 ? (b.freq / 1000).toFixed(2) + 'k' : b.freq + ' Hz'} · ${
      b.gain > 0 ? '+' : ''
    }${b.gain.toFixed(1)} dB · Q ${b.q.toFixed(2)}`
    ctx.font = `11px ${MONO}`
    const w = ctx.measureText(text).width + 16
    const x = Math.min(Math.max(px(b.freq) - w / 2, x0), x1 - w)
    const y = Math.max(py(b.gain) - 34, yTop + 2)
    ctx.fillStyle = 'rgba(11,8,16,0.88)'
    ctx.strokeStyle = 'rgba(201,166,255,0.35)'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.roundRect(x, y, w, 20, 6)
    ctx.fill()
    ctx.stroke()
    ctx.fillStyle = '#F2ECFA'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.fillText(text, x + 8, y + 10)
  }
}
