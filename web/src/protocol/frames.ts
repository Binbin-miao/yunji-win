/**
 * 帧构造与解析（纯函数，无浏览器依赖）。
 *
 * 约定见 docs/web-hid-framing.md：
 * - WebHID 的报告 ID 是独立参数，负载里不能出现首字节 0x4B
 * - 负载补零到 63 字节
 * - 响应以 inputreport 到达，data 去掉报告 ID 后即协议帧
 */

export const REPORT_ID = 0x4b
export const PAYLOAD_LEN = 63

/** 写方向标记（读取用 0x80） */
export const DIR_WRITE = 0x01

export const CMD = {
  mic: 0x02,
  volume: 0x03,
  commit: 0x04,
  eqBand: 0x09,
  eqCommit: 0x0a,
  firmware: 0x0c,
  filter: 0x11,
  balance: 0x16,
  led: 0x18,
  gain: 0x19,
} as const

/** 组装一帧发送负载（不含报告 ID），补零到 63 字节 */
export function buildPayload(body: number[], payloadLen = PAYLOAD_LEN): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(payloadLen)
  out.set(body.slice(0, payloadLen))
  return out
}

const i16le = (v: number): [number, number] => [v & 0xff, (v >> 8) & 0xff]

/** 读请求：80 <cmd> [args...] */
export const readFrame = (cmd: number, args: number[] = []): number[] => [0x80, cmd, ...args]

/** 写请求：01 <cmd> <len> <payload...> */
export function writeFrame(cmd: number, payload: number[]): number[] {
  return [DIR_WRITE, cmd, payload.length, ...payload]
}

/** 音量写入帧：01 03 02 <lo> <hi>（值 = level × 256） */
export const volumeWriteFrame = (raw: number): number[] => writeFrame(CMD.volume, i16le(raw * 256))

/** 提交帧：01 04 00 */
export const commitFrame = (): number[] => writeFrame(CMD.commit, [])

/** 判断响应是否属于某个命令（丢弃错位回包） */
export function isResponseFor(data: Uint8Array, cmd: number): boolean {
  return data.length >= 3 && data[0] === 0x80 && data[1] === cmd
}

export const le16 = (b: Uint8Array, i: number): number => {
  const v = b[i] | (b[i + 1] << 8)
  return v & 0x8000 ? v - 0x10000 : v
}
