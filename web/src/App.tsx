import { useCallback, useEffect, useRef, useState } from 'react'
import { COPY } from './copy'
import { DEVICE_MODELS } from './data/devices'
import { createDebouncer, type Debouncer } from './domain/commit'
import { balDisplay, micDisplay, volBounds, volDisplay, volRaw } from './domain/params'
import { DB_RANGES, DEFAULT_BANDS, DEMO_BANDS, type EqBand } from './domain/eq'
import EqChart from './components/EqChart'
import { SimulatorTransport } from './transport/simulator'
import { WebHidTransport } from './transport/webhid'
import { STAGE_TEXT, TransportError } from './transport/errors'
import type { ConnectedDevice, DeviceState, Transport } from './transport/types'

const isMobile = /Android|iPhone|iPad|iPod|Mobile/i.test(
  typeof navigator === 'undefined' ? '' : navigator.userAgent,
)

type WriteStatus = { kind: 'idle' | 'writing' | 'done' | 'warn' | 'error'; text?: string }
type SliderKey = 'volume' | 'mic' | 'balance'
type ParamKey = SliderKey | 'filter' | 'gain' | 'led'

const SLIDERS: Record<SliderKey, { min: number; max: number }> = {
  volume: { min: 0, max: 60 }, // 运行时按芯片覆盖
  mic: { min: -30, max: 30 },
  balance: { min: -20, max: 20 },
}

export default function App() {
  const [hidReady, setHidReady] = useState(false)
  const [device, setDevice] = useState<ConnectedDevice | null>(null)
  const [state, setState] = useState<DeviceState | null>(null)
  const [failed, setFailed] = useState<Array<keyof DeviceState>>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [reading, setReading] = useState(false)
  const [transport, setTransport] = useState<Transport | null>(null)
  const [drafts, setDrafts] = useState<Partial<Record<SliderKey, number>>>({})
  const [texts, setTexts] = useState<Partial<Record<SliderKey, string>>>({})
  const [status, setStatus] = useState<Partial<Record<ParamKey, WriteStatus>>>({})
  const [bands, setBands] = useState<EqBand[]>(DEFAULT_BANDS)
  const [dbRange, setDbRange] = useState<(typeof DB_RANGES)[number]>(12)

  const debouncers = useRef<Partial<Record<SliderKey, Debouncer<number>>>>({})
  /** 每次连接/断开自增，用来丢弃上一 session 的异步回调 */
  const sessionRef = useRef(0)
  const applyRef = useRef<(key: ParamKey, value: number) => void>(() => undefined)
  const transportRef = useRef<Transport | null>(null)

  useEffect(() => {
    setHidReady(WebHidTransport.supported())
  }, [])

  // 拔线后清空界面，避免显示「已连接」但所有操作都失败
  useEffect(() => {
    const hid = navigator.hid
    if (!hid || !device) return
    const onGone = (ev: HIDConnectionEvent) => {
      if (ev.device.vendorId !== device.vendorId || ev.device.productId !== device.productId) return
      sessionRef.current += 1
      setError(COPY.deviceGone)
      setTransport(null)
      setDevice(null)
      setState(null)
      setDrafts({})
      setStatus({})
    }
    hid.addEventListener('disconnect', onGone)
    return () => hid.removeEventListener('disconnect', onGone)
  }, [device])

  const chip = device?.model?.chip ?? 'cb5100'

  const load = useCallback(async (t: Transport) => {
    setReading(true)
    setError(null)
    try {
      const res = await t.readState()
      setState(res.state)
      setFailed(res.failed)
      setDrafts({})
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setReading(false)
    }
  }, [])

  /** 把一次参数写入落到设备，并回填结果 */
  const apply = useCallback(async (key: ParamKey, value: number) => {
    const t = transportRef.current
    if (!t) return
    const session = sessionRef.current
    setStatus(s => ({ ...s, [key]: { kind: 'writing' } }))

    const finish = (sent: number, back: number, describe: (v: number) => string) => {
      if (session !== sessionRef.current) return
      if (back === sent) {
        setStatus(s => ({ ...s, [key]: { kind: 'done', text: `已写入 ${describe(back)}` } }))
      } else {
        // 设备有量化或延迟，回读与写入值不同不算失败，但要如实告知
        setStatus(s => ({
          ...s,
          [key]: { kind: 'warn', text: `已写入 ${describe(sent)}，设备回读 ${describe(back)}` },
        }))
      }
      setDrafts(d => {
        const next = { ...d }
        if (key === 'volume' || key === 'mic' || key === 'balance') delete next[key]
        return next
      })
    }

    try {
      if (key === 'volume') {
        const back = await t.setVolume(value)
        if (session !== sessionRef.current) return
        setState(s => (s ? { ...s, volume: back } : s))
        finish(value, back, v => String(volDisplay(v, chip)))
      } else if (key === 'mic') {
        const back = await t.setMic(value)
        if (session !== sessionRef.current) return
        setState(s => (s ? { ...s, mic: back } : s))
        finish(value, back, v => micDisplay(v))
      } else if (key === 'balance') {
        const back = await t.setBalance(value)
        if (session !== sessionRef.current) return
        setState(s => (s ? { ...s, balance: back } : s))
        finish(value, back, v => balDisplay(v))
      } else if (key === 'filter') {
        const back = await t.setFilter(value)
        if (session !== sessionRef.current) return
        setState(s => (s ? { ...s, filter: back } : s))
        finish(value, back, v => COPY.filterModes[v] ?? String(v))
      } else if (key === 'gain') {
        const back = await t.setGain(value)
        if (session !== sessionRef.current) return
        setState(s => (s ? { ...s, gain: back } : s))
        finish(value, back, v => COPY.gainLevels[v] ?? String(v))
      } else {
        const back = await t.setLed(value !== 0)
        if (session !== sessionRef.current) return
        setState(s => (s ? { ...s, led: back } : s))
        finish(value !== 0 ? 1 : 0, back ? 1 : 0, v => (v ? '开' : '关'))
      }
    } catch (e) {
      if (session !== sessionRef.current) return
      const msg =
        e instanceof TransportError
          ? `${STAGE_TEXT[e.stage]}：${e.message}`
          : e instanceof Error
            ? e.message
            : String(e)
      setStatus(s => ({ ...s, [key]: { kind: 'error', text: msg } }))
      setDrafts(d => {
        const next = { ...d }
        if (key === 'volume' || key === 'mic' || key === 'balance') delete next[key]
        return next
      })
      try {
        const res = await t.readState()
        if (session === sessionRef.current) {
          setState(res.state)
          setFailed(res.failed)
        }
      } catch {
        /* 回读也失败时保持原样，错误提示已给出 */
      }
    }
  }, [chip])

  useEffect(() => {
    transportRef.current = transport
    applyRef.current = (key, value) => void apply(key, value)
  }, [transport, apply])

  const attach = useCallback(() => {
    for (const key of ['volume', 'mic', 'balance'] as const) {
      debouncers.current[key]?.cancel()
      debouncers.current[key] = createDebouncer<number>(v => {
        applyRef.current(key, v)
        return Promise.resolve()
      }, 400)
    }
  }, [])

  const run = useCallback(
    async (next: Transport) => {
      setBusy(true)
      setError(null)
      try {
        const connected = await next.connect()
        sessionRef.current += 1
        setTransport(next)
        setDevice(connected)
        setStatus({})
        setDrafts({})
        // 模拟器给一条示例曲线；真机暂时用平直曲线（设备内 EQ 读取在 09 号实现）
        setBands(connected.kind === 'simulator' ? DEMO_BANDS : DEFAULT_BANDS)
        attach()
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
    for (const key of ['volume', 'mic', 'balance'] as const) debouncers.current[key]?.cancel()
    try {
      await transportRef.current?.disconnect()
    } finally {
      setTransport(null)
      setDevice(null)
      setState(null)
      setDrafts({})
      setStatus({})
      setBusy(false)
    }
  }

  const statusText = device ? (device.kind === 'simulator' ? '模拟器' : '已连接') : '未连接'
  const volRange = volBounds(chip)

  function shown(key: SliderKey): number {
    if (drafts[key] !== undefined) return drafts[key]!
    if (!state) return key === 'volume' ? volRange.max : 0
    if (key === 'volume') return volDisplay(state.volume, chip)
    if (key === 'mic') return state.mic
    return state.balance
  }

  function slide(key: SliderKey, v: number) {
    setDrafts(d => ({ ...d, [key]: v }))
    setStatus(s => ({ ...s, [key]: { kind: 'idle' } }))
  }

  function commit(key: SliderKey) {
    const raw =
      key === 'volume' ? volRaw(shown('volume'), chip) : Math.round(shown(key))
    debouncers.current[key]?.schedule(raw)
  }

  /** 手填数值：Enter 或失焦提交，越界夹到区间，非法输入丢弃 */
  function commitText(key: SliderKey) {
    const text = texts[key]
    if (text === undefined) return
    setTexts(t => ({ ...t, [key]: undefined }))
    const n = Number(text)
    if (!Number.isFinite(n)) return
    const r = range(key)
    const clamped = Math.max(r.min, Math.min(r.max, Math.round(n)))
    slide(key, clamped)
    debouncers.current[key]?.schedule(key === 'volume' ? volRaw(clamped, chip) : clamped)
  }

  function range(key: SliderKey) {
    if (key === 'volume') return volRange
    return SLIDERS[key]
  }

  const statusNode = (key: ParamKey) => {
    const s = status[key]
    if (!s || s.kind === 'idle') return null
    return (
      <span className={`write ${s.kind}`}>
        {s.kind === 'writing' ? '写入中…' : (s.text ?? (s.kind === 'error' ? '写入失败' : '已写入'))}
      </span>
    )
  }

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
        {failed.length > 0 && (
          <div className="banner">
            以下参数读取失败：
            {failed.map(k => COPY.param[k].label).join('、')}。其余参数可正常使用，可点「重新读取」重试，
            或拔插设备后再连。
          </div>
        )}

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

        {device && (
          <section className="card">
            <div className="card-head">
              <h2>参数均衡器</h2>
              <span className="hint">proEQ · 8 段峰值 · 48 kHz 显示域</span>
              <div className="spacer" />
              <div className="chips">
                {DB_RANGES.map(r => (
                  <button
                    key={r}
                    className={`chip ${dbRange === r ? 'on' : ''}`}
                    onClick={() => setDbRange(r)}
                  >
                    ±{r} dB
                  </button>
                ))}
              </div>
            </div>
            <EqChart bands={bands} range={dbRange} />
            <div className="bands">
              {bands.map((b, i) => (
                <div className="band" key={`${b.freq}-${i}`}>
                  <span className="band-i">{i + 1}</span>
                  <span className="band-f">{b.freq >= 1000 ? `${b.freq / 1000}k` : b.freq}</span>
                  <span className="band-g">{b.gain > 0 ? `+${b.gain}` : b.gain}</span>
                </div>
              ))}
            </div>
            <p className="hint">
              {device.kind === 'simulator'
                ? '模拟器示例曲线；真机上此处显示设备内 EQ'
                : '设备内 EQ 读取将在写入功能接入后同步，当前显示为平直曲线'}
            </p>
          </section>
        )}

        {device && state && (
          <section className="card">
            <div className="card-head">
              <h2>{COPY.sectionState}</h2>
              <span className="hint">{COPY.sectionStateHint}</span>
            </div>
            <div className="params">
              {(['volume', 'mic', 'balance'] as const).map(key => {
                const r = range(key)
                return (
                  <div className="param param-wide" key={key}>
                    <div className="param-top">
                      <span className="param-label">{COPY.param[key].label}</span>
                      <input
                        className="num"
                        type="text"
                        inputMode="numeric"
                        value={texts[key] ?? String(shown(key))}
                        disabled={status[key]?.kind === 'writing'}
                        onChange={e => setTexts(t => ({ ...t, [key]: e.target.value }))}
                        onBlur={() => commitText(key)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') e.currentTarget.blur()
                          if (e.key === 'Escape') {
                            setTexts(t => ({ ...t, [key]: undefined }))
                            e.currentTarget.blur()
                          }
                        }}
                        aria-label={`${COPY.param[key].label} 数值`}
                      />
                      {statusNode(key)}
                    </div>
                    <input
                      className="slider"
                      type="range"
                      min={r.min}
                      max={r.max}
                      step={1}
                      value={shown(key)}
                      disabled={status[key]?.kind === 'writing'}
                      onChange={e => slide(key, Number(e.target.value))}
                      onPointerUp={() => commit(key)}
                      onKeyUp={() => commit(key)}
                      aria-label={COPY.param[key].label}
                    />
                    <span className="param-hint">{COPY.param[key].hint}</span>
                  </div>
                )
              })}

              <div className="param param-wide">
                <div className="param-top">
                  <span className="param-label">{COPY.param.filter.label}</span>
                  {statusNode('filter')}
                </div>
                <div className="chips">
                  {COPY.filterModes.map((name, i) => (
                    <button
                      key={name}
                      className={`chip ${state.filter === i ? 'on' : ''}`}
                      onClick={() => apply('filter', i)}
                    >
                      {name}
                    </button>
                  ))}
                </div>
                <span className="param-hint">{COPY.param.filter.hint}</span>
              </div>

              <div className="param">
                <div className="param-top">
                  <span className="param-label">{COPY.param.gain.label}</span>
                  {statusNode('gain')}
                </div>
                <div className="chips">
                  {COPY.gainLevels.map((name, i) => (
                    <button
                      key={name}
                      className={`chip ${state.gain === i ? 'on' : ''}`}
                      onClick={() => apply('gain', i)}
                    >
                      {name}
                    </button>
                  ))}
                </div>
                <span className="param-hint">{COPY.param.gain.hint}</span>
              </div>

              <div className="param">
                <div className="param-top">
                  <span className="param-label">{COPY.param.led.label}</span>
                </div>
                <strong className="param-value small">{failed.includes('led') ? '—' : state.led ? '开' : '关'}</strong>
                <span className="param-hint">{COPY.param.led.hint}</span>
              </div>

              <div className="param">
                <div className="param-top">
                  <span className="param-label">{COPY.param.firmware.label}</span>
                </div>
                <strong className="param-value small">
                  {failed.includes('firmware') ? '—' : state.firmware}
                </strong>
                <span className="param-hint">{COPY.param.firmware.hint}</span>
              </div>
            </div>
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
