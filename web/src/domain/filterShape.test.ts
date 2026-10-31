import { describe, expect, it } from 'vitest'
import { FILTER_MAX_HZ, filterDbAt, filterResponse, ringingOf } from './filterShape'

/**
 * 示意曲线的形状约定。这些不是"实测精度"断言，而是防止改参数时把三类的差别抹平：
 * 陡降要真的陡、缓降要真的缓、无过采样要有混叠抖动、相位补偿与低延迟频响必须一致。
 */
describe('滤波模式示意曲线', () => {
  it('陡降在 22 kHz 之后基本到底，通带保持平坦', () => {
    expect(filterDbAt(0, 18000)).toBeGreaterThan(-1)
    expect(filterDbAt(0, 22000)).toBeLessThan(-30)
    expect(filterDbAt(0, FILTER_MAX_HZ)).toBeLessThan(-80)
  })

  it('缓降是缓坡：16 kHz 才开始明显掉，24 kHz 也没到底', () => {
    expect(filterDbAt(2, 12000)).toBeGreaterThan(-6)
    expect(filterDbAt(2, 16000)).toBeLessThan(-8)
    expect(filterDbAt(2, FILTER_MAX_HZ)).toBeGreaterThan(-40)
  })

  it('缓降比陡降在 20 kHz 处明显更高（不能画成同一根线）', () => {
    expect(filterDbAt(0, 20000)).toBeGreaterThan(-1) // 陡降在 20 kHz 还基本平坦
    expect(filterDbAt(2, 20000)).toBeLessThan(-15) // 缓降此时已经掉了不少
  })

  it('无过采样通带平坦，20 kHz 以上出现混叠抖动', () => {
    expect(filterDbAt(4, 8000)).toBeGreaterThan(-1)
    const tail = [20000, 21000, 22000, 23000, 24000].map(f => filterDbAt(4, f))
    const spread = Math.max(...tail) - Math.min(...tail)
    expect(spread).toBeGreaterThan(4)
  })

  it('低延迟与相位补偿频响相同，差别只在振铃位置', () => {
    for (const f of [1000, 12000, 20000, 23000]) {
      expect(filterDbAt(0, f)).toBeCloseTo(filterDbAt(1, f), 6)
      expect(filterDbAt(2, f)).toBeCloseTo(filterDbAt(3, f), 6)
    }
    expect(ringingOf(0)).toBe('post')
    expect(ringingOf(2)).toBe('post')
    expect(ringingOf(1)).toBe('both')
    expect(ringingOf(3)).toBe('both')
  })

  it('采样点数与横轴范围固定，五档都覆盖完整轴', () => {
    for (let mode = 0; mode < 5; mode++) {
      const r = filterResponse(mode)
      expect(r.freqs[0]).toBe(0)
      expect(r.freqs[r.freqs.length - 1]).toBe(FILTER_MAX_HZ)
      expect(r.dbs).toHaveLength(r.freqs.length)
    }
  })
})
