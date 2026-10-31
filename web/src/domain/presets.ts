/**
 * 预设：一组 8 段曲线的命名快照。
 *
 * v1 只存曲线本身，不存音量/滤波这些全局参数 —— 后者一旦「应用」就得写设备，
 * 语义和曲线不同，等后续单独做「设备状态快照」时再处理。
 *
 * 存在浏览器 localStorage，换电脑或清缓存会丢，界面必须明说。
 */

import type { EqBand } from './eq'
import { clampBand } from './eqEdit'

export const PRESET_VERSION = 1
export const STORAGE_KEY = 'yunji.presets.v1'

export interface Preset {
  id: string
  name: string
  bands: EqBand[]
  createdAt: number
}

export interface PresetFile {
  version: number
  presets: Preset[]
}

const makeId = (): string =>
  `p${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`

export function createPreset(name: string, bands: EqBand[]): Preset {
  return {
    id: makeId(),
    name: name.trim() || '未命名预设',
    bands: bands.map(b => clampBand(b)),
    createdAt: Date.now(),
  }
}

/** 校验并规范化一条预设；不合法返回 null */
export function normalizePreset(raw: unknown): Preset | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  if (!Array.isArray(o.bands)) return null
  const bands = o.bands
    .map(b => {
      const r = b as Record<string, unknown>
      const freq = Number(r.freq)
      const q = Number(r.q)
      const gain = Number(r.gain)
      if (!Number.isFinite(freq) || !Number.isFinite(q) || !Number.isFinite(gain)) return null
      return clampBand({ freq, q, gain })
    })
    .filter((b): b is EqBand => b !== null)
  if (!bands.length) return null

  return {
    id: typeof o.id === 'string' && o.id ? o.id : makeId(),
    name: typeof o.name === 'string' && o.name.trim() ? o.name.trim() : '未命名预设',
    bands,
    createdAt: typeof o.createdAt === 'number' ? o.createdAt : Date.now(),
  }
}

/** 导出为文件内容（带版本号，便于以后迁移） */
export function serializePresets(presets: Preset[]): string {
  const file: PresetFile = { version: PRESET_VERSION, presets }
  return JSON.stringify(file, null, 2)
}

/** 解析导入文件；返回预设与错误说明 */
export function parsePresets(text: string): { presets: Preset[]; error?: string } {
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    return { presets: [], error: '不是合法的 JSON 文件' }
  }

  const obj = data as Partial<PresetFile> & { presets?: unknown }
  const list = Array.isArray(obj?.presets)
    ? obj.presets
    : Array.isArray(data)
      ? (data as unknown[])
      : null
  if (!list) return { presets: [], error: '文件里没有 presets 数组' }

  const presets = list.map(normalizePreset).filter((p): p is Preset => p !== null)
  if (!presets.length) return { presets: [], error: '没有解析出任何有效预设（检查 bands 字段）' }
  return { presets }
}
