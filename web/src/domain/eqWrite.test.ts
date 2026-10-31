import { describe, expect, it } from 'vitest'
import type { EqBand } from './eq'
import { bandPacket, deviceCoeffs, eqApplyFrame, eqPackets } from './eqWrite'

/**
 * 黄金样本由桌面版 app/yunji/protocol/eqdata.py 的 EQData.band_packet(0) 生成，
 * 已去掉首字节 0x4B。任何字节偏差都说明两边打包不一致。
 */
const GOLDEN: Array<{ band: EqBand; bytes: number[] }> = [
  {
    band: { freq: 60, q: 0.7, gain: 3 },
    bytes: [1, 9, 24, 0, 0, 0, 0, 22, 234, 15, 64, 226, 103, 77, 128, 143, 238, 162, 63, 30, 152, 178, 127, 91, 39, 77, 192, 60, 0, 192, 0, 0, 3, 2, 0, 0],
  },
  {
    band: { freq: 1000, q: 1.4, gain: 0.5 },
    bytes: [1, 9, 24, 0, 0, 0, 0, 79, 139, 21, 64, 18, 201, 27, 131, 178, 69, 19, 61, 238, 54, 228, 124, 0, 47, 215, 194, 232, 3, 192, 0, 128, 0, 2, 0, 0],
  },
  {
    band: { freq: 8000, q: 0.9, gain: -1.5 },
    bytes: [1, 9, 24, 0, 0, 0, 0, 153, 252, 163, 61, 58, 59, 234, 170, 236, 110, 155, 36, 198, 196, 21, 85, 124, 148, 192, 221, 64, 31, 192, 0, 128, 254, 2, 0, 0],
  },
  {
    band: { freq: 120, q: 0.75, gain: 0 },
    bytes: [1, 9, 24, 0, 0, 0, 0, 0, 0, 0, 64, 204, 174, 171, 128, 148, 82, 85, 63, 52, 81, 84, 127, 108, 173, 170, 192, 120, 0, 192, 0, 0, 0, 2, 0, 0],
  },
]

describe('EQ 设备封包', () => {
  it.each(GOLDEN)('与桌面版逐字节一致：$band.freq Hz / $band.gain dB', ({ band, bytes }) => {
    expect(bandPacket(0, band)).toEqual(bytes)
  })

  it('负载长度固定 36 字节（含报告 ID 则为 37）', () => {
    expect(bandPacket(0, GOLDEN[0].band)).toHaveLength(36)
  })

  it('报文头包含段号，类型字节恒为 02', () => {
    const p = bandPacket(3, GOLDEN[0].band)
    expect(p.slice(0, 7)).toEqual([0x01, 0x09, 0x18, 0x00, 3, 0x00, 0x00])
    expect(p[33]).toBe(0x02)
    expect(p[35]).toBe(0x00)
  })

  it('频率以小端写入，Q 字段恒为 C0 00', () => {
    const p = bandPacket(0, { freq: 1000, q: 1.4, gain: 0.5 })
    expect(p[27] | (p[28] << 8)).toBe(1000)
    expect(p.slice(29, 31)).toEqual([0xc0, 0x00])
  })

  it('负增益的整数部分按补码写入', () => {
    const p = bandPacket(0, { freq: 8000, q: 0.9, gain: -1.5 })
    expect(p[31]).toBe(128) // 小数部分 0.5 × 256
    expect(p[32]).toBe(254) // -2 的补码
  })

  it('offset 写入到正确位置', () => {
    const p = bandPacket(0, GOLDEN[0].band, -3)
    expect(p[34]).toBe(253)
  })

  it('系数是 5 个 int32，且 Q30 量级合理', () => {
    const coeffs = deviceCoeffs({ freq: 1000, q: 1, gain: 0 })
    expect(coeffs).toHaveLength(5)
    // 增益为 0 时 b0 应接近 2^30
    expect(Math.abs(coeffs[0]) / 2 ** 30).toBeCloseTo(1, 1)
  })

  it('8 段生成 8 个负载，段号递增', () => {
    const bands = Array.from({ length: 8 }, (_, i) => ({ freq: 100 * (i + 1), q: 0.75, gain: 0 }))
    const packets = eqPackets(bands)
    expect(packets).toHaveLength(8)
    packets.forEach((p, i) => expect(p[4]).toBe(i))
  })

  it('生效帧与协议文档一致', () => {
    expect(eqApplyFrame()).toEqual([0x01, 0x0a, 0x04, 0x00, 0x00, 0xff, 0xff])
  })
})
