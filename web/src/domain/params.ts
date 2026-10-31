/**
 * 参数显示换算。
 *
 * 设备返回的是 DAC 原始值。桌面版的 SliderRow 有个容易看错的地方：
 * `set_value(raw + 30)` 设的是**滑杆位置**，而真正显示的文字由 `value_fmt` 渲染成 `pos - 30`，
 * 也就是**原始值**。所以麦克风、平衡的显示值 = 原始值，只有音量需要加 offset。
 *
 * 依据：pages_device.py 的 mic_row / bal_row / _vol_text。
 */

import type { ChipType } from '../data/devices'

export interface VolRange {
  min: number
  max: number
  /** 显示值 = 原始值 + offset */
  offset: number
}

/** 与 config.py 的 TTGK_MIN/MAX_DAC_VOL、TTGK_DAC_VOL_OFFSET 一致 */
export const DAC_VOL: Record<ChipType, VolRange> = {
  cb5100: { min: -60, max: 0, offset: 60 },
  cb1200: { min: -8, max: 4, offset: 0 },
}

/** 音量显示值（cb5100 为 0..60，cb1200 为 −8..+4） */
export const volDisplay = (raw: number, chip: ChipType): number => raw + DAC_VOL[chip].offset

/** 滑杆的显示值区间——滑块必须用这个，不能用 0..span，否则 cb1200 的负档拖不到 */
export const volBounds = (chip: ChipType): { min: number; max: number } => {
  const r = DAC_VOL[chip]
  return { min: r.min + r.offset, max: r.max + r.offset }
}

/** 显示值反算原始值，并夹到芯片量程内 */
export const volRaw = (display: number, chip: ChipType): number => {
  const r = DAC_VOL[chip]
  return Math.max(r.min, Math.min(r.max, Math.round(display - r.offset)))
}

/** 麦克风：原始值即显示值，范围 −30..30 */
export const micDisplay = (raw: number): string => (raw > 0 ? `+${raw}` : String(raw))

/** 声道平衡：原始值即显示值，−20..20 */
export const balDisplay = (raw: number): string =>
  raw > 0 ? `右 ${raw}` : raw < 0 ? `左 ${-raw}` : '居中'
