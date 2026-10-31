import type { ConnectedDevice, DeviceState, Transport } from './types'
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

  async readState(): Promise<DeviceState> {
    return { ...this.state }
  }

  async setVolume(raw: number): Promise<number> {
    this.state = { ...this.state, volume: raw }
    return raw
  }
}
