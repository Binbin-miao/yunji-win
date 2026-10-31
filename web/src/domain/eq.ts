/**
 * 参数均衡器的频响计算（显示用）。
 *
 * 两个采样率不能混：
 * - 显示曲线用 48000 Hz（EQ_DISPLAY_SAMPLE_RATE），与桌面版/官方 App 的曲线一致
 * - 写入设备的 DSP 系数用 96000 Hz（EQ_DEVICE_SAMPLE_RATE），见协议参考第三章
 *
 * 官方只使用峰值（peaking）滤波器，类型字节恒为 0x02，因此这里不建模低架/高架。
 */

export const EQ_DISPLAY_SAMPLE_RATE = 48000
export const F_MIN = 20
export const F_MAX = 20000
export const DB_RANGES = [6, 12] as const

export interface EqBand {
  freq: number
  q: number
  gain: number
}

export const DEFAULT_BANDS: EqBand[] = [60, 120, 250, 500, 1000, 2000, 4000, 8000].map(freq => ({
  freq,
  q: 0.75,
  gain: 0,
}))

/** 模拟器用的示例曲线，让界面有东西可看 */
export const DEMO_BANDS: EqBand[] = [
  { freq: 60, q: 0.7, gain: 3 },
  { freq: 120, q: 0.9, gain: 1.5 },
  { freq: 250, q: 1.0, gain: -1 },
  { freq: 500, q: 1.2, gain: -2 },
  { freq: 1000, q: 1.4, gain: 0.5 },
  { freq: 2000, q: 1.4, gain: 2.5 },
  { freq: 4000, q: 1.2, gain: -1.5 },
  { freq: 8000, q: 0.9, gain: 1 },
]

interface Coeffs {
  b0: number
  b1: number
  b2: number
  a1: number
  a2: number
}

/** 峰值滤波器系数（已按 a0 归一化） */
export function peakCoeffs(freq: number, q: number, gain: number, sr = EQ_DISPLAY_SAMPLE_RATE): Coeffs {
  const A = Math.pow(10, gain / 40)
  const w0 = (2 * Math.PI * freq) / sr
  const cw = Math.cos(w0)
  const alpha = Math.sin(w0) / (2 * q)
  const a0 = 1 + alpha / A
  return {
    b0: (1 + alpha * A) / a0,
    b1: (-2 * cw) / a0,
    b2: (1 - alpha * A) / a0,
    a1: (-2 * cw) / a0,
    a2: (1 - alpha / A) / a0,
  }
}

/** 单段在某频点的响应（dB） */
export function bandResponseDb(
  band: EqBand,
  freq: number,
  sr = EQ_DISPLAY_SAMPLE_RATE,
): number {
  const c = peakCoeffs(band.freq, band.q, band.gain, sr)
  const w = (2 * Math.PI * freq) / sr
  const cw = Math.cos(w)
  const sw = Math.sin(w)
  const c2 = Math.cos(2 * w)
  const s2 = Math.sin(2 * w)
  const num = Math.hypot(c.b0 + c.b1 * cw + c.b2 * c2, c.b1 * sw + c.b2 * s2)
  const den = Math.hypot(1 + c.a1 * cw + c.a2 * c2, c.a1 * sw + c.a2 * s2)
  return den === 0 ? 0 : 20 * Math.log10(num / den)
}

/** 8 段叠加后的响应（dB） */
export function sumResponseDb(bands: EqBand[], freq: number, sr = EQ_DISPLAY_SAMPLE_RATE): number {
  let total = 0
  for (const band of bands) total += bandResponseDb(band, freq, sr)
  return total
}

/** 对数频率轴上的均匀取点 */
export function logFreqs(n: number, fMin = F_MIN, fMax = F_MAX): number[] {
  const ratio = Math.log10(fMax / fMin)
  return Array.from({ length: n }, (_, i) => fMin * Math.pow(10, (i / (n - 1)) * ratio))
}

/** 整条曲线（对数轴均匀取点） */
export function curve(bands: EqBand[], n = 220): { freqs: number[]; dbs: number[] } {
  const freqs = logFreqs(n)
  return { freqs, dbs: freqs.map(f => sumResponseDb(bands, f)) }
}

/** 频率映射到 0..1 的横向比例 */
export const freqToRatio = (freq: number, fMin = F_MIN, fMax = F_MAX): number =>
  Math.log10(freq / fMin) / Math.log10(fMax / fMin)

/** dB 映射到 0..1 的纵向比例（0 在中间） */
export const dbToRatio = (db: number, range: number): number => 0.5 - db / (2 * range)
