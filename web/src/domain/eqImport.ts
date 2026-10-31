/**
 * EQ 导入解析：支持社区流通的四种格式。
 *
 * 1. Equalizer APO / AutoEQ 参数式：Filter 1: ON PK Fc 105 Hz Gain -3.2 dB Q 0.70
 * 2. GraphicEQ：GraphicEQ: 20 -3.5; 25 -3.2; …
 * 3. Wavelet JSON：{"graphicEQ": [[20,-3.5], …]}
 * 4. 本工具原生 JSON：{"bands":[{"freq","q","gain"}]}
 *
 * 解析逻辑对照桌面版 app/yunji/protocol/eqformat.py。
 * 注意：本工具只建模峰值滤波器，APO 的 LS/HS 会被当作峰值近似并给出警告。
 */

import type { EqBand } from './eq'
import { clampBand } from './eqEdit'

export interface ParsedEQ {
  bands: EqBand[]
  /** 频响折线（GraphicEQ / Wavelet），需要拟合才能变成 8 段 */
  graphic: Array<[number, number]>
  preamp?: number
  format: string
  warnings: string[]
}

export type ParseResult = { ok: true; result: ParsedEQ } | { ok: false; error: string }

const APO_LINE = /Filter\s*\d*\s*:\s*(ON|OFF)?\s*([A-Za-z]+)(.*)$/i
const APO_KV = /(Fc|Gain|Q|BW)\s+([+-]?\d+(?:\.\d+)?)/gi
const GRAPHIC_HEAD = /GraphicEQ\s*:\s*/i
const GRAPHIC_PAIR = /([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)/g

const APO_TYPES = new Set(['PK', 'PEQ', 'MODAL', 'LS', 'LSC', 'LSH', 'HS', 'HSC', 'HSH'])
const SHELF_TYPES = new Set(['LS', 'LSC', 'LSH', 'HS', 'HSC', 'HSH'])

/** 带宽（八度）→ Q */
export function bwToQ(bw: number): number {
  if (!(bw > 0)) return 0.75
  return 1 / (2 * (Math.pow(2, bw / 2) - Math.pow(2, -bw / 2)))
}

function parseApo(text: string): ParsedEQ {
  const out: ParsedEQ = { bands: [], graphic: [], format: 'Equalizer APO', warnings: [] }
  let shelfCount = 0

  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line || line.startsWith('#') || line.startsWith('//')) continue

    const pre = line.match(/Preamp\s*:\s*(-?\d+(?:\.\d+)?)\s*dB/i)
    if (pre) {
      out.preamp = Number(pre[1])
      continue
    }

    const m = line.match(APO_LINE)
    if (!m) continue
    if ((m[1] ?? 'ON').toUpperCase() === 'OFF') continue
    const type = m[2].toUpperCase()
    if (!APO_TYPES.has(type)) continue
    if (SHELF_TYPES.has(type)) shelfCount++

    const kv: Record<string, number> = {}
    for (const hit of m[3].matchAll(APO_KV)) kv[hit[1].toUpperCase()] = Number(hit[2])
    if (kv.FC === undefined) continue

    const q = kv.Q ?? (kv.BW !== undefined ? bwToQ(kv.BW) : 0.75)
    out.bands.push(clampBand({ freq: kv.FC, q, gain: kv.GAIN ?? 0 }))
  }

  if (shelfCount > 0) {
    out.warnings.push(`有 ${shelfCount} 段低架/高架滤波器，本工具只支持峰值，已按峰值近似`)
  }
  return out
}

function parseGraphic(text: string): ParsedEQ {
  const m = text.match(GRAPHIC_HEAD)
  const out: ParsedEQ = { bands: [], graphic: [], format: 'GraphicEQ', warnings: [] }
  if (!m) return out
  const body = text.slice((m.index ?? 0) + m[0].length)
  for (const hit of body.matchAll(GRAPHIC_PAIR)) {
    out.graphic.push([Number(hit[1]), Number(hit[2])])
  }
  out.graphic.sort((a, b) => a[0] - b[0])
  return out
}

function parseWavelet(obj: Record<string, unknown>): ParsedEQ | null {
  const pts = obj.graphicEQ
  if (!Array.isArray(pts) || !pts.length) return null
  const graphic: Array<[number, number]> = []
  for (const p of pts) {
    if (Array.isArray(p) && p.length >= 2) {
      const f = Number(p[0])
      const g = Number(p[1])
      if (Number.isFinite(f) && Number.isFinite(g)) graphic.push([f, g])
    }
  }
  if (!graphic.length) return null
  graphic.sort((a, b) => a[0] - b[0])
  return { bands: [], graphic, format: 'Wavelet', warnings: [] }
}

function parseNative(obj: Record<string, unknown>): ParsedEQ | null {
  const raw = obj.bands
  if (!Array.isArray(raw) || !raw.length) return null
  const bands: EqBand[] = []
  for (const b of raw) {
    if (!b || typeof b !== 'object') continue
    const r = b as Record<string, unknown>
    const freq = Number(r.freq ?? 1000)
    const q = Number(r.q ?? 0.75)
    const gain = Number(r.gain ?? 0)
    if (!Number.isFinite(freq) || !Number.isFinite(q) || !Number.isFinite(gain)) continue
    bands.push(clampBand({ freq, q, gain }))
  }
  if (!bands.length) return null
  const out: ParsedEQ = { bands, graphic: [], format: '本工具格式', warnings: [] }
  const pre = Number(obj.preamp)
  if (Number.isFinite(pre)) out.preamp = pre
  return out
}

/** 自动嗅探格式并解析 */
export function parseEqText(text: string): ParseResult {
  const src = text.trim()
  if (!src) return { ok: false, error: '内容为空' }

  if (src.startsWith('{') || src.startsWith('[')) {
    let obj: unknown
    try {
      obj = JSON.parse(src)
    } catch {
      return { ok: false, error: 'JSON 格式错误（括号或逗号不匹配）' }
    }
    if (Array.isArray(obj)) {
      return { ok: false, error: 'JSON 是数组，但没有 bands 字段' }
    }
    if (!obj || typeof obj !== 'object') return { ok: false, error: 'JSON 内容不是对象' }
    const native = parseNative(obj as Record<string, unknown>)
    if (native) return { ok: true, result: native }
    const wavelet = parseWavelet(obj as Record<string, unknown>)
    if (wavelet) return { ok: true, result: wavelet }
    return { ok: false, error: '没有解析出 bands 或 graphicEQ 字段' }
  }

  if (GRAPHIC_HEAD.test(src)) {
    const result = parseGraphic(src)
    if (!result.graphic.length) return { ok: false, error: 'GraphicEQ 里没有成对的「频率 增益」数值' }
    return { ok: true, result }
  }

  const result = parseApo(src)
  if (!result.bands.length) {
    return {
      ok: false,
      error: '没有识别到任何滤波器行，检查是否包含 “Filter 1: ON PK Fc … Gain … Q …” 这类内容',
    }
  }
  return { ok: true, result }
}

/** 把解析结果转成段数组；折线需要外部拟合（见 eqFit） */
export function toBands(result: ParsedEQ): EqBand[] {
  return result.bands
}
