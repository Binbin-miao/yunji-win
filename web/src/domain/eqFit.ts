/**
 * 把任意段数 / 折线拟合为设备的 8 段参数均衡。
 *
 * 算法对照桌面版 app/yunji/protocol/fitting.py：
 * 以 8 个 biquad 的响应为基函数，在 dB 域做带岭正则的最小二乘，
 * 基函数用「增益 ±0.5 dB 的数值差分」求得，外层次迭代 5 次吸收非线性。
 *
 * 拟合在显示域（48 kHz）进行，与屏幕上的曲线同一套计算，因此预览可信。
 */

import { EQ_DISPLAY_SAMPLE_RATE, F_MAX, F_MIN, bandResponseDb, type EqBand } from './eq'
import type { ParsedEQ } from './eqImport'
import { MAX_GAIN, MAX_Q, MIN_Q } from './eqEdit'

const FIT_POINTS = 160
const FIT_ITERATIONS = 5
const RIDGE = 1e-4
const DEFAULT_Q = 0.75

export interface FitResult {
  bands: EqBand[]
  maxError: number
  rmsError: number
  sourceCount: number
  /** 拟合点上的目标曲线，用于对照预览 */
  target: { freqs: number[]; dbs: number[] }
  fitted: { freqs: number[]; dbs: number[] }
}

export function logGrid(fMin: number, fMax: number, n: number): number[] {
  const ratio = Math.log10(fMax / fMin)
  return Array.from({ length: n }, (_, i) => fMin * Math.pow(10, (i / (n - 1)) * ratio))
}

/** 在对数频率轴上线性插值；超出范围取端点值 */
export function interpLog(points: Array<[number, number]>, f: number): number {
  if (!points.length) return 0
  if (f <= points[0][0]) return points[0][1]
  if (f >= points[points.length - 1][0]) return points[points.length - 1][1]
  let lo = 0
  let hi = points.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (points[mid][0] <= f) lo = mid
    else hi = mid
  }
  const [f0, g0] = points[lo]
  const [f1, g1] = points[hi]
  if (f1 <= f0) return g0
  const t = (Math.log10(f) - Math.log10(f0)) / (Math.log10(f1) - Math.log10(f0))
  return g0 + (g1 - g0) * t
}

/** 一条曲线（若干段的叠加）在给定频点上的响应 */
function sumResponse(freqs: number[], bands: EqBand[]): number[] {
  const out = new Array(freqs.length).fill(0)
  for (const b of bands) {
    for (let k = 0; k < freqs.length; k++) out[k] += bandResponseDb(b, freqs[k], EQ_DISPLAY_SAMPLE_RATE)
  }
  return out
}

/** 高斯消元（部分主元）解 A x = b，奇异时返回 null */
export function gaussSolve(A: number[][], b: number[]): number[] | null {
  const n = b.length
  const M = A.map((row, i) => [...row, b[i]])
  for (let col = 0; col < n; col++) {
    let piv = col
    for (let r = col + 1; r < n; r++) if (Math.abs(M[r][col]) > Math.abs(M[piv][col])) piv = r
    if (Math.abs(M[piv][col]) < 1e-12) return null
    if (piv !== col) [M[col], M[piv]] = [M[piv], M[col]]
    const pv = M[col][col]
    for (let r = col + 1; r < n; r++) {
      const factor = M[r][col] / pv
      if (factor === 0) continue
      for (let c = col; c <= n; c++) M[r][c] -= factor * M[col][c]
    }
  }
  const x = new Array(n).fill(0)
  for (let r = n - 1; r >= 0; r--) {
    let s = M[r][n]
    for (let c = r + 1; c < n; c++) s -= M[r][c] * x[c]
    x[r] = s / M[r][r]
  }
  return x
}

/** 带岭正则的最小二乘 */
function ridgeLstsq(basis: number[][], y: number[]): number[] | null {
  const m = basis.length
  const n = y.length
  const A = Array.from({ length: m }, () => new Array(m).fill(0))
  const rhs = new Array(m).fill(0)
  for (let i = 0; i < m; i++) {
    const bi = basis[i]
    for (let j = i; j < m; j++) {
      const bj = basis[j]
      let s = 0
      for (let k = 0; k < n; k++) s += bi[k] * bj[k]
      A[i][j] = s
      A[j][i] = s
    }
    let r = 0
    for (let k = 0; k < n; k++) r += bi[k] * y[k]
    rhs[i] = r
  }
  let trace = 0
  for (let i = 0; i < m; i++) trace += A[i][i]
  const lam = RIDGE * (m ? trace / m : 1)
  for (let i = 0; i < m; i++) A[i][i] += lam
  return gaussSolve(A, rhs)
}

/** 解析结果 → 目标频响 */
export function buildTarget(parsed: ParsedEQ, freqs: number[]): number[] {
  if (parsed.graphic.length) return freqs.map(f => interpLog(parsed.graphic, f))
  if (parsed.bands.length) return sumResponse(freqs, parsed.bands)
  return freqs.map(() => 0)
}

/** 中心频率选择：源不超过 8 段就沿用，否则在 30–16k 对数轴均匀取 8 个 */
export function pickCenters(parsed: ParsedEQ): number[] {
  if (parsed.bands.length && parsed.bands.length <= 8) {
    return parsed.bands
      .map(b => b.freq)
      .sort((a, b) => a - b)
      .map(f => Math.max(F_MIN, Math.min(F_MAX, f)))
  }
  return logGrid(30, 16000, 8)
}

const clampQ = (q: number) => Math.max(MIN_Q, Math.min(MAX_Q, q))

export function fitParsed(parsed: ParsedEQ): FitResult {
  const centers = pickCenters(parsed)
  const source = parsed.bands.length && parsed.bands.length <= 8
    ? parsed.bands.slice().sort((a, b) => a.freq - b.freq)
    : null
  const qs = source ? source.map(b => clampQ(b.q > 0 ? b.q : DEFAULT_Q)) : centers.map(() => DEFAULT_Q)

  const freqs = logGrid(F_MIN, F_MAX, FIT_POINTS)
  const target = buildTarget(parsed, freqs)
  const sourceCount = parsed.bands.length || parsed.graphic.length

  let gains = centers.map(() => 0)
  const makeBands = (g: number[]) => centers.map((freq, i) => ({ freq, q: qs[i], gain: g[i] }))

  for (let iter = 0; iter < FIT_ITERATIONS; iter++) {
    const cur = sumResponse(freqs, makeBands(gains))
    const resid = target.map((t, k) => t - cur[k])

    const basis: number[][] = []
    for (let i = 0; i < centers.length; i++) {
      const gp = [...gains]
      gp[i] += 0.5
      const gm = [...gains]
      gm[i] -= 0.5
      const rp = sumResponse(freqs, makeBands(gp))
      const rm = sumResponse(freqs, makeBands(gm))
      basis.push(rp.map((v, k) => v - rm[k]))
    }

    const delta = ridgeLstsq(basis, resid)
    if (!delta) break

    const next = gains.map((g, i) => Math.max(-MAX_GAIN, Math.min(MAX_GAIN, g + delta[i])))
    let moved = 0
    for (let i = 0; i < next.length; i++) moved = Math.max(moved, Math.abs(next[i] - gains[i]))
    gains = next
    if (moved < 1e-4) break
  }

  const bands = makeBands(gains).map(b => ({
    freq: Math.round(b.freq),
    q: Math.round(b.q * 100) / 100,
    gain: Math.round(b.gain * 10) / 10,
  }))

  const fittedDbs = sumResponse(freqs, bands)
  const errs = target.map((t, k) => t - fittedDbs[k])
  const maxError = errs.reduce((m, e) => Math.max(m, Math.abs(e)), 0)
  const rmsError = Math.sqrt(errs.reduce((s, e) => s + e * e, 0) / (errs.length || 1))

  return {
    bands,
    maxError,
    rmsError,
    sourceCount,
    target: { freqs, dbs: target },
    fitted: { freqs, dbs: fittedDbs },
  }
}
