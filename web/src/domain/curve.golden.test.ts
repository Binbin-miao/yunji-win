import { describe, expect, it } from 'vitest'
import { DEMO_BANDS, curve } from './eq'

/**
 * 16 号工单的防回归：性能优化只许改画法，不许改形状。
 * 下面两组数是从 06 号工单的渲染逻辑里取的，任何改动导致曲线变形都会在这里失败。
 */
const PICKS = [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200, 220, 239]
const GOLDEN_FREQS = [
  20, 35.651, 63.551, 113.284, 201.936, 359.965, 641.662, 1143.805, 2038.911, 3634.496, 6478.735,
  11548.784, 20000,
]
const GOLDEN_DBS = [
  0.7189, 2.0412, 3.4919, 2.7432, 0.2043, -1.3848, -1.1935, 0.6868, 2.1991, -0.5971, 0.4025,
  0.4742, 0.0263,
]

describe('曲线形状黄金值', () => {
  it('240 点采样的频率轴与增益逐点一致', () => {
    const { freqs, dbs } = curve(DEMO_BANDS, 240)
    PICKS.forEach((i, k) => {
      expect(freqs[i]).toBeCloseTo(GOLDEN_FREQS[k], 2)
      expect(dbs[i]).toBeCloseTo(GOLDEN_DBS[k], 3)
    })
  })

  it('采样点数加密后形状不变：2000 点插值到同一批频率仍是同一根线', () => {
    const dense = curve(DEMO_BANDS, 2000)
    const at = (f: number) => {
      for (let i = 1; i < dense.freqs.length; i++) {
        if (dense.freqs[i] >= f) {
          const t = (f - dense.freqs[i - 1]) / (dense.freqs[i] - dense.freqs[i - 1])
          return dense.dbs[i - 1] + t * (dense.dbs[i] - dense.dbs[i - 1])
        }
      }
      return dense.dbs[dense.dbs.length - 1]
    }
    GOLDEN_FREQS.forEach((f, k) => {
      expect(Math.abs(at(f) - GOLDEN_DBS[k]), `${f} Hz 处形状变了`).toBeLessThan(0.05)
    })
  })
})
