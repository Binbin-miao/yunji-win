/**
 * 设备传输层接口。
 *
 * UI 只认这个接口；真机（WebHID）与模拟器是两个实现，
 * 切换只发生在装配处，页面逻辑不区分。
 */

export type TransportKind = 'webhid' | 'simulator'

export interface ConnectedDevice {
  kind: TransportKind
  name: string
  vendorId: number
  productId: number
  /** 型号表里匹配到的机型；模拟器固定返回凌云剑 */
  model?: import('../data/devices').DeviceModel
}

/** 设备当前状态。数值为设备原始值，显示换算见 domain/params.ts */
export interface DeviceState {
  firmware: string
  /** DAC 原始值；cb5100 为 −60..0，cb1200 为 −8..+4 */
  volume: number
  /** 原始值 −30..30，显示时 +30 */
  mic: number
  /** 滤波器模式编号 */
  filter: number
  /** 增益档位 0/1 */
  gain: number
  led: boolean
  /** 声道平衡 −20..+20 */
  balance: number
}

export interface Transport {
  readonly kind: TransportKind
  connect(): Promise<ConnectedDevice>
  disconnect(): Promise<void>
  readState(): Promise<DeviceState>
  /** 以下写入均返回设备回读确认后的值 */
  setVolume(raw: number): Promise<number>
  setMic(raw: number): Promise<number>
  setFilter(mode: number): Promise<number>
  setGain(level: number): Promise<number>
  setLed(on: boolean): Promise<boolean>
  setBalance(raw: number): Promise<number>
}
