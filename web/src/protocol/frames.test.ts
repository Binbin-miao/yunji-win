import { describe, expect, it } from 'vitest'
import {
  CMD,
  PAYLOAD_LEN,
  buildPayload,
  commitFrame,
  isResponseFor,
  le16,
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
