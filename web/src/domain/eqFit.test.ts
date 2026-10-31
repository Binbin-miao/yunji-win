import { describe, expect, it } from 'vitest'
import { buildTarget, fitParsed, gaussSolve, interpLog, logGrid, pickCenters } from './eqFit'
import { parseEqText } from './eqImport'
import type { ParsedEQ } from './eqImport'

const TEN_BANDS = Array.from({ length: 10 }, (_, i) => {
  const freq = Math.round(31 * Math.pow(1000, i / 9))
  const gain = ((i % 5) - 2) * 1.5
  return `Filter ${i + 1}: ON PK Fc ${freq} Hz Gain ${gain} dB Q 1.00`
}).join('\n')

function parsed(text: string): ParsedEQ {
  const r = parseEqText(text)
  if (!r.ok) throw new Error(`解析失败: ${r.error}`)
  return r.result
}

describe('基础工具', () => {
  it('对数网格首尾正确', () => {
    const g = logGrid(20, 20000, 5)
    expect(g[0]).toBeCloseTo(20, 9)
    expect(g[4]).toBeCloseTo(20000, 6)
  })

  it('插值在端点外取端点值', () => {
    const pts: Array<[number, number]> = [[100, 2], [1000, -3]]
    expect(interpLog(pts, 50)).toBe(2)
    expect(interpLog(pts, 5000)).toBe(-3)
    expect(interpLog(pts, 100)).toBe(2)
  })

  it('插值在对数轴中点取值', () => {
    const pts: Array<[number, number]> = [[100, 0], [1000, 10]]
    expect(interpLog(pts, Math.sqrt(100 * 1000))).toBeCloseTo(5, 6)
  })

  it('高斯消元能解简单方程组', () => {
    const x = gaussSolve([[2, 1], [1, 3]], [3, 5])
    expect(x?.[0]).toBeCloseTo(0.8, 9)
    expect(x?.[1]).toBeCloseTo(1.4, 9)
  })

  it('奇异矩阵返回 null 而不是抛错', () => {
    expect(gaussSolve([[1, 2], [2, 4]], [1, 2])).toBeNull()
  })
})

describe('拟合', () => {
  it('10 段配置拟合成 8 段，误差有限且合理', () => {
    const p = parsed(TEN_BANDS)
    expect(p.bands).toHaveLength(10)
    const fit = fitParsed(p)
    expect(fit.bands).toHaveLength(8)
    expect(fit.sourceCount).toBe(10)
    expect(Number.isFinite(fit.maxError)).toBe(true)
    expect(fit.rmsError).toBeLessThan(2)
  })

  it('拟合结果的增益不超出 ±12 dB，频率递增', () => {
    const fit = fitParsed(parsed(TEN_BANDS))
    for (const b of fit.bands) {
      expect(b.gain).toBeLessThanOrEqual(12)
      expect(b.gain).toBeGreaterThanOrEqual(-12)
    }
    const freqs = fit.bands.map(b => b.freq)
    expect([...freqs].sort((a, b) => a - b)).toEqual(freqs)
  })

  it('8 段以内的配置沿用原频率与 Q', () => {
    const r = parseEqText('Filter 1: ON PK Fc 100 Hz Gain 3 dB Q 1.50\nFilter 2: ON PK Fc 2000 Hz Gain -2 dB Q 2.00')
    if (!r.ok) throw new Error('解析失败')
    const fit = fitParsed(r.result)
    expect(fit.bands.map(b => b.freq)).toEqual([100, 2000])
    expect(fit.bands[1].q).toBe(2)
  })

  it('折线（上百点）能拟合成 8 段', () => {
    const pts = Array.from({ length: 100 }, (_, i) => {
      const f = 20 * Math.pow(1000, i / 99)
      const g = 6 * Math.sin(i / 12)
      return `${f.toFixed(1)} ${g.toFixed(2)}`
    }).join('; ')
    const r = parseEqText(`GraphicEQ: ${pts}`)
    if (!r.ok) throw new Error('解析失败')
    const fit = fitParsed(r.result)
    expect(fit.bands).toHaveLength(8)
    expect(fit.sourceCount).toBe(100)
  })

  it('全零目标拟合成接近零的增益', () => {
    const p: ParsedEQ = { bands: [], graphic: [[20, 0], [20000, 0]], preamp: undefined, format: 'x', warnings: [] }
    const fit = fitParsed(p)
    for (const b of fit.bands) expect(Math.abs(b.gain)).toBeLessThan(0.2)
  })

  it('目标曲线与拟合曲线都在拟合点上有值', () => {
    const fit = fitParsed(parsed(TEN_BANDS))
    expect(fit.target.dbs).toHaveLength(160)
    expect(fit.fitted.dbs).toHaveLength(160)
    expect(buildTarget(parsed(TEN_BANDS), logGrid(20, 20000, 160))).toHaveLength(160)
  })

  it('超过 8 段时不沿用源频率，改用均匀布点', () => {
    const centers = pickCenters(parsed(TEN_BANDS))
    expect(centers).toHaveLength(8)
    expect(centers[0]).toBeCloseTo(30, 6)
  })
})
