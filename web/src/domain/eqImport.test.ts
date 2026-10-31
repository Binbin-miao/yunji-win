import { describe, expect, it } from 'vitest'
import { bwToQ, parseEqText } from './eqImport'

const APO = `# AutoEQ export
Preamp: -6.0 dB
Filter 1: ON PK Fc 105 Hz Gain -3.2 dB Q 0.70
Filter 2: ON PK Fc 1000 Hz Gain +2.5 dB Q 1.20
Filter 3: OFF PK Fc 3000 Hz Gain 5.0 dB Q 1.00
Filter 4: ON LS Fc 200 Hz Gain -4.0 dB Q 0.71
`

describe('Equalizer APO 解析', () => {
  it('解析出启用段、跳过 OFF 行、读到 Preamp', () => {
    const r = parseEqText(APO)
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.result.format).toBe('Equalizer APO')
    expect(r.result.preamp).toBe(-6)
    expect(r.result.bands).toHaveLength(3)
    expect(r.result.bands[0]).toEqual({ freq: 105, q: 0.7, gain: -3.2 })
    expect(r.result.bands[1].gain).toBe(2.5)
  })

  it('低架/高架给出近似警告', () => {
    const r = parseEqText(APO)
    if (!r.ok) return
    expect(r.result.warnings.join()).toContain('峰值')
  })

  it('支持 BW 换算成 Q', () => {
    const r = parseEqText('Filter 1: ON PK Fc 500 Hz Gain 2 dB BW 1.0')
    if (!r.ok) return
    expect(r.result.bands[0].q).toBeCloseTo(bwToQ(1), 2)
  })

  it('没有滤波器行时报错并给出示例', () => {
    const r = parseEqText('hello world')
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toContain('Filter')
  })
})

describe('GraphicEQ 解析', () => {
  it('解析上百个点且不丢点', () => {
    const pts = Array.from({ length: 120 }, (_, i) => `${20 + i * 10} ${(i % 7) - 3}`).join('; ')
    const r = parseEqText(`GraphicEQ: ${pts}`)
    if (!r.ok) throw new Error('应解析成功')
    expect(r.result.format).toBe('GraphicEQ')
    expect(r.result.graphic).toHaveLength(120)
    expect(r.result.graphic[0][0]).toBe(20)
  })

  it('按频率升序排列', () => {
    const r = parseEqText('GraphicEQ: 1000 -1; 100 2; 10000 -3')
    if (!r.ok) return
    expect(r.result.graphic.map(p => p[0])).toEqual([100, 1000, 10000])
  })

  it('只有表头没有数值时报错', () => {
    const r = parseEqText('GraphicEQ: ')
    expect(r.ok).toBe(false)
  })
})

describe('Wavelet 与原生 JSON', () => {
  it('解析 Wavelet 的 graphicEQ', () => {
    const r = parseEqText(JSON.stringify({ graphicEQ: [[20, -3.5], [25, -3.2]] }))
    if (!r.ok) return
    expect(r.result.format).toBe('Wavelet')
    expect(r.result.graphic).toHaveLength(2)
  })

  it('解析原生 bands 并钳制参数', () => {
    const r = parseEqText(
      JSON.stringify({ bands: [{ freq: 999999, q: 0.5, gain: 99 }], preamp: -3 }),
    )
    if (!r.ok) return
    expect(r.result.format).toBe('本工具格式')
    expect(r.result.bands[0]).toEqual({ freq: 20000, q: 0.5, gain: 12 })
    expect(r.result.preamp).toBe(-3)
  })

  it('坏 JSON 给出明确错误', () => {
    const r = parseEqText('{"bands": [')
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toContain('JSON')
  })

  it('JSON 里没有可用字段时报错', () => {
    const r = parseEqText('{"foo": 1}')
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.error).toContain('bands')
  })

  it('空内容报错', () => {
    expect(parseEqText('   ').ok).toBe(false)
  })
})
