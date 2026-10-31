/** WebHID 的最小类型声明（TS 的 lib.dom 尚未包含完整定义） */

interface HIDReportItem {
  reportSize: number
  reportCount: number
}

interface HIDReportInfo {
  reportId: number
  items: HIDReportItem[]
}

interface HIDCollectionInfo {
  usagePage: number
  usage: number
  inputReports: HIDReportInfo[]
  outputReports: HIDReportInfo[]
  featureReports: HIDReportInfo[]
}

interface HIDInputReportEvent extends Event {
  readonly reportId: number
  readonly data: DataView
  readonly device: HIDDevice
}

interface HIDDevice extends EventTarget {
  readonly opened: boolean
  readonly vendorId: number
  readonly productId: number
  readonly productName: string
  readonly collections: HIDCollectionInfo[]
  open(): Promise<void>
  close(): Promise<void>
  sendReport(reportId: number, data: BufferSource): Promise<void>
  receiveFeatureReport(reportId: number): Promise<DataView>
  addEventListener(
    type: 'inputreport',
    listener: (this: HIDDevice, ev: HIDInputReportEvent) => void,
    options?: boolean | AddEventListenerOptions,
  ): void
  removeEventListener(
    type: 'inputreport',
    listener: (this: HIDDevice, ev: HIDInputReportEvent) => void,
    options?: boolean | EventListenerOptions,
  ): void
}

interface HIDDeviceFilter {
  vendorId?: number
  productId?: number
  usagePage?: number
  usage?: number
}

interface HIDConnectionEvent extends Event {
  readonly device: HIDDevice
}

interface HID extends EventTarget {
  requestDevice(options: { filters: HIDDeviceFilter[] }): Promise<HIDDevice[]>
  getDevices(): Promise<HIDDevice[]>
  addEventListener(
    type: 'connect' | 'disconnect',
    listener: (ev: HIDConnectionEvent) => void,
    options?: boolean | AddEventListenerOptions,
  ): void
  removeEventListener(
    type: 'connect' | 'disconnect',
    listener: (ev: HIDConnectionEvent) => void,
    options?: boolean | EventListenerOptions,
  ): void
}

interface Navigator {
  readonly hid?: HID
}
