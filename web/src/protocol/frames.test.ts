import { describe, expect, it } from 'vitest'
import {
  CMD,
  PAYLOAD_LEN,
  balanceWriteFrames,
  buildPayload,
  commitFrame,
  filterWriteFrame,
  gainWriteFrame,
  isResponseFor,
  le16,
  ledWriteFrame,
  micWriteFrame,
  readFrame,
  volumeWriteFrame,
  writeFrame,
} from './frames'

describe('帧构造', () => {
  it('负载补零到 63 字节，且首字节不含报告 ID', () => {
    const p = buildPayload(readFrame(CMD.firmware))
    expect(p.length).toBe(PAYLOAD_LEN)
    expect(Array.from(p.slice(0, 4))).toEqual([0x80, 0x0c, 0x00, 0x00])
  })

  it('音量写入帧：01 03 02 lo hi，值为电平 × 256', () => {
    expect(volumeWriteFrame(60)).toEqual([0x01, 0x03, 0x02, 0x00, 0x3c])
    expect(volumeWriteFrame(0)).toEqual([0x01, 0x03, 0x02, 0x00, 0x00])
  })

  it('音量写入帧对负值使用补码', () => {
    // -12 × 256 = -3072 → 0xF400
    expect(volumeWriteFrame(-12)).toEqual([0x01, 0x03, 0x02, 0x00, 0xf4])
  })

  it('提交帧固定为 01 04 00', () => {
    expect(commitFrame()).toEqual([0x01, 0x04, 0x00])
  })

  it('麦克风写入帧：01 02 02 lo hi', () => {
    expect(micWriteFrame(18)).toEqual([0x01, 0x02, 0x02, 0x00, 0x12])
  })

  it('滤波器/增益/指示灯写入帧均为 01 <cmd> 01 <value>', () => {
    expect(filterWriteFrame(2)).toEqual([0x01, 0x11, 0x01, 0x02])
    expect(gainWriteFrame(1)).toEqual([0x01, 0x19, 0x01, 0x01])
    expect(ledWriteFrame(true)).toEqual([0x01, 0x18, 0x01, 0x01])
    expect(ledWriteFrame(false)).toEqual([0x01, 0x18, 0x01, 0x00])
  })

  it('平衡为左右两个包，只衰减被压低的一侧', () => {
    expect(balanceWriteFrames(0)).toEqual([
      [0x01, 0x16, 0x04, 0x00, 0x00, 0x00],
      [0x01, 0x16, 0x04, 0x01, 0x00, 0x00],
    ])

    const [l5, r5] = balanceWriteFrames(5) // 偏右 → 压左声道
    expect(l5.slice(3)).toEqual([0x00, 0x00, 0xfb]) // −5 × 256 = −1280 → 0xFB00
    expect(r5.slice(3)).toEqual([0x01, 0x00, 0x00])

    const [l3, r3] = balanceWriteFrames(-3) // 偏左 → 压右声道
    expect(l3.slice(3)).toEqual([0x00, 0x00, 0x00])
    expect(r3.slice(3)).toEqual([0x01, 0x00, 0xfd]) // −3 × 256 = −768 → 0xFD00
  })

  it('平衡越界值被夹到 ±20', () => {
    const [l] = balanceWriteFrames(99)
    expect(l.slice(3)).toEqual([0x00, 0x00, 0xec]) // −20 × 256 = −5120 → 0xEC00
  })

  it('麦克风/滤波/增益越界值被夹到量程', () => {
    expect(micWriteFrame(99)).toEqual([0x01, 0x02, 0x02, 0x00, 0x1e]) // 30 × 256 = 0x1E00
    expect(micWriteFrame(-99)).toEqual([0x01, 0x02, 0x02, 0x00, 0xe2]) // −30 × 256 → 0xE200
    expect(filterWriteFrame(9)).toEqual([0x01, 0x11, 0x01, 0x04])
    expect(gainWriteFrame(5)).toEqual([0x01, 0x19, 0x01, 0x01])
  })

  it('写帧长度字段等于负载长度', () => {
    expect(writeFrame(CMD.filter, [1])).toEqual([0x01, 0x11, 0x01, 0x01])
  })
})

describe('响应识别', () => {
  it('只认 80 <cmd> 开头的响应', () => {
    expect(isResponseFor(new Uint8Array([0x80, 0x03, 0x02]), CMD.volume)).toBe(true)
    expect(isResponseFor(new Uint8Array([0x80, 0x0c, 0x00]), CMD.volume)).toBe(false)
    expect(isResponseFor(new Uint8Array([0x01, 0x03, 0x02]), CMD.volume)).toBe(false)
    expect(isResponseFor(new Uint8Array([0x80]), CMD.volume)).toBe(false)
  })

  it('小端读取带符号数', () => {
    expect(le16(new Uint8Array([0x00, 0x12]), 0)).toBe(0x1200)
    expect(le16(new Uint8Array([0x00, 0xf4]), 0)).toBe(-3072)
  })
})
