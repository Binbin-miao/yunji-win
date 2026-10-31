import { useCallback, useEffect, useRef } from 'react'
import type { EqBand } from '../domain/eq'
import { DB_RANGES } from '../domain/eq'
import type { TargetCurve } from '../data/targets'
import { drawData, drawGrid } from './chartDraw'
import {
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
} from '../domain/eqEdit'

/** 判定「点击」而非「拖动」的像素阈值 */
const CLICK_SLOP = 4

interface Props {
  bands: EqBand[]
  /** 叠加的目标曲线，null 表示不叠加 */
  target?: TargetCurve | null
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

export default function EqChart({ bands, target, range, selected, onSelect, onChange, onBegin, onCommit, height = 320 }: Props) {
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
  // 网格层缓存在离屏画布上，只有尺寸或纵轴范围变了才重画；
  // 每帧只做「贴网格 + 画曲线与锚点」，拖动时开销稳定。
  const gridCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const gridKeyRef = useRef('')
  const rafRef = useRef(0)

  const render = useCallback(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return

    const dpr = window.devicePixelRatio || 1
    const l = layout()
    const w = Math.max(1, Math.round(l.width))
    const dw = Math.round(w * dpr)
    const dh = Math.round(height * dpr)
    if (canvas.width !== dw || canvas.height !== dh) {
      canvas.width = dw
      canvas.height = dh
      canvas.style.width = `${w}px`
      canvas.style.height = `${height}px`
    }

    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, height)

    // 网格画在下面那张画布上，尺寸或纵轴范围变了才重画；这一帧只管曲线
    const key = `${w}x${height}@${dpr}:${range}`
    if (gridKeyRef.current !== key) {
      const g = gridCanvasRef.current
      const gctx = g?.getContext('2d')
      if (g && gctx) {
        g.width = dw
        g.height = dh
        g.style.width = `${w}px`
        g.style.height = `${height}px`
        gctx.setTransform(dpr, 0, 0, dpr, 0, 0)
        gctx.clearRect(0, 0, w, height)
        drawGrid(gctx, l, range)
      }
      gridKeyRef.current = key
    }

    drawData(ctx, l, { bands, target: target ?? null, selected }, range)
  }, [bands, target, range, selected, height])

  // 同一帧内的多次改动合并成一次重绘
  const renderRef = useRef(render)
  renderRef.current = render
  const schedule = useCallback(() => {
    if (rafRef.current) return
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = 0
      renderRef.current()
    })
  }, [])

  useEffect(() => {
    schedule()
  }, [render, schedule])

  useEffect(() => {
    const wrap = wrapRef.current
    if (!wrap) return
    const ro = new ResizeObserver(() => {
      gridKeyRef.current = '' // 尺寸变了，网格层作废
      schedule()
    })
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [schedule])

  useEffect(() => () => cancelAnimationFrame(rafRef.current), [])

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

  // 读屏软件没法理解画布，这里把曲线念成一句话
  const chartLabel =
    '参数均衡器曲线：' +
    bands
      .map((b, i) => `第 ${i + 1} 段 ${b.freq} 赫兹 ${b.gain > 0 ? '+' : ''}${b.gain} 分贝 Q ${b.q}`)
      .join('；') +
    (selected != null ? `。当前选中第 ${selected + 1} 段` : '')

  return (
    <div ref={wrapRef} className="chart">
      <canvas ref={gridCanvasRef} className="chart-canvas chart-grid" aria-hidden="true" />
      <canvas
        ref={canvasRef}
        className="chart-canvas"
        tabIndex={0}
        role="application"
        aria-label={chartLabel}
        aria-describedby="chart-help"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDoubleClick={onDoubleClick}
        onContextMenu={onContextMenu}
        onWheel={onWheel}
        onKeyDown={onKeyDown}
      />
      <span id="chart-help" className="visually-hidden">
        共 {bands.length} 段，当前选中第 {(selected ?? 0) + 1} 段时可用方向键调整频率与增益，
        按住 Shift 步进更大，Delete 删除该段。
      </span>
    </div>
  )
}
