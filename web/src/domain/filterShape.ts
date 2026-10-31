/**
 * 5 档滤波模式的**示意**频响曲线（不是实测数据）。
 *
 * 厂商只给了 5 个名字，没有任何实测曲线，所以这里按数字滤波器的常识画：
 * - 陡降：通带到 ~19 kHz，之后在 22 kHz 附近陡然掉下去
 * - 缓降：从十几 kHz 就开始缓坡，高频整体偏软
 * - 无过采样：通带平坦，Nyquist 附近出现混叠（画成抖动）
 *
 * 「低延迟」与「相位补偿」频响相同，差别在振铃位置（见 ringing）。
 * 横轴用 0–24 kHz 线性（48 kHz 采样域的 Nyquist），对数轴会把 15–24 kHz 挤成一条缝，看不出陡缓差别。
 */

/** 示意图的横轴上限：48 kHz 采样率下的 Nyquist */
export const FILTER_MAX_HZ = 24000

export interface FilterShape {
  freqs: number[]
  dbs: number[]
}

/** 振铃位置：低延迟=只在脉冲之后，相位补偿=前后对称（线性相位） */
export type Ringing = 'post' | 'both'

export function ringingOf(mode: number): Ringing {
  return mode === 1 || mode === 3 ? 'both' : 'post'
}

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)))
  return t * t * (3 - 2 * t)
}

/** 单个频点的示意衰减量（dB，0 为通带） */
export function filterDbAt(mode: number, f: number): number {
  switch (mode) {
    case 0:
    case 1: // 陡降（两档频响相同）
      return -92 * smoothstep(20500, 22500, f)
    case 2:
    case 3: // 缓降（两档频响相同）
      return -34 * Math.pow(f / FILTER_MAX_HZ, 3)
    case 4: // 无过采样：通带平坦，20 kHz 以上混叠成抖动
      return f <= 20000 ? -0.6 * Math.pow(f / 20000, 2) : -4 + 5 * Math.sin((f - 20000) / 260)
    default:
      return 0
  }
}

/** 采样一张示意曲线，n 个点，横轴 0–24 kHz 线性 */
export function filterResponse(mode: number, n = 120): FilterShape {
  const freqs = Array.from({ length: n }, (_, i) => (i / (n - 1)) * FILTER_MAX_HZ)
  return { freqs, dbs: freqs.map(f => filterDbAt(mode, f)) }
}
