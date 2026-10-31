import type { ConnectedDevice, DeviceState, StateReadResult, Transport } from './types'
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
  ledValueFrame,
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
  /** 灯光「开」命中的编码值，探测成功后本会话复用 */
  private ledOnValue: number | null = null
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
  private async sendAndWait(
    cmd: number,
    args: number[] = [],
    attempts = MAX_RETRY,
  ): Promise<Uint8Array> {
    const device = this.requireDevice()
    const payload = buildPayload(readFrame(cmd, args), PAYLOAD_LEN)

    for (let attempt = 0; attempt <= attempts; attempt++) {
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
    // 个别固件对被手机 App 改动过的灯效不回 [arg] 形式，退一步不带 arg 再试
    let resp: Uint8Array
    try {
      resp = await this.sendAndWait(CMD.led, [1], 0)
    } catch {
      resp = await this.sendAndWait(CMD.led, [], 0)
    }
    return (resp[3] ?? 0) !== 0
  }

  private async readBalance(): Promise<number> {
    const l = await this.sendAndWait(CMD.balance, [4, 0])
    const r = await this.sendAndWait(CMD.balance, [4, 1])
    return Math.round(le16(r, 4) / 256) - Math.round(le16(l, 4) / 256)
  }

  readState(): Promise<StateReadResult> {
    return this.enqueue(async () => {
      const failed: Array<keyof DeviceState> = []
      const safe = async <T>(key: keyof DeviceState, fallback: T, run: () => Promise<T>): Promise<T> => {
        try {
          return await run()
        } catch {
          failed.push(key)
          return fallback
        }
      }

      const firmware = await safe('firmware', '(读取失败)', () => this.readFirmware())
      const volume = await safe('volume', 0, () => this.readVolume())
      const mic = await safe('mic', 0, () => this.readMic())
      const filter = await safe('filter', 0, () => this.readFilter())
      const gain = await safe('gain', 0, () => this.readGain())
      const led = await safe('led', false, () => this.readLed())
      const balance = await safe('balance', 0, () => this.readBalance())

      return { state: { firmware, volume, mic, filter, gain, led, balance }, failed }
    })
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
      // 与桌面版一致：只发 01 18 01 <value>，不补提交
      // 手机 App 能调但桌面版偶尔调不动，说明「开」的编码并非固定为 1，
      // 这里按 1 → 2 依次探测，命中后记住本次会话用哪个值。
      if (!on) {
        await this.sendRaw(ledValueFrame(0))
        const back = await this.readUntil(async () => ((await this.readLed()) ? 1 : 0), 0)
        return back !== 0
      }

      const candidates = this.ledOnValue !== null ? [this.ledOnValue] : [1, 2]
      for (const value of candidates) {
        await this.sendRaw(ledValueFrame(value))
        const back = await this.readUntil(async () => ((await this.readLed()) ? 1 : 0), 1)
        if (back !== 0) {
          this.ledOnValue = value
          return true
        }
      }
      return false
    })
  }

  setBalance(raw: number): Promise<number> {
    return this.enqueue(async () => {
      for (const frame of balanceWriteFrames(raw)) await this.sendRaw(frame)
      return this.readUntil(() => this.readBalance(), raw)
    })
  }
}
