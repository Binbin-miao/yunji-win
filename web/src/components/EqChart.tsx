import { useCallback, useEffect, useRef } from 'react'
import { DB_RANGES, F_MAX, F_MIN, curve, type EqBand } from '../domain/eq'
import {
  HIT_RADIUS,
  MAX_BANDS,
  type Layout,
  type LockAxis,
  addBand,
  bandAtPoint,
  dragBand,
  freqLimits,
  hitBand,
  nudgeBand,
  removeBand,
  replaceBand,
  scrollQ,
  xAtFreq,
  yAtDb,
} from '../domain/eqEdit'

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
/** 判定「点击」而非「拖动」的像素阈值 */
const CLICK_SLOP = 4

interface Props {
  bands: EqBand[]
  range: (typeof DB_RANGES)[number]
  selected: number | null
  onSelect: (index: number | null) => void
  /** transient=true 表示拖拽中的中间态，不入历史 */
  onChange: (bands: EqBand[], transient?: boolean) => void
  /** 拖拽开始（用于记录撤销快照） */
  onBegin?: () => void
  /** 拖拽结束（提交撤销快照） */
  onCommit?: () => void
  height?: number
}

interface DragState {
  index: number
  startBand: EqBand
  startX: number
  startY: number
  moved: boolean
}

export default function EqChart({ bands, range, selected, onSelect, onChange, onBegin, onCommit, height = 320 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const dragRef = useRef<DragState | null>(null)
  const bandsRef = useRef(bands)
  bandsRef.current = bands

  const layout = (): Layout => ({
    width: wrapRef.current?.clientWidth ?? 600,
    height,
    range,
  })

  const localPoint = (e: { clientX: number; clientY: number }) => {
    const rect = canvasRef.current!.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  // ---------- 绘制 ----------
  const draw = useCallback(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return

    const dpr = window.devicePixelRatio || 1
    const l = layout()
    canvas.width = Math.round(l.width * dpr)
    canvas.height = Math.round(height * dpr)
    canvas.style.width = `${l.width}px`
    canvas.style.height = `${height}px`

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, l.width, height)

    const px = (f: number) => xAtFreq(f, l)
    const py = (db: number) => yAtDb(db, l)
    const x0 = px(F_MIN)
    const x1 = px(F_MAX)
    const yTop = py(range)
    const yBottom = py(-range)

    // 竖向网格
    ctx.strokeStyle = 'rgba(196,164,255,0.10)'
    ctx.lineWidth = 1
    for (const t of TICKS) {
      const x = Math.round(px(t)) + 0.5
      ctx.beginPath()
      ctx.moveTo(x, yTop)
      ctx.lineTo(x, yBottom)
      ctx.stroke()
    }

    // 横向网格
    const step = range === 12 ? 6 : 3
    for (let db = -range; db <= range; db += step) {
      const y = Math.round(py(db)) + 0.5
      ctx.strokeStyle = db === 0 ? 'rgba(196,164,255,0.24)' : 'rgba(196,164,255,0.08)'
      ctx.beginPath()
      ctx.moveTo(x0, y)
      ctx.lineTo(x1, y)
      ctx.stroke()
    }

    // 刻度
    ctx.fillStyle = 'rgba(167,156,184,0.75)'
    ctx.font = '10px "Cascadia Mono", Consolas, monospace'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    for (const t of TICKS) ctx.fillText(LABELS[t], px(t), yBottom + 6)
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    for (let db = -range; db <= range; db += step) {
      ctx.fillText(db > 0 ? `+${db}` : String(db), x0 - 6, py(db))
    }

    // 曲线
    const { freqs, dbs } = curve(bands, 240)
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
    const fill = ctx.createLinearGradient(0, yTop, 0, yBottom)
    fill.addColorStop(0, 'rgba(161,117,240,0.28)')
    fill.addColorStop(1, 'rgba(161,117,240,0)')
    ctx.save()
    ctx.lineTo(x1, py(0))
    ctx.lineTo(x0, py(0))
    ctx.closePath()
    ctx.fillStyle = fill
    ctx.fill()
    ctx.restore()

    ctx.save()
    trace()
    ctx.strokeStyle = '#C9A6FF'
    ctx.lineWidth = 2
    ctx.shadowColor = 'rgba(201,166,255,0.75)'
    ctx.shadowBlur = 10
    ctx.stroke()
    ctx.restore()

    // 锚点
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
      ctx.font = '9px "Cascadia Mono", Consolas, monospace'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'bottom'
      ctx.fillText(String(i + 1), x, y - 9)
    })

    // 选中段的读数
    if (selected !== null && bands[selected]) {
      const b = bands[selected]
      const text = `${b.freq >= 1000 ? (b.freq / 1000).toFixed(2) + 'k' : b.freq + ' Hz'} · ${
        b.gain > 0 ? '+' : ''
      }${b.gain.toFixed(1)} dB · Q ${b.q.toFixed(2)}`
      ctx.font = '11px "Cascadia Mono", Consolas, monospace'
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
  }, [bands, range, selected, height])

  useEffect(() => {
    draw()
    const ro = new ResizeObserver(draw)
    if (wrapRef.current) ro.observe(wrapRef.current)
    return () => ro.disconnect()
  }, [draw])

  // ---------- 事件 ----------
  function onPointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    const l = layout()
    const { x, y } = localPoint(e)
    const hit = hitBand(bands, l, x, y)
    onSelect(hit >= 0 ? hit : null)
    if (hit < 0) return

    dragRef.current = { index: hit, startBand: bands[hit], startX: x, startY: y, moved: false }
    onBegin?.()
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function onPointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    const drag = dragRef.current
    if (!drag) return
    const l = layout()
    const { x, y } = localPoint(e)
    if (!drag.moved && Math.hypot(x - drag.startX, y - drag.startY) > CLICK_SLOP) {
      drag.moved = true
    }
    if (!drag.moved) return

    const dx = x - drag.startX
    const dy = y - drag.startY
    // 按住 Ctrl/⌘：按位移较大的方向锁定单轴
    const lock: LockAxis = e.ctrlKey || e.metaKey ? (Math.abs(dx) >= Math.abs(dy) ? 'gain' : 'freq') : null
    const limits = freqLimits(bandsRef.current, drag.index)
    const next = dragBand(drag.startBand, l, drag.startX, drag.startY, x, y, lock, limits)
    onChange(replaceBand(bandsRef.current, drag.index, next), true)
  }

  function onPointerUp(e: React.PointerEvent<HTMLCanvasElement>) {
    const drag = dragRef.current
    dragRef.current = null
    if (drag?.moved) {
      onCommit?.()
      return
    }
    if (!drag) return

    // 单击空白 → 新增一段
    const l = layout()
    const { x, y } = localPoint(e)
    if (hitBand(bands, l, x, y) >= 0) return
    if (bands.length >= MAX_BANDS) return
    const created = bandAtPoint(l, x, y)
    onChange(addBand(bands, created), false)
    onSelect(null)
  }

  function onDoubleClick(e: React.MouseEvent<HTMLCanvasElement>) {
    const l = layout()
    const { x, y } = localPoint(e)
    const hit = hitBand(bands, l, x, y)
    if (hit < 0) return
    // 双击锚点归零（滤波器类型字节设备只认 0x02，故不提供切换）
    onChange(replaceBand(bands, hit, { ...bands[hit], gain: 0 }), false)
  }

  function onContextMenu(e: React.MouseEvent<HTMLCanvasElement>) {
    e.preventDefault()
    const l = layout()
    const { x, y } = localPoint(e)
    const hit = hitBand(bands, l, x, y)
    if (hit < 0) return
    onChange(removeBand(bands, hit), false)
    onSelect(null)
  }

  function onWheel(e: React.WheelEvent<HTMLCanvasElement>) {
    if (selected === null) return
    const band = bands[selected]
    if (!band) return
    e.preventDefault()
    onChange(replaceBand(bands, selected, scrollQ(band, e.deltaY, e.shiftKey)), false)
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLCanvasElement>) {
    if (selected === null) return
    const band = bands[selected]
    if (!band) return
    if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault()
      onChange(removeBand(bands, selected), false)
      onSelect(null)
      return
    }
    if (!e.key.startsWith('Arrow')) return
    e.preventDefault()
    const limits = freqLimits(bands, selected)
    onChange(replaceBand(bands, selected, nudgeBand(band, e.key, e.shiftKey, limits)), false)
  }

  return (
    <div ref={wrapRef} className="chart">
      <canvas
        ref={canvasRef}
        className="chart-canvas"
        tabIndex={0}
        role="application"
        aria-label="参数均衡器曲线，可拖动锚点调整，方向键微调，Delete 删除"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDoubleClick={onDoubleClick}
        onContextMenu={onContextMenu}
        onWheel={onWheel}
        onKeyDown={onKeyDown}
      />
    </div>
  )
}
