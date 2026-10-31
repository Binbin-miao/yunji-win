import type { ConnectedDevice, DeviceState, Transport } from './types'
import { DEVICE_MODELS, findModel } from '../data/devices'
import {
  CMD,
  PAYLOAD_LEN,
  REPORT_ID,
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

  /** 写值 → 10ms → 提交（只有需要提交的参数走这条） */
  private async writeWithCommit(frame: number[]): Promise<void> {
    await this.sendRaw(frame)
    await sleep(WRITE_GAP)
    await this.sendRaw(commitFrame())
  }

  /**
   * 回读校验：设备写入后有量化与延迟，单次读可能拿到陈旧值。
   * 最多读 3 次（间隔 40ms），返回最后一次读到的值，由调用方决定是否提示。
   */
  private async readUntil(getter: () => Promise<number>, expected: number): Promise<number> {
    let last = await getter()
    for (let i = 0; i < 2 && last !== expected; i++) {
      await sleep(40)
      last = await getter()
    }
    return last
  }

  // ---- 单项读取（内部使用，调用方需在队列内） ----
  private async readFirmware(): Promise<string> {
    const resp = await this.sendAndWait(CMD.firmware)
    let out = ''
    for (let i = 3; i < resp.length; i++) {
      const b = resp[i]
      if (b === 0 || !(b === 0x2e || (b >= 0x30 && b <= 0x39))) break
      out += String.fromCharCode(b)
    }
    return out || '(空)'
  }

  private async readVolume(): Promise<number> {
    return Math.round(le16(await this.sendAndWait(CMD.volume), 3) / 256)
  }

  private async readMic(): Promise<number> {
    return Math.round(le16(await this.sendAndWait(CMD.mic), 3) / 256)
  }

  private async readFilter(): Promise<number> {
    return (await this.sendAndWait(CMD.filter))[3] ?? 0
  }

  private async readGain(): Promise<number> {
    return (await this.sendAndWait(CMD.gain))[3] ?? 0
  }

  private async readLed(): Promise<boolean> {
    return ((await this.sendAndWait(CMD.led, [1]))[3] ?? 0) !== 0
  }

  private async readBalance(): Promise<number> {
    const l = await this.sendAndWait(CMD.balance, [4, 0])
    const r = await this.sendAndWait(CMD.balance, [4, 1])
    return Math.round(le16(r, 4) / 256) - Math.round(le16(l, 4) / 256)
  }

  readState(): Promise<DeviceState> {
    return this.enqueue(async () => ({
      firmware: await this.readFirmware(),
      volume: await this.readVolume(),
      mic: await this.readMic(),
      filter: await this.readFilter(),
      gain: await this.readGain(),
      led: await this.readLed(),
      balance: await this.readBalance(),
    }))
  }

  // ---- 写入（返回设备实际值，不一致由界面提示，不当作失败） ----
  setVolume(raw: number): Promise<number> {
    return this.enqueue(async () => {
      await this.writeWithCommit(volumeWriteFrame(raw))
      return this.readUntil(() => this.readVolume(), raw)
    })
  }

  setMic(raw: number): Promise<number> {
    return this.enqueue(async () => {
      await this.writeWithCommit(micWriteFrame(raw))
      return this.readUntil(() => this.readMic(), raw)
    })
  }

  setFilter(mode: number): Promise<number> {
    return this.enqueue(async () => {
      await this.sendRaw(filterWriteFrame(mode))
      return this.readUntil(() => this.readFilter(), mode)
    })
  }

  setGain(level: number): Promise<number> {
    return this.enqueue(async () => {
      await this.sendRaw(gainWriteFrame(level))
      return this.readUntil(() => this.readGain(), level)
    })
  }

  setLed(on: boolean): Promise<boolean> {
    return this.enqueue(async () => {
      // 桌面版此处不提交，但实测只发 01 18 01 01 时设备可能不落盘，补一条提交
      await this.writeWithCommit(ledWriteFrame(on))
      const back = await this.readUntil(async () => ((await this.readLed()) ? 1 : 0), on ? 1 : 0)
      return back !== 0
    })
  }

  setBalance(raw: number): Promise<number> {
    return this.enqueue(async () => {
      for (const frame of balanceWriteFrames(raw)) await this.sendRaw(frame)
      return this.readUntil(() => this.readBalance(), raw)
    })
  }
}
