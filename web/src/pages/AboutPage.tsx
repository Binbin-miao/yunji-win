import { COPY } from '../copy'
import type { ConnectedDevice, DeviceState } from '../transport/types'

interface Props {
  device: ConnectedDevice | null
  state: DeviceState | null
  failed: Array<keyof DeviceState>
}

export default function AboutPage({ device, state, failed }: Props) {
  const rows: Array<[string, string]> = [
    ['项目', '云姬网页版调音台（非官方）'],
    ['定位', '免安装，浏览器直连 USB 设备'],
    ['浏览器要求', 'Chrome / Edge 113+ 桌面版（WebHID），手机浏览器不支持'],
    ['协议', '与桌面版共用同一套 HID 协议（0x4B 报告）'],
    ['设备', device ? `${device.name}（${device.kind === 'simulator' ? '模拟器' : '真机'}）` : '未连接'],
    [
      '固件',
      state && !failed.includes('firmware') ? state.firmware : '—',
    ],
    ['桌面版', 'github.com/Binbin-miao/yunji-win'],
  ]

  return (
    <>
      <section className="card">
        <div className="card-head">
          <h2>关于</h2>
          <span className="hint">诊断信息可直接截图反馈</span>
        </div>
        <table className="kv">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <td>{k}</td>
                <td>{v}</td>
              </tr>
            ))}
            <tr>
              <td>UA</td>
              <td className="mono dim">{navigator.userAgent}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>已知限制</h2>
        </div>
        <ul className="limits">
          <li>{COPY.param.led.hint}（写入实测无效，写错命令会让设备进红灯闪烁）</li>
          <li>旋润系列走厂商控制传输，浏览器无法发起，请用桌面版</li>
          <li>左右声道独立 EQ 不支持：硬件是单套 8 段，平衡只是整体衰减</li>
          <li>手机浏览器没有 WebHID，只能看界面不能连设备</li>
        </ul>
      </section>
    </>
  )
}
