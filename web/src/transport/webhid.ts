import type { ConnectedDevice, DeviceState, Transport } from './types'
import { DEVICE_MODELS, findModel } from '../data/devices'
import {
  CMD,
  PAYLOAD_LEN,
  REPORT_ID,
  buildPayload,
  commitFrame,
  isResponseFor,
  le16,
  readFrame,
  volumeWriteFrame,
} from '../protocol/frames'
import { TransportError } from './errors'

/**
 * 真机：WebHID 直连。
 *
 * 串行化：同一时刻只允许一条 USB 事务在飞（会话级队列）。
 * 帧构造与偏移见 docs/web-hid-framing.md。
 */

const IO_TIMEOUT = 900
const MAX_RETRY = 2
/** 与桌面版 set_vol 的 10ms 间隔一致 */
const WRITE_GAP = 10

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

export class WebHidTransport implements Transport {
  readonly kind = 'webhid' as const

  private device: HIDDevice | null = null
  private inbox: Uint8Array[] = []
  private queue: Promise<unknown> = Promise.resolve()
  private readonly onReport = (ev: HIDInputReportEvent) => {
    this.inbox.push(new Uint8Array(ev.data.buffer, ev.data.byteOffset, ev.data.byteLength))
  }

  static supported(): boolean {
    return typeof navigator !== 'undefined' && !!navigator.hid
  }

  async connect(): Promise<ConnectedDevice> {
    if (!WebHidTransport.supported()) {
      throw new TransportError('当前浏览器不支持 WebHID，请改用 Chrome 或 Edge 113+ 桌面版', 'connect')
    }
    const picked = await navigator.hid!.requestDevice({
      filters: DEVICE_MODELS.map(m => ({ vendorId: m.vendorId, productId: m.productId })),
    })
    if (!picked.length) throw new TransportError('没有选择设备', 'connect')

    const device = picked[0]
    if (!device.opened) await device.open()
    device.addEventListener('inputreport', this.onReport)
    this.device = device

    return {
      kind: this.kind,
      name: device.productName || '未知设备',
      vendorId: device.vendorId,
      productId: device.productId,
      model: findModel(device.vendorId, device.productId),
    }
  }

  async disconnect(): Promise<void> {
    try {
      this.device?.removeEventListener('inputreport', this.onReport)
      if (this.device?.opened) await this.device.close()
    } finally {
      this.device = null
      this.inbox = []
    }
  }

  private enqueue<T>(job: () => Promise<T>): Promise<T> {
    const next = this.queue.then(job, job)
    this.queue = next.catch(() => undefined)
    return next
  }

  private requireDevice(): HIDDevice {
    if (!this.device?.opened) throw new TransportError('设备未打开或已断开', 'connect')
    return this.device
  }

  /** 发一帧，不等待回复 */
  private async sendRaw(body: number[]): Promise<void> {
    const device = this.requireDevice()
    try {
      await device.sendReport(REPORT_ID, buildPayload(body, PAYLOAD_LEN))
    } catch (e) {
      throw new TransportError(`写入失败: ${e instanceof Error ? e.message : String(e)}`, 'write')
    }
  }

  /** 发一帧并等待 CMD 匹配的响应；不匹配的丢弃（可能是上一条的延迟回包） */
  private async sendAndWait(cmd: number, args: number[] = []): Promise<Uint8Array> {
    const device = this.requireDevice()
    const payload = buildPayload(readFrame(cmd, args), PAYLOAD_LEN)

    for (let attempt = 0; attempt <= MAX_RETRY; attempt++) {
      this.inbox = []
      try {
        await device.sendReport(REPORT_ID, payload)
      } catch (e) {
        throw new TransportError(`写入失败: ${e instanceof Error ? e.message : String(e)}`, 'write')
      }

      const deadline = performance.now() + IO_TIMEOUT
      while (performance.now() < deadline) {
        const hit = this.inbox.find(d => isResponseFor(d, cmd))
        if (hit) return hit
        await sleep(16)
      }
    }
    throw new TransportError(`命令 0x${cmd.toString(16)} 无响应`, 'read')
  }

  private async readVolumeRaw(): Promise<number> {
    const resp = await this.sendAndWait(CMD.volume)
    return Math.round(le16(resp, 3) / 256)
  }

  /** 写入音量并回读校验，返回设备实际值 */
  setVolume(raw: number): Promise<number> {
    return this.enqueue(async () => {
      await this.sendRaw(volumeWriteFrame(raw))
      await sleep(WRITE_GAP)
      await this.sendRaw(commitFrame())

      const back = await this.readVolumeRaw()
      if (back !== raw) {
        throw new TransportError(`设备回读为 ${back}，与写入值 ${raw} 不一致`, 'verify')
      }
      return back
    })
  }

  readState(): Promise<DeviceState> {
    return this.enqueue(async () => {
      const firmwareResp = await this.sendAndWait(CMD.firmware)
      let firmware = ''
      for (let i = 3; i < firmwareResp.length; i++) {
        const b = firmwareResp[i]
        if (b === 0 || !(b === 0x2e || (b >= 0x30 && b <= 0x39))) break
        firmware += String.fromCharCode(b)
      }

      const volume = await this.readVolumeRaw()
      const micResp = await this.sendAndWait(CMD.mic)
      const filterResp = await this.sendAndWait(CMD.filter)
      const gainResp = await this.sendAndWait(CMD.gain)
      const ledResp = await this.sendAndWait(CMD.led, [1])
      const balL = await this.sendAndWait(CMD.balance, [4, 0])
      const balR = await this.sendAndWait(CMD.balance, [4, 1])

      return {
        firmware: firmware || '(空)',
        volume,
        // 偏移 = 桌面版 resp 索引 − 1（桌面版的 resp[0] 是报告 ID）
        mic: Math.round(le16(micResp, 3) / 256),
        filter: filterResp[3] ?? 0,
        gain: gainResp[3] ?? 0,
        led: (ledResp[3] ?? 0) !== 0,
        balance: Math.round(le16(balR, 4) / 256) - Math.round(le16(balL, 4) / 256),
      }
    })
  }
}
