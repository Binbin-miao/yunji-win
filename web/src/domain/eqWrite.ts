/**
 * 8 段 EQ 的设备封包（写入用）。
 *
 * 与显示曲线的关键差别：
 * - 系数用 **96000 Hz** 计算（设备 DSP 采样率），不是显示用的 48000
 * - 系数打成 Q30 定点（×2^30，Java 的 floor(x+0.5) 取整）
 * - 单段负载 36 字节（不含报告 ID），完整 37 字节含首字节 0x4B
 *
 * 报文结构（去掉 0x4B 后）：
 * [01 09 18 00 idx 00 00] + 20B 系数 + 2B 频率 + 2B Q 占位(C0 00)
 * + 2B 增益 + 1B 类型(恒 02) + 1B offset + 1B 尾 00
 */

import type { EqBand } from './eq'

export const EQ_DEVICE_SAMPLE_RATE = 96000
const TWO_POW_30 = 2 ** 30
/** Java Math.round(double) = floor(x + 0.5)，负数时与 JS 的 Math.round 不同 */
const javaRound = (x: number) => Math.floor(x + 0.5)

const i32le = (v: number): number[] => {
  const u = v >>> 0
  return [u & 0xff, (u >>> 8) & 0xff, (u >>> 16) & 0xff, (u >>> 24) & 0xff]
}

const i16le = (v: number): number[] => {
  const u = v & 0xffff
  return [u & 0xff, (u >> 8) & 0xff]
}

/** 96 kHz 下的峰值滤波器系数，按 a0 归一化后转成 Q30 整数 */
export function deviceCoeffs(band: EqBand): number[] {
  const A = Math.pow(10, band.gain / 40)
  const w0 = (2 * Math.PI * band.freq) / EQ_DEVICE_SAMPLE_RATE
  const cw = Math.cos(w0)
  const alpha = Math.sin(w0) / (2 * band.q)
  const a0 = 1 + alpha / A
  const b0 = (1 + alpha * A) / a0
  const b1 = (-2 * cw) / a0
  const b2 = (1 - alpha * A) / a0
  const a1 = (-2 * cw) / a0
  const a2 = (1 - alpha / A) / a0
  return [b0, b1, b2, -a1, -a2].map(v => javaRound(v * TWO_POW_30))
}

/** 单段负载（不含报告 ID），36 字节 */
export function bandPacket(index: number, band: EqBand, offset = 0): number[] {
  const gain = band.gain
  const floorGain = Math.floor(gain)
  // 小数部分截断取低 8 位（与桌面版 int((gain-floor)*256) 一致）
  const frac = Math.trunc((gain - floorGain) * 256) & 0xff

  const head = [0x01, 0x09, 0x18, 0x00, index & 0xff, 0x00, 0x00]
  const coeffs = deviceCoeffs(band).flatMap(i32le)
  const freq = i16le(Math.round(band.freq))
  const q = [0xc0, 0x00]
  const gainBytes = [frac, floorGain & 0xff]
  const type = [0x02]
  const off = [offset & 0xff]
  const tail = [0x00]

  return [...head, ...coeffs, ...freq, ...q, ...gainBytes, ...type, ...off, ...tail]
}

/** EQ 生效提交帧：01 0A 04 00 00 FF FF */
export const eqApplyFrame = (): number[] => [0x01, 0x0a, 0x04, 0x00, 0x00, 0xff, 0xff]

/** 8 段的完整负载序列 */
export function eqPackets(bands: EqBand[], offset = 0): number[][] {
  return bands.map((band, i) => bandPacket(i, band, offset))
}
