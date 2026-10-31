import { describe, expect, it } from 'vitest'
import { TARGETS, findTarget } from '../data/targets'
import type { EqBand } from './eq'
import { diffStats, sampleTarget, targetDbAt } from './target'

const flatTarget = { id: 'flat', label: '平直', source: '', validMaxHz: 20000, points: [[20, 0], [20000, 0]] as Array<[number, number]> }

describe('目标曲线取值', () => {
  it('端点外取端点值', () => {
    expect(targetDbAt(flatTarget.points, 5)).toBe(0)
    const ramp: Array<[number, number]> = [[100, 0], [1000, 10]]
    expect(targetDbAt(ramp, 50)).toBe(0)
    expect(targetDbAt(ramp, 5000)).toBe(10)
  })

  it('对数轴中点取到中间值', () => {
    const ramp: Array<[number, number]> = [[100, 0], [1000, 10]]
    expect(targetDbAt(ramp, Math.sqrt(100 * 1000))).toBeCloseTo(5, 6)
  })

  it('采样数量与频点一致', () => {
    expect(sampleTarget(flatTarget.points, [20, 100, 1000])).toEqual([0, 0, 0])
  })

  it('内置三条曲线都存在且点数合理', () => {
    expect(TARGETS).toHaveLength(3)
    for (const t of TARGETS) {
      expect(t.points.length).toBeGreaterThan(50)
      expect(findTarget(t.id)).toBe(t)
    }
  })
})

describe('差值统计', () => {
  const flat: EqBand[] = [60, 120, 250, 500, 1000, 2000, 4000, 8000].map(freq => ({ freq, q: 0.75, gain: 0 }))

  it('曲线与平直目标完全重合时差值接近 0', () => {
    const s = diffStats(flat, flatTarget)
    expect(Math.abs(s.maxPos!.db)).toBeLessThan(1e-9)
    expect(Math.abs(s.maxNeg!.db)).toBeLessThan(1e-9)
    expect(s.rms).toBeLessThan(1e-9)
  })

  it('在 1kHz 抬升时最大正差出现在 1kHz 附近', () => {
    const bands = flat.map(b => (b.freq === 1000 ? { ...b, q: 2, gain: 6 } : b))
    const s = diffStats(bands, flatTarget)
    expect(s.maxPos!.db).toBeGreaterThan(5.5)
    expect(s.maxPos!.freq).toBeGreaterThan(700)
    expect(s.maxPos!.freq).toBeLessThan(1400)
    expect(s.rms).toBeGreaterThan(0)
  })

  it('整体下降时最大负差为负值', () => {
    const bands = flat.map(b => ({ ...b, gain: -3 }))
    const s = diffStats(bands, flatTarget)
    expect(s.maxNeg!.db).toBeLessThan(-2.5)
  })

  it('与真实目标曲线比较不报错且数值有限', () => {
    const s = diffStats(flat, TARGETS[0])
    expect(Number.isFinite(s.rms)).toBe(true)
    expect(Number.isFinite(s.maxPos!.db)).toBe(true)
  })
})
