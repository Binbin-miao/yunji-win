/** 预设的本地存储（localStorage）。读写失败不抛错，交给界面提示。 */

import { STORAGE_KEY, normalizePreset, type Preset } from '../domain/presets'

export function loadPresets(): { presets: Preset[]; error?: string } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { presets: [] }
    const list = JSON.parse(raw)
    if (!Array.isArray(list)) return { presets: [], error: '本地数据格式异常，已忽略' }
    return { presets: list.map(normalizePreset).filter((p): p is Preset => p !== null) }
  } catch {
    return { presets: [], error: '读取本地预设失败（浏览器可能禁用了存储）' }
  }
}

export function savePresets(presets: Preset[]): string | null {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(presets))
    return null
  } catch {
    return '保存失败：浏览器存储不可用或已写满'
  }
}
