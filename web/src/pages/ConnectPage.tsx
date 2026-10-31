import { COPY } from '../copy'
import { DEVICE_MODELS } from '../data/devices'
import type { ConnectedDevice, DeviceState } from '../transport/types'

interface Props {
  device: ConnectedDevice | null
  state: DeviceState | null
  failed: Array<keyof DeviceState>
  hidReady: boolean
  isMobile: boolean
  busy: boolean
  reading: boolean
  error: string | null
  onConnectReal: () => void
  onConnectSim: () => void
  onReload: () => void
  onDisconnect: () => void
}

export default function ConnectPage({
  device,
  state,
  failed,
  hidReady,
  isMobile,
  busy,
  reading,
  error,
  onConnectReal,
  onConnectSim,
  onReload,
  onDisconnect,
}: Props) {
  return (
    <>
      {!hidReady && <div className="banner">{isMobile ? COPY.mobile : COPY.noHid}</div>}
      {error && <div className="banner error">{error}</div>}
      {failed.length > 0 && (
        <div className="banner">
          以下参数读取失败：{failed.map(k => COPY.param[k].label).join('、')}
          。其余参数可正常使用，可点「重新读取」重试，或拔插设备后再连。
        </div>
      )}

      <section className="card">
        <div className="card-head">
          <h2>连接</h2>
          <span className="hint">
            {device ? '已连接，可切换到「调音」开始调整' : '插上设备后点「连接真机」，浏览器会弹窗请求授权'}
          </span>
        </div>
        {device ? (
          <div className="dev-row">
            <div>
              <strong className="dev-name">{device.name}</strong>
              <span className="mono dim">
                {' '}
                {device.vendorId.toString(16).padStart(4, '0')}:
                {device.productId.toString(16).padStart(4, '0')}
              </span>
            </div>
            <span className="badge">{device.kind === 'simulator' ? '模拟器' : '真机'}</span>
            <span className="hint">
              {device.model ? `${device.model.vendor} · ${device.model.name}` : '未知品牌'}
              {state ? ` · 固件 ${failed.includes('firmware') ? '—' : state.firmware}` : ''}
            </span>
            <div className="spacer" />
            <button className="btn ghost" onClick={onReload} disabled={busy || reading}>
              {reading ? COPY.reading : COPY.reread}
            </button>
            <button className="btn ghost" onClick={onDisconnect} disabled={busy}>
              {COPY.disconnect}
            </button>
          </div>
        ) : (
          <div className="row">
            <button className="btn" onClick={onConnectReal} disabled={busy || !hidReady} title={COPY.hintReal}>
              {COPY.connectReal}
            </button>
            <button className="btn ghost" onClick={onConnectSim} disabled={busy} title={COPY.hintSim}>
              {COPY.connectSim}
            </button>
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-head">
          <h2>{COPY.sectionModels}</h2>
          <span className="hint">{COPY.sectionModelsHint}</span>
        </div>
        <div className="models">
          {DEVICE_MODELS.map(m => (
            <div key={`${m.vendorId}-${m.productId}`} className={`model ${m.webSupported ? '' : 'model-off'}`}>
              <div className="model-top">
                <strong>{m.name}</strong>
                <span className={`tag ${m.webSupported ? 'tag-on' : 'tag-off'}`}>
                  {m.webSupported ? COPY.supported : COPY.unsupported}
                </span>
              </div>
              <span className="mono dim">
                {m.vendor} · {m.vendorId.toString(16).padStart(4, '0')}:
                {m.productId.toString(16).padStart(4, '0')}
              </span>
            </div>
          ))}
        </div>
      </section>
    </>
  )
}
