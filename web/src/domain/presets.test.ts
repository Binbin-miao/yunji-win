import { describe, expect, it } from 'vitest'
import type { EqBand } from './eq'
import {
  PRESET_VERSION,
  createPreset,
  normalizePreset,
  parsePresets,
  serializePresets,
  type Preset,
} from './presets'

const bands: EqBand[] = [
  { freq: 60, q: 0.7, gain: 3 },
  { freq: 1000, q: 1.4, gain: -2.5 },
]

describe('预设创建与校验', () => {
  it('创建时补全名称并钳制参数', () => {
    const p = createPreset('   ', [{ freq: 999999, q: 99, gain: 99 }])
    expect(p.name).toBe('未命名预设')
    expect(p.bands[0].freq).toBe(20000)
    expect(p.bands[0].gain).toBe(12)
    expect(p.id).toBeTruthy()
  })

  it('拒绝没有 bands 的对象', () => {
    expect(normalizePreset({ name: 'x' })).toBeNull()
    expect(normalizePreset(null)).toBeNull()
    expect(normalizePreset({ bands: [] })).toBeNull()
  })

  it('丢弃非法段、保留合法段', () => {
    const p = normalizePreset({
      name: '半坏',
      bands: [{ freq: 100, q: 1, gain: 2 }, { freq: 'abc', q: 1, gain: 2 }],
    })
    expect(p?.bands).toHaveLength(1)
    expect(p?.name).toBe('半坏')
  })
})

describe('导出与导入', () => {
  it('导出带版本号，导入后内容一致', () => {
    const p = createPreset('监听', bands)
    const text = serializePresets([p])
    expect(JSON.parse(text).version).toBe(PRESET_VERSION)

    const { presets, error } = parsePresets(text)
    expect(error).toBeUndefined()
    expect(presets).toHaveLength(1)
    expect(presets[0].name).toBe('监听')
    expect(presets[0].bands).toEqual(bands)
  })

  it('坏 JSON 给出明确错误', () => {
    const r = parsePresets('{ not json')
    expect(r.presets).toHaveLength(0)
    expect(r.error).toContain('JSON')
  })

  it('缺少 presets 数组时给出错误', () => {
    expect(parsePresets('{"foo":1}').error).toContain('presets')
  })

  it('全部条目都非法时报错而不是静默成功', () => {
    const r = parsePresets('{"presets":[{"name":"空"}]}')
    expect(r.presets).toHaveLength(0)
    expect(r.error).toBeTruthy()
  })

  it('兼容直接是数组的老格式', () => {
    const r = parsePresets(JSON.stringify([{ name: '老格式', bands }]))
    expect(r.presets).toHaveLength(1)
    expect(r.presets[0].name).toBe('老格式')
  })

  it('往返不丢精度', () => {
    const p: Preset = createPreset('精度', [{ freq: 1234, q: 1.23, gain: -4.5 }])
    const back = parsePresets(serializePresets([p])).presets[0]
    expect(back.bands[0]).toEqual({ freq: 1234, q: 1.23, gain: -4.5 })
  })
})
