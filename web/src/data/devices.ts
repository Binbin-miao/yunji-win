/** 设备型号表：与桌面版 product-list.json 保持一致 */

export type ChipType = 'cb5100' | 'cb1200'

export interface DeviceModel {
  vendorId: number
  productId: number
  vendor: string
  name: string
  /** DAC 芯片，决定音量等参数的取值量程 */
  chip: ChipType
  /** 浏览器通道是否可用。旋润走厂商控制传输，WebHID 无法发起 */
  webSupported: boolean
  note?: string
}

export const DEVICE_MODELS: DeviceModel[] = [
  { vendorId: 0x2fc6, productId: 0xf0fb, vendor: '旋润', name: 'You Got Me', chip: 'cb5100', webSupported: false, note: '厂商控制传输' },
  { vendorId: 0x2fc6, productId: 0xf0fc, vendor: '旋润', name: 'YUNJI43198PRO', chip: 'cb5100', webSupported: false, note: '厂商控制传输' },
  { vendorId: 0x2fc6, productId: 0xf0fd, vendor: '旋润', name: 'YUNJI43198ULTRA', chip: 'cb5100', webSupported: false, note: '厂商控制传输' },
  { vendorId: 0x3302, productId: 0x43e1, vendor: 'TTGK', name: '测试双43', chip: 'cb5100', webSupported: true },
  { vendorId: 0x3302, productId: 0x43ec, vendor: 'TTGK', name: '凌云剑', chip: 'cb5100', webSupported: true },
  { vendorId: 0x3302, productId: 0x4311, vendor: 'TTGK', name: '青云剑', chip: 'cb5100', webSupported: true },
  { vendorId: 0x3302, productId: 0x124f, vendor: 'TTGK', name: 'Q25', chip: 'cb1200', webSupported: true },
  { vendorId: 0x3302, productId: 0x1246, vendor: 'TTGK', name: '云中剑', chip: 'cb1200', webSupported: true },
]

export const findModel = (vendorId: number, productId: number): DeviceModel | undefined =>
  DEVICE_MODELS.find(m => m.vendorId === vendorId && m.productId === productId)
