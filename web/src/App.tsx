import { useCallback, useEffect, useRef, useState } from 'react'
import { COPY } from './copy'
import { DEVICE_MODELS } from './data/devices'
import { createDebouncer, type Debouncer } from './domain/commit'
import { balDisplay, micDisplay, volBounds, volDisplay, volRaw } from './domain/params'
import { SimulatorTransport } from './transport/simulator'
import { WebHidTransport } from './transport/webhid'
import { STAGE_TEXT, TransportError } from './transport/errors'
import type { ConnectedDevice, DeviceState, Transport } from './transport/types'

const isMobile = /Android|iPhone|iPad|iPod|Mobile/i.test(
  typeof navigator === 'undefined' ? '' : navigator.userAgent,
)

type WriteStatus = { kind: 'idle' | 'writing' | 'done' | 'error'; text?: string }

export default function App() {
  const [hidReady, setHidReady] = useState(false)
  const [device, setDevice] = useState<ConnectedDevice | null>(null)
  const [state, setState] = useState<DeviceState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [reading, setReading] = useState(false)
  const [transport, setTransport] = useState<Transport | null>(null)
  const [draftVol, setDraftVol] = useState<number | null>(null)
  const [writeStatus, setWriteStatus] = useState<WriteStatus>({ kind: 'idle' })
  const debouncer = useRef<Debouncer<number> | null>(null)
  /** 每次连接/断开自增，用来丢弃上一session 的异步回调 */
  const sessionRef = useRef(0)

  useEffect(() => {
    setHidReady(WebHidTransport.supported())
  }, [])

  // 拔线后清空界面，避免显示「已连接」但所有操作都失败
  useEffect(() => {
    const hid = navigator.hid
    if (!hid || !device) return
    const onGone = (ev: HIDConnectionEvent) => {
      if (ev.device.vendorId !== device.vendorId || ev.device.productId !== device.productId) return
      debouncer.current?.cancel()
      setError(COPY.deviceGone)
      setTransport(null)
      setDevice(null)
      setState(null)
      setDraftVol(null)
      setWriteStatus({ kind: 'idle' })
    }
    hid.addEventListener('disconnect', onGone)
    return () => hid.removeEventListener('disconnect', onGone)
  }, [device])

  const load = useCallback(async (t: Transport) => {
    setReading(true)
    setError(null)
    try {
      setState(await t.readState())
      setDraftVol(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setReading(false)
    }
  }, [])

  const attach = useCallback(
    (t: Transport, chip: 'cb5100' | 'cb1200', session: number) => {
      debouncer.current?.cancel()
      debouncer.current = createDebouncer<number>(async raw => {
        if (session !== sessionRef.current) return
        setWriteStatus({ kind: 'writing' })
        try {
          const back = await t.setVolume(raw)
          if (session !== sessionRef.current) return
          setState(s => (s ? { ...s, volume: back } : s))
          // 只清掉与写入值一致的草稿；用户已拖到别处时保留他的新位置
          const written = volDisplay(back, chip)
          setDraftVol(d => (d === written ? null : d))
          setWriteStatus({ kind: 'done', text: `已写入 ${written}` })
        } catch (e) {
          if (session !== sessionRef.current) return
          const msg =
            e instanceof TransportError
              ? `${STAGE_TEXT[e.stage]}：${e.message}`
              : e instanceof Error
                ? e.message
                : String(e)
          setWriteStatus({ kind: 'error', text: msg })
          try {
            const fresh = await t.readState()
            if (session !== sessionRef.current) return
            setState(fresh)
          } catch {
            /* 回读也失败时保持原样，错误提示已给出 */
          }
          setDraftVol(null)
        }
      }, 400)
    },
    [],
  )

  const run = useCallback(
    async (next: Transport) => {
      setBusy(true)
      setError(null)
      try {
        const connected = await next.connect()
        sessionRef.current += 1
        setTransport(next)
        setDevice(connected)
        setWriteStatus({ kind: 'idle' })
        attach(next, connected.model?.chip ?? 'cb5100', sessionRef.current)
        await load(next)
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setBusy(false)
      }
    },
    [attach, load],
  )

  // 开发/演示用：地址带 ?sim=1 直接进模拟器，方便截图与回归
  const autoSim = useRef(false)
  useEffect(() => {
    if (autoSim.current) return
    if (new URLSearchParams(window.location.search).get('sim') !== '1') return
    autoSim.current = true
    void run(new SimulatorTransport())
  }, [run])

  async function disconnect() {
    setBusy(true)
    sessionRef.current += 1
    try {
      debouncer.current?.cancel()
      await transport?.disconnect()
    } finally {
      setTransport(null)
      setDevice(null)
      setState(null)
      setDraftVol(null)
      setWriteStatus({ kind: 'idle' })
      setBusy(false)
    }
  }

  const statusText = device ? (device.kind === 'simulator' ? '模拟器' : '已连接') : '未连接'
  const chip = device?.model?.chip ?? 'cb5100'
  const bounds = volBounds(chip)
  const shownVol = draftVol ?? (state ? volDisplay(state.volume, chip) : bounds.max)

  function onSlide(v: number) {
    setDraftVol(v)
    if (writeStatus.kind !== 'idle') setWriteStatus({ kind: 'idle' })
  }

  function commitVolume() {
    if (!state) return
    const display = draftVol ?? volDisplay(state.volume, chip)
    debouncer.current?.schedule(volRaw(display, chip))
  }

  const params: Array<{ key: keyof DeviceState; value: string }> = state
    ? [
        { key: 'firmware', value: state.firmware },
        { key: 'mic', value: micDisplay(state.mic) },
        { key: 'filter', value: COPY.filterModes[state.filter] ?? `模式 ${state.filter}` },
        { key: 'gain', value: COPY.gainLevels[state.gain] ?? `档位 ${state.gain}` },
        { key: 'led', value: state.led ? '开' : '关' },
        { key: 'balance', value: balDisplay(state.balance) },
      ]
    : []

  return (
    <div className="shell">
      <aside className="rail">
        <svg className="logo" viewBox="0 0 40 40" aria-hidden="true">
          <path
            d="M20 12c3-5 9-8 14-7-1 5-4 10-9 12 3 1 6 3 7 6-4 1-8 0-11-2 1 4 0 8-2 11-2-3-3-7-2-11-3 2-7 3-11 2 1-3 4-5 7-6-5-2-8-7-9-12 5-1 11 2 14 7z"
            fill="rgba(201,166,255,.18)"
            stroke="#C9A6FF"
            strokeWidth="1.2"
          />
          <circle cx="20" cy="19" r="2.2" fill="#C9A6FF" />
        </svg>
        <nav>
          <span className="rail-item on" title="设备">◈</span>
          <span className="rail-item" title="调音">∿</span>
          <span className="rail-item" title="预设">⌸</span>
        </nav>
      </aside>

      <main className="main">
        <header className="header">
          <div className="brand">
            <strong>{COPY.appName}</strong>
            <span>{COPY.tagline}</span>
          </div>
          <div className={`pill ${device ? 'pill-on' : ''}`}>
            <i />
            {statusText}
          </div>
          <div className="spacer" />
          {device ? (
            <>
              <button className="btn ghost" onClick={() => transport && load(transport)} disabled={busy || reading}>
                {reading ? COPY.reading : COPY.reread}
              </button>
              <button className="btn ghost" onClick={disconnect} disabled={busy}>
                {COPY.disconnect}
              </button>
            </>
          ) : (
            <>
              <button
                className="btn"
                onClick={() => run(new WebHidTransport())}
                disabled={busy || !hidReady}
                title={COPY.hintReal}
              >
                {COPY.connectReal}
              </button>
              <button
                className="btn ghost"
                onClick={() => run(new SimulatorTransport())}
                disabled={busy}
                title={COPY.hintSim}
              >
                {COPY.connectSim}
              </button>
            </>
          )}
        </header>

        {!hidReady && <div className="banner">{isMobile ? COPY.mobile : COPY.noHid}</div>}
        {device?.kind === 'simulator' && <div className="banner sim">{COPY.simBanner}</div>}
        {error && <div className="banner error">{error}</div>}

        {device && (
          <section className="card">
            <div className="card-head">
              <h2>{device.name}</h2>
              <span className="mono">
                {device.vendorId.toString(16).padStart(4, '0')}:
                {device.productId.toString(16).padStart(4, '0')}
              </span>
              <span className="badge">{device.kind === 'simulator' ? '模拟器' : '真机'}</span>
              <span className="hint">
                {device.model ? `${device.model.vendor} · ${device.model.name}` : '未知品牌'}
              </span>
            </div>
          </section>
        )}

        {device && state && (
          <section className="card">
            <div className="card-head">
              <h2>{COPY.param.volume.label}</h2>
              <span className="mono">
                {shownVol} / {bounds.max}
              </span>
              <span className={`write ${writeStatus.kind}`}>
                {writeStatus.kind === 'writing' && '写入中…'}
                {writeStatus.kind === 'done' && (writeStatus.text ?? '已写入')}
                {writeStatus.kind === 'error' && (writeStatus.text ?? '写入失败')}
              </span>
            </div>
            <input
              className="slider"
              type="range"
              min={bounds.min}
              max={bounds.max}
              step={1}
              value={shownVol}
              disabled={writeStatus.kind === 'writing'}
              onChange={e => onSlide(Number(e.target.value))}
              onPointerUp={commitVolume}
              onKeyUp={commitVolume}
              aria-label={COPY.param.volume.label}
            />
            <p className="hint">{COPY.param.volume.hint} · 松手后约 0.4 秒写入设备</p>
          </section>
        )}

        {device && (
          <section className="card">
            <div className="card-head">
              <h2>{COPY.sectionState}</h2>
              <span className="hint">{COPY.sectionStateHint}</span>
            </div>
            {reading && !state ? (
              <p className="hint">{COPY.reading}</p>
            ) : (
              <div className="params">
                {params.map(p => (
                  <div className="param" key={p.key}>
                    <span className="param-label">{COPY.param[p.key].label}</span>
                    <strong className="param-value">{p.value}</strong>
                    <span className="param-hint">{COPY.param[p.key].hint}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        <section className="card">
          <div className="card-head">
            <h2>{COPY.sectionModels}</h2>
            <span className="hint">{COPY.sectionModelsHint}</span>
          </div>
          <div className="models">
            {DEVICE_MODELS.map(m => (
              <div
                key={`${m.vendorId}-${m.productId}`}
                className={`model ${m.webSupported ? '' : 'model-off'}`}
              >
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
      </main>
    </div>
  )
}
