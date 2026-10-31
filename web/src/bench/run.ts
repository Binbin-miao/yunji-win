/**
 * 曲线区性能基准（16 号工单）。
 *
 * 跑法：
 *   cd web && npx vite --port 4174
 *   浏览器打开 http://127.0.0.1:4174/yunji-win/web/bench/
 *
 * 无头抓数（结果会写进 title，方便直接 grep）：
 *   chrome --headless=new --disable-gpu --dump-dom http://127.0.0.1:4174/yunji-win/web/bench/
 *
 * 量的都是同一台机器上的相对开销；绝对值随机器、浏览器、是否软件渲染差别很大，
 * 所以 web/BENCH.md 里必须一并写清环境。
 */
import { DEMO_BANDS, curve, type EqBand } from '../domain/eq'
import { fitParsed } from '../domain/eqFit'
import { parseEqText } from '../domain/eqImport'
import { drawData, drawGrid } from '../components/chartDraw'
import { xAtFreq, yAtDb, type Layout } from '../domain/eqEdit'
import { TARGETS } from '../data/targets'

const REPS = 200

interface Case {
  label: string
  width: number
  height: number
  dpr: number
}

const CASES: Case[] = [
  { label: '960×320 @1x（笔记本常见）', width: 960, height: 320, dpr: 1 },
  { label: '1280×320 @2x（高分屏）', width: 1280, height: 320, dpr: 2 },
  { label: '1920×480 @2x（全屏宽）', width: 1920, height: 480, dpr: 2 },
]

function makeCanvas(c: Case) {
  const el = document.createElement('canvas')
  el.width = Math.round(c.width * c.dpr)
  el.height = Math.round(c.height * c.dpr)
  const ctx = el.getContext('2d')
  if (!ctx) throw new Error('拿不到 2d 上下文')
  ctx.setTransform(c.dpr, 0, 0, c.dpr, 0, 0)
  return { el, ctx }
}

/** 跑 reps 次取平均毫秒数；先预热一次，避免把首次 JIT 与字体加载算进去 */
function bench(reps: number, fn: () => void) {
  fn()
  const t0 = performance.now()
  for (let i = 0; i < reps; i++) fn()
  return (performance.now() - t0) / reps
}

/** 模拟拖动：每帧把第 2 段的频率与增益推一点 */
function draggedBands(step: number): EqBand[] {
  const t = (step % 60) / 60
  return DEMO_BANDS.map((b, i) =>
    i === 1 ? { ...b, freq: Math.round(60 + t * 160), gain: +(3 - t * 6).toFixed(2) } : b,
  )
}

const GRID_EQ = Array.from({ length: 100 }, (_, i) => {
  const f = Math.round(20 * Math.pow(1000, i / 99))
  return `${f} ${(6 * Math.sin(i / 9) - 2).toFixed(2)}`
}).join('; ')

function measure(c: Case) {
  const target = TARGETS[0] ?? null
  const layout: Layout = { width: c.width, height: c.height, range: 12 }
  const main = makeCanvas(c)
  const grid = makeCanvas(c)
  const clear = () => main.ctx.clearRect(0, 0, c.width, c.height)
  // Canvas2D 只记录命令，真正栅格化发生在提交时。
  // 读一个像素强制同步出图，这样量到的才是真实绘制成本，而不是命令排队成本。
  const flush = (ctx: CanvasRenderingContext2D) => ctx.getImageData(0, 0, 1, 1)

  const gridMs = bench(30, () => {
    grid.ctx.clearRect(0, 0, c.width, c.height)
    drawGrid(grid.ctx, layout, 12)
    flush(grid.ctx)
  })

  let step = 0
  const dataMs = bench(REPS, () => {
    drawData(main.ctx, layout, { bands: draggedBands(step++), target, selected: 1 }, 12)
    flush(main.ctx)
  })

  // 本版：网格在底下那张画布上常驻，每帧只清 + 画曲线
  step = 0
  const frameMs = bench(REPS, () => {
    clear()
    drawData(main.ctx, layout, { bands: draggedBands(step++), target, selected: 1 }, 12)
    flush(main.ctx)
  })

  // 优化前的写法：每帧把网格和数据一起重画
  step = 0
  const oldMs = bench(REPS, () => {
    clear()
    drawGrid(main.ctx, layout, 12)
    drawData(main.ctx, layout, { bands: draggedBands(step++), target, selected: 1 }, 12)
    flush(main.ctx)
  })

  step = 0
  const curveMs = bench(REPS, () => {
    curve(draggedBands(step++), 240)
  })

  return { label: c.label, gridMs, dataMs, frameMs, oldMs, curveMs }
}

/**
 * 发光画法对比：同一条 240 点曲线，一次用 shadowBlur，一次用「淡光 + 亮线」两次描边。
 * 这是本次最值钱的优化，单独量出来，避免被网格层的噪声盖掉。
 */
function glowBench(c: Case) {
  const layout: Layout = { width: c.width, height: c.height, range: 12 }
  const { freqs, dbs } = curve(DEMO_BANDS, 240)
  const main = makeCanvas(c)
  const flush = (ctx: CanvasRenderingContext2D) => ctx.getImageData(0, 0, 1, 1)
  const path = () => {
    const ctx = main.ctx
    ctx.beginPath()
    freqs.forEach((f, i) => {
      const x = xAtFreq(f, layout)
      const y = yAtDb(dbs[i], layout)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
  }

  const shadow = bench(REPS, () => {
    main.ctx.clearRect(0, 0, c.width, c.height)
    path()
    const ctx = main.ctx
    ctx.save()
    ctx.strokeStyle = '#C9A6FF'
    ctx.lineWidth = 2
    ctx.shadowColor = 'rgba(201,166,255,0.75)'
    ctx.shadowBlur = 10
    ctx.stroke()
    ctx.restore()
    flush(ctx)
  })

  const twoStroke = bench(REPS, () => {
    main.ctx.clearRect(0, 0, c.width, c.height)
    path()
    const ctx = main.ctx
    ctx.save()
    ctx.lineJoin = 'round'
    ctx.lineCap = 'round'
    ctx.strokeStyle = 'rgba(201,166,255,0.16)'
    ctx.lineWidth = 7
    ctx.stroke()
    ctx.strokeStyle = '#C9A6FF'
    ctx.lineWidth = 2
    ctx.stroke()
    ctx.restore()
    flush(ctx)
  })

  return { label: c.label, shadow, twoStroke }
}

function run() {
  const rows: string[] = []
  const results = CASES.map(measure)

  const chrome = (navigator.userAgent.match(/Chrome\/[\d.]+/) ?? ['未知浏览器'])[0]
  rows.push(`浏览器      ${chrome}`)
  rows.push(`每项次数量   拖动帧 ${REPS} 次、网格 30 次，取平均`)
  rows.push('')
  rows.push('画布                    网格层重画    本版每帧    旧版每帧   省下')
  for (const r of results) {
    const save = ((r.oldMs - r.frameMs) / r.oldMs) * 100
    rows.push(
      `${r.label.padEnd(22)} ${r.gridMs.toFixed(3).padStart(8)} ms ${r.frameMs
        .toFixed(3)
        .padStart(9)} ms ${r.oldMs.toFixed(3).padStart(8)} ms ${save.toFixed(0).padStart(5)} %`,
    )
  }
  rows.push('')
  rows.push('发光画法（同一条 240 点曲线，只换发光手段）')
  for (const g of CASES.map(glowBench)) {
    rows.push(
      `${g.label.padEnd(22)} shadowBlur ${g.shadow.toFixed(3).padStart(7)} ms ` +
        `→ 两次描边 ${g.twoStroke.toFixed(3).padStart(7)} ms ` +
        `（${((1 - g.twoStroke / g.shadow) * 100).toFixed(0)} % 更快）`,
    )
  }
  rows.push('')
  rows.push(`曲线计算    ${results[0].curveMs.toFixed(3)} ms / 240 点（已含在数据层里）`)

  const parsed = parseEqText(`GraphicEQ: ${GRID_EQ}`)
  if (parsed.ok) {
    const fitMs = bench(10, () => {
      fitParsed(parsed.result)
    })
    rows.push(`拟合        100 个频点 → 8 段：${fitMs.toFixed(1)} ms（160 拟合点 × 5 次迭代）`)
    rows.push('            超过 16 ms 帧预算，所以放到「拟合中…」里异步跑，不占拖动路径')
  } else {
    rows.push(`拟合未跑：${parsed.error}`)
  }

  const worst = Math.max(...results.map(r => r.frameMs))
  rows.push('')
  rows.push(
    worst < 16
      ? `结论：最慢一档单帧 ${worst.toFixed(2)} ms，60 fps（16.7 ms）还有 ${(16.7 / worst).toFixed(0)} 倍余量。`
      : `结论：最慢一档单帧 ${worst.toFixed(2)} ms，已超 16 ms，需要继续优化。`,
  )

  const text = rows.join('\n')
  const out = document.getElementById('out')
  if (out) out.textContent = text

  const first = results[0]
  document.title = `BENCH frame=${first.frameMs.toFixed(2)}ms old=${first.oldMs.toFixed(2)}ms`
}

// 同步跑完再让 load 事件结束，这样 --dump-dom 直接拿到结果
try {
  run()
} catch (e) {
  const out = document.getElementById('out')
  if (out) out.textContent = `基准跑挂了：${e instanceof Error ? e.stack : String(e)}`
}
