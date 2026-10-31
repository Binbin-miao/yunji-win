/**
 * 曲线的交互计算（纯函数，无 DOM）。
 *
 * 画布布局与命中检测都在这里，组件只负责事件与绘制，
 * 这样拖拽的数学部分可以脱离浏览器单测。
 */

import { F_MAX, F_MIN, dbToRatio, freqToRatio, type EqBand } from './eq'

export const MAX_BANDS = 8
export const MIN_FREQ = F_MIN
export const MAX_FREQ = F_MAX
export const MAX_GAIN = 12
export const MIN_Q = 0.1
export const MAX_Q = 10
/** 增益吸附到 0 的阈值 */
export const SNAP_DB = 0.15
/** 命中半径（像素） */
export const HIT_RADIUS = 12

export const PAD = { left: 34, right: 12, top: 10, bottom: 22 }

export interface Layout {
  width: number
  height: number
  range: number
}

export interface Box {
  x0: number
  y0: number
  w: number
  h: number
}

export const plotBox = (l: Layout): Box => ({
  x0: PAD.left,
  y0: PAD.top,
  w: Math.max(1, l.width - PAD.left - PAD.right),
  h: Math.max(1, l.height - PAD.top - PAD.bottom),
})

export const xAtFreq = (f: number, l: Layout): number => {
  const b = plotBox(l)
  return b.x0 + freqToRatio(f, F_MIN, F_MAX) * b.w
}

export const yAtDb = (db: number, l: Layout): number => {
  const b = plotBox(l)
  return b.y0 + dbToRatio(db, l.range) * b.h
}

/** 像素 x → 频率（反解对数轴） */
export const freqAtX = (x: number, l: Layout): number => {
  const b = plotBox(l)
  const ratio = Math.min(1, Math.max(0, (x - b.x0) / b.w))
  return F_MIN * Math.pow(F_MAX / F_MIN, ratio)
}

/** 像素 y → dB */
export const dbAtY = (y: number, l: Layout): number => {
  const b = plotBox(l)
  const ratio = Math.min(1, Math.max(0, (y - b.y0) / b.h))
  return (0.5 - ratio) * 2 * l.range
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))

/** 增益靠近 0 时吸附，避免手抖留下 ±0.1 */
export const snapGain = (g: number): number => (Math.abs(g) < SNAP_DB ? 0 : g)

/** 相邻两段之间至少相差的倍数，防止挤在一起无法分辨 */
export const MIN_FREQ_GAP = 1.02

export interface FreqLimits {
  minFreq: number
  maxFreq: number
}

/**
 * 某段可用的频率区间：夹在左右邻居之间，保持段的先后顺序。
 * 拖拽与键盘微调都必须用它，否则能把第 1 段拖到第 8 段右边。
 */
export function freqLimits(bands: EqBand[], index: number): FreqLimits {
  const prev = index > 0 ? bands[index - 1].freq : 0
  const next = index >= 0 && index < bands.length - 1 ? bands[index + 1].freq : Infinity
  const minFreq = prev > 0 ? Math.max(MIN_FREQ, prev * MIN_FREQ_GAP) : MIN_FREQ
  const maxFreq = Number.isFinite(next) ? Math.min(MAX_FREQ, next / MIN_FREQ_GAP) : MAX_FREQ
  // 极端情况下（邻居贴太近）保证区间不反转
  return { minFreq: Math.min(minFreq, maxFreq), maxFreq: Math.max(minFreq, maxFreq) }
}

/** 把一段参数收进设备与界面都接受的范围内（不做吸附，吸附只在拖动时用） */
export function clampBand(band: EqBand, limits?: FreqLimits): EqBand {
  const lo = limits ? Math.max(MIN_FREQ, limits.minFreq) : MIN_FREQ
  const hi = limits ? Math.min(MAX_FREQ, limits.maxFreq) : MAX_FREQ
  return {
    freq: Math.round(clamp(band.freq, lo, hi)),
    q: Math.round(clamp(band.q, MIN_Q, MAX_Q) * 100) / 100,
    gain: Math.round(clamp(band.gain, -MAX_GAIN, MAX_GAIN) * 10) / 10,
  }
}

/** 命中检测：返回指针下的段索引，没有则 -1 */
export function hitBand(bands: EqBand[], l: Layout, x: number, y: number): number {
  let best = -1
  let bestDist = HIT_RADIUS
  bands.forEach((b, i) => {
    const d = Math.hypot(xAtFreq(b.freq, l) - x, yAtDb(b.gain, l) - y)
    if (d <= bestDist) {
      best = i
      bestDist = d
    }
  })
  return best
}

export type LockAxis = 'freq' | 'gain' | null

/**
 * 拖动：从按下时的原始段出发，按累计像素位移算出新参数。
 * 用「起点 + 总位移」而不是逐帧累加，避免误差累积与漂移。
 */
export function dragBand(
  start: EqBand,
  l: Layout,
  startX: number,
  startY: number,
  curX: number,
  curY: number,
  lock: LockAxis,
  limits?: FreqLimits,
): EqBand {
  const next = { ...start }
  // lock 表示「锁定哪个轴」：'freq' 时频率不动，只改增益；'gain' 反之
  if (lock !== 'freq') {
    next.freq = freqAtX(xAtFreq(start.freq, l) + (curX - startX), l)
  }
  if (lock !== 'gain') {
    next.gain = snapGain(dbAtY(yAtDb(start.gain, l) + (curY - startY), l))
  }
  return clampBand(next, limits)
}

/** 在某个像素位置插入新段（增益取该位置对应值） */
export function bandAtPoint(l: Layout, x: number, y: number): EqBand {
  return clampBand({ freq: freqAtX(x, l), q: 0.75, gain: dbAtY(y, l) })
}

/** 键盘微调：方向键改频率/增益 */
export function nudgeBand(
  band: EqBand,
  key: string,
  shift: boolean,
  limits?: FreqLimits,
): EqBand {
  const next = { ...band }
  const gainStep = shift ? 1 : 0.1
  const freqFactor = shift ? 1.2 : 1.02
  if (key === 'ArrowUp') next.gain += gainStep
  else if (key === 'ArrowDown') next.gain -= gainStep
  else if (key === 'ArrowLeft') next.freq /= freqFactor
  else if (key === 'ArrowRight') next.freq *= freqFactor
  else return band
  return clampBand(next, limits)
}

/** 滚轮调 Q */
export function scrollQ(band: EqBand, deltaY: number, shift: boolean): EqBand {
  const step = shift ? 0.5 : 0.05
  return clampBand({ ...band, q: band.q - Math.sign(deltaY) * step })
}

/** 新增一段（到上限返回原数组） */
export function addBand(bands: EqBand[], band: EqBand): EqBand[] {
  if (bands.length >= MAX_BANDS) return bands
  return [...bands, band].sort((a, b) => a.freq - b.freq)
}

/** 删除一段 */
export function removeBand(bands: EqBand[], index: number): EqBand[] {
  if (index < 0 || index >= bands.length) return bands
  return bands.filter((_, i) => i !== index)
}

/** 替换某一段（保持索引） */
export function replaceBand(bands: EqBand[], index: number, band: EqBand): EqBand[] {
  return bands.map((b, i) => (i === index ? band : b))
}
