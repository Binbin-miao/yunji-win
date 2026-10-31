import { useCallback, useEffect, useRef, useState } from 'react'
import { COPY } from './copy'
import { createDebouncer, type Debouncer } from './domain/commit'
import { DB_RANGES, DEFAULT_BANDS, DEMO_BANDS, type EqBand } from './domain/eq'
import { createHistory, type History } from './domain/history'
import { balDisplay, micDisplay, volBounds, volDisplay, volRaw } from './domain/params'
import { SimulatorTransport } from './transport/simulator'
import { WebHidTransport } from './transport/webhid'
import { STAGE_TEXT, TransportError } from './transport/errors'
import type { ConnectedDevice, DeviceState, Transport } from './transport/types'
import type { PageKey, ParamKey, SliderKey, WriteStatus } from './types/ui'
import ConnectPage from './pages/ConnectPage'
import TunePage from './pages/TunePage'
import PresetsPage from './pages/PresetsPage'
import AboutPage from './pages/AboutPage'

const isMobile = /Android|iPhone|iPad|iPod|Mobile/i.test(
  typeof navigator === 'undefined' ? '' : navigator.userAgent,
)

const SLIDERS: Record<SliderKey, { min: number; max: number }> = {
  volume: { min: 0, max: 60 }, // 运行时按芯片覆盖
  mic: { min: -30, max: 30 },
  balance: { min: -20, max: 20 },
}

const NAV: Array<{ key: PageKey; icon: string; label: string }> = [
  { key: 'connect', icon: '◈', label: '连接' },
  { key: 'tune', icon: '∿', label: '调音' },
  { key: 'presets', icon: '⌸', label: '预设' },
  { key: 'about', icon: '⌾', label: '关于' },
]

export default function App() {
  const [page, setPage] = useState<PageKey>('connect')
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
  const historyRef = useRef<History<EqBand[]>>(createHistory<EqBand[]>(DEFAULT_BANDS))
  /** 地址里指定了页签时，连接后不自动跳到调音页 */
  const pinnedPage = useRef(false)
  const [dbRange, setDbRange] = useState<(typeof DB_RANGES)[number]>(12)
  const [eqStatus, setEqStatus] = useState<WriteStatus>({ kind: 'idle' })

  const debouncers = useRef<Partial<Record<SliderKey, Debouncer<number>>>>({})
  const sessionRef = useRef(0)
  const applyRef = useRef<(key: ParamKey, value: number) => void>(() => undefined)
  const transportRef = useRef<Transport | null>(null)

  function changeBands(next: EqBand[], transient = false) {
    historyRef.current.set(next, transient)
    setBands(historyRef.current.present)
  }
  function beginBands() {
    historyRef.current.begin()
  }
  function commitBands() {
    historyRef.current.commit()
    setBands(historyRef.current.present)
  }
  function undoBands() {
    historyRef.current.undo()
    setBands(historyRef.current.present)
  }
  function redoBands() {
    historyRef.current.redo()
    setBands(historyRef.current.present)
  }

  // 全局撤销/重做快捷键（输入框内不拦截）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      const key = e.key.toLowerCase()
      if (key === 'z') {
        e.preventDefault()
        if (e.shiftKey) {
          historyRef.current.redo()
        } else {
          historyRef.current.undo()
        }
        setBands(historyRef.current.present)
      } else if (key === 'y') {
        e.preventDefault()
        historyRef.current.redo()
        setBands(historyRef.current.present)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    setHidReady(WebHidTransport.supported())
  }, [])

  // 拔线后清空界面
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

  const apply = useCallback(
    async (key: ParamKey, value: number) => {
      const t = transportRef.current
      if (!t) return
      const session = sessionRef.current
      setStatus(s => ({ ...s, [key]: { kind: 'writing' } }))

      const finish = (sent: number, back: number, describe: (v: number) => string) => {
        if (session !== sessionRef.current) return
        if (back === sent) {
          setStatus(s => ({ ...s, [key]: { kind: 'done', text: `已写入 ${describe(back)}` } }))
        } else {
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
        } else {
          const back = await t.setGain(value)
          if (session !== sessionRef.current) return
          setState(s => (s ? { ...s, gain: back } : s))
          finish(value, back, v => COPY.gainLevels[v] ?? String(v))
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
          /* 回读失败时保留原状态，错误已提示 */
        }
      }
    },
    [chip],
  )

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
        const initial = connected.kind === 'simulator' ? DEMO_BANDS : DEFAULT_BANDS
        historyRef.current.reset(initial)
        setBands(initial)
        attach()
        await load(next)
        if (!pinnedPage.current) setPage('tune')
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setBusy(false)
      }
    },
    [attach, load],
  )

  // 开发/演示用：?page=presets 直达某个页签
  useEffect(() => {
    const target = new URLSearchParams(window.location.search).get('page')
    if (target === 'connect' || target === 'tune' || target === 'presets' || target === 'about') {
      setPage(target)
      pinnedPage.current = true
    }
  }, [])

  // 开发/演示用：地址带 ?sim=1 直接进模拟器
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
      setPage('connect')
      setBusy(false)
    }
  }

  const volRange = volBounds(chip)

  function shown(key: SliderKey): number {
    if (drafts[key] !== undefined) return drafts[key]!
    if (!state) return key === 'volume' ? volRange.max : 0
    if (key === 'volume') return volDisplay(state.volume, chip)
    if (key === 'mic') return state.mic
    return state.balance
  }

  function range(key: SliderKey) {
    if (key === 'volume') return volRange
    return SLIDERS[key]
  }

  function slide(key: SliderKey, v: number) {
    setDrafts(d => ({ ...d, [key]: v }))
    setStatus(s => ({ ...s, [key]: { kind: 'idle' } }))
  }

  function commit(key: SliderKey) {
    const raw = key === 'volume' ? volRaw(shown('volume'), chip) : Math.round(shown(key))
    debouncers.current[key]?.schedule(raw)
  }

  function commitText(key: SliderKey) {
    const text = texts[key]
    if (text === undefined) return
    setText(key, undefined)
    const n = Number(text)
    if (!Number.isFinite(n)) return
    const r = range(key)
    const clamped = Math.max(r.min, Math.min(r.max, Math.round(n)))
    slide(key, clamped)
    debouncers.current[key]?.schedule(key === 'volume' ? volRaw(clamped, chip) : clamped)
  }

  function setText(key: SliderKey, value: string | undefined) {
    setTexts(t => ({ ...t, [key]: value }))
  }

  async function writeEq() {
    const t = transportRef.current
    if (!t) return
    setEqStatus({ kind: 'writing' })
    try {
      const result = await t.setEq(bands)
      setEqStatus(
        result.dspRefreshed
          ? { kind: 'done', text: '已写入设备并生效' }
          : { kind: 'warn', text: '参数已写入，但生效刷新未确认，可用官方 App 复核' },
      )
    } catch (e) {
      const msg =
        e instanceof TransportError
          ? `${STAGE_TEXT[e.stage]}：${e.message}`
          : e instanceof Error
            ? e.message
            : String(e)
      setEqStatus({ kind: 'error', text: msg })
    }
  }

  const statusText = device ? (device.kind === 'simulator' ? '模拟器' : '已连接') : '未连接'

  // 手机上渲染整套桌面界面会破版，且 WebHID 本来就不存在：只给一句「请用电脑」
  if (isMobile) {
    return (
      <div className="gate">
        <strong>{COPY.mobileTitle}</strong>
        <p>{COPY.mobile}</p>
        <p className="hint">{COPY.mobileWhy}</p>
      </div>
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
          {NAV.map(item => (
            <button
              key={item.key}
              className={`rail-item ${page === item.key ? 'on' : ''}`}
              onClick={() => setPage(item.key)}
              title={item.label}
              aria-label={item.label}
            >
              {item.icon}
            </button>
          ))}
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
          <span className="hint">{NAV.find(n => n.key === page)?.label}</span>
        </header>

        {device?.kind === 'simulator' && <div className="banner sim">{COPY.simBanner}</div>}

        {page === 'connect' && (
          <ConnectPage
            device={device}
            state={state}
            failed={failed}
            hidReady={hidReady}
            isMobile={isMobile}
            busy={busy}
            reading={reading}
            error={error}
            onConnectReal={() => run(new WebHidTransport())}
            onConnectSim={() => run(new SimulatorTransport())}
            onReload={() => transport && load(transport)}
            onDisconnect={disconnect}
          />
        )}

        {page === 'tune' &&
          (device ? (
            <TunePage
              device={device}
              state={state}
              failed={failed}
              bands={bands}
              onBandsChange={changeBands}
              onBandsBegin={beginBands}
              onBandsCommit={commitBands}
              canUndo={historyRef.current.canUndo}
              canRedo={historyRef.current.canRedo}
              onUndo={undoBands}
              onRedo={redoBands}
              eqStatus={eqStatus}
              onWriteEq={writeEq}
              dbRange={dbRange}
              onDbRange={setDbRange}
              status={status}
              texts={texts}
              setText={setText}
              shown={shown}
              range={range}
              slide={slide}
              commit={commit}
              commitText={commitText}
              apply={(key, value) => void apply(key, value)}
            />
          ) : (
            <section className="card">
              <div className="card-head">
                <h2>还没连接设备</h2>
              </div>
              <p className="hint">先去「连接」页连接真机，或点下面进入模拟器。</p>
              <div className="row" style={{ marginTop: 12 }}>
                <button className="btn" onClick={() => setPage('connect')}>
                  去连接
                </button>
                <button className="btn ghost" onClick={() => run(new SimulatorTransport())} disabled={busy}>
                  {COPY.connectSim}
                </button>
              </div>
            </section>
          ))}

        {page === 'presets' && (
          <PresetsPage
            bands={bands}
            deviceName={device?.name ?? null}
            onApply={next => {
              changeBands(next, false)
              setPage('tune')
            }}
          />
        )}
        {page === 'about' && <AboutPage device={device} state={state} failed={failed} />}
      </main>
    </div>
  )
}
