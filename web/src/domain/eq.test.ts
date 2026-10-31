import { describe, expect, it } from 'vitest'
import {
  DEFAULT_BANDS,
  EQ_DISPLAY_SAMPLE_RATE,
  bandResponseDb,
  curve,
  dbToRatio,
  freqToRatio,
  logFreqs,
  sumResponseDb,
  type EqBand,
} from './eq'

const peak = (freq: number, q: number, gain: number): EqBand => ({ freq, q, gain })

describe('频响计算', () => {
  it('全零曲线在任何频点都是 0 dB', () => {
    for (const f of [20, 100, 1000, 10000, 20000]) {
      expect(Math.abs(sumResponseDb(DEFAULT_BANDS, f))).toBeLessThan(1e-9)
    }
  })

  it('单段峰值在中心频率处等于设定增益', () => {
    const band = peak(1000, 0.75, 6)
    expect(bandResponseDb(band, 1000)).toBeCloseTo(6, 6)
  })

  it('单段峰值在中心频率处等于负增益', () => {
    const band = peak(1000, 0.75, -4.5)
    expect(bandResponseDb(band, 1000)).toBeCloseTo(-4.5, 6)
  })

  it('偏离中心频率后响应衰减', () => {
    const band = peak(1000, 1, 6)
    expect(bandResponseDb(band, 1000)).toBeCloseTo(6, 6)
    expect(bandResponseDb(band, 100)).toBeLessThan(1)
  })

  it('显示域用 48 kHz，不是设备的 96 kHz', () => {
    expect(EQ_DISPLAY_SAMPLE_RATE).toBe(48000)
    // 同一段在 96k 下算出的高频响应会不同，用这个差异锁住采样率不会被改错
    const band = peak(10000, 1, 6)
    const at48 = bandResponseDb(band, 18000, 48000)
    const at96 = bandResponseDb(band, 18000, 96000)
    expect(Math.abs(at48 - at96)).toBeGreaterThan(0.1)
  })
})

describe('坐标映射', () => {
  it('频率端点映射到 0 与 1，中点是几何平均 ', () => {
    expect(freqToRatio(20)).toBeCloseTo(0, 12)
    expect(freqToRatio(20000)).toBeCloseTo(1, 12)
    expect(freqToRatio(Math.sqrt(20 * 20000))).toBeCloseTo(0.5, 6)
  })

  it('dB 映射以 0 为中心', () => {
    expect(dbToRatio(0, 12)).toBeCloseTo(0.5, 12)
    expect(dbToRatio(12, 12)).toBeCloseTo(0, 12)
    expect(dbToRatio(-12, 12)).toBeCloseTo(1, 12)
    expect(dbToRatio(6, 12)).toBeCloseTo(0.25, 12)
  })
})

describe('曲线采样', () => {
  it('对数轴取点首尾落在 20 与 20k', () => {
    const freqs = logFreqs(11)
    expect(freqs[0]).toBeCloseTo(20, 9)
    expect(freqs[10]).toBeCloseTo(20000, 6)
  })

  it('曲线点数与频点数一致', () => {
    const { freqs, dbs } = curve(DEFAULT_BANDS, 50)
    expect(freqs).toHaveLength(50)
    expect(dbs).toHaveLength(50)
  })
})
