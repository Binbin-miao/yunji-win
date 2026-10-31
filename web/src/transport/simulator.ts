import type { ConnectedDevice, DeviceState, StateReadResult, Transport } from './types'
import { DEVICE_MODELS } from '../data/devices'

/** 模拟器：不下发任何硬件命令，状态存在内存里 */
export class SimulatorTransport implements Transport {
  readonly kind = 'simulator' as const

  private state: DeviceState = {
    firmware: '0.8',
    volume: -12, // 原始值；cb5100 下显示 48
    mic: 18, // 原始值；显示同为 18
    filter: 1,
    gain: 1,
    led: true,
    balance: 0,
  }

  async connect(): Promise<ConnectedDevice> {
    const model = DEVICE_MODELS.find(m => m.name === '凌云剑')
    return {
      kind: this.kind,
      name: model?.name ?? '模拟设备',
      vendorId: model?.vendorId ?? 0x3302,
      productId: model?.productId ?? 0x43ec,
      model,
    }
  }

  async disconnect(): Promise<void> {
    /* 无状态可清理 */
  }

  async readState(): Promise<StateReadResult> {
    return { state: { ...this.state }, failed: [] }
  }

  async setVolume(raw: number): Promise<number> {
    this.state = { ...this.state, volume: raw }
    return raw
  }

  async setMic(raw: number): Promise<number> {
    this.state = { ...this.state, mic: raw }
    return raw
  }

  async setFilter(mode: number): Promise<number> {
    this.state = { ...this.state, filter: mode }
    return mode
  }

  async setGain(level: number): Promise<number> {
    this.state = { ...this.state, gain: level }
    return level
  }

  async setLed(on: boolean): Promise<boolean> {
    this.state = { ...this.state, led: on }
    return on
  }

  async setBalance(raw: number): Promise<number> {
    this.state = { ...this.state, balance: raw }
    return raw
  }
}
