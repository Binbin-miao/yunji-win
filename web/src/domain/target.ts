/**
 * 目标曲线的取值与差值统计。
 *
 * 差值 = 当前曲线 − 目标曲线。正数表示当前比目标多，负数表示少。
 */

import type { TargetCurve } from '../data/targets'
import { F_MAX, F_MIN, curve, type EqBand } from './eq'
import { logGrid } from './eqFit'

export interface Extremum {
  freq: number
  db: number
}

export interface DiffStats {
  maxPos: Extremum | null
  maxNeg: Extremum | null
  rms: number
}

/** 目标曲线在某频点的值（对数轴线性插值，超出范围取端点） */
export function targetDbAt(points: Array<[number, number]>, freq: number): number {
  if (!points.length) return 0
  if (freq <= points[0][0]) return points[0][1]
  const last = points[points.length - 1]
  if (freq >= last[0]) return last[1]

  let lo = 0
  let hi = points.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (points[mid][0] <= freq) lo = mid
    else hi = mid
  }
  const [f0, g0] = points[lo]
  const [f1, g1] = points[hi]
  if (f1 <= f0) return g0
  const t = (Math.log10(freq) - Math.log10(f0)) / (Math.log10(f1) - Math.log10(f0))
  return g0 + (g1 - g0) * t
}

/** 目标曲线在给定频点上的采样，供画图用 */
export function sampleTarget(points: Array<[number, number]>, freqs: number[]): number[] {
  return freqs.map(f => targetDbAt(points, f))
}

/** 当前曲线与目标曲线的差值统计 */
export function diffStats(bands: EqBand[], target: TargetCurve, n = 160): DiffStats {
  const freqs = logGrid(F_MIN, F_MAX, n)
  const cur = curve(bands, n)
  let maxPos: Extremum | null = null
  let maxNeg: Extremum | null = null
  let sumSq = 0

  for (let i = 0; i < freqs.length; i++) {
    const d = cur.dbs[i] - targetDbAt(target.points, freqs[i])
    sumSq += d * d
    if (!maxPos || d > maxPos.db) maxPos = { freq: freqs[i], db: d }
    if (!maxNeg || d < maxNeg.db) maxNeg = { freq: freqs[i], db: d }
  }

  return { maxPos, maxNeg, rms: Math.sqrt(sumSq / freqs.length) }
}

/** 差值序列（当前 − 目标），供填充区域使用 */
export function diffSeries(bands: EqBand[], target: TargetCurve, n = 160): { freqs: number[]; dbs: number[] } {
  const freqs = logGrid(F_MIN, F_MAX, n)
  const cur = curve(bands, n)
  return { freqs, dbs: freqs.map((f, i) => cur.dbs[i] - targetDbAt(target.points, f)) }
}
