import { useState } from 'react'
import { COPY } from '../copy'
import BandEditor from '../components/BandEditor'
import ImportPanel from '../components/ImportPanel'
import FilterPicker from '../components/FilterPicker'
import EqChart from '../components/EqChart'
import { TARGETS } from '../data/targets'
import { DB_RANGES, type EqBand } from '../domain/eq'
import { diffStats } from '../domain/target'
import { MAX_BANDS, freqLimits, removeBand, replaceBand } from '../domain/eqEdit'
import type { ConnectedDevice, DeviceState } from '../transport/types'
import type { ParamKey, SliderKey, WriteStatus } from '../types/ui'

interface Props {
  device: ConnectedDevice
  state: DeviceState | null
  failed: Array<keyof DeviceState>
  bands: EqBand[]
  onBandsChange: (bands: EqBand[], transient?: boolean) => void
  onBandsBegin: () => void
  onBandsCommit: () => void
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  eqStatus: WriteStatus
  onWriteEq: () => void
  dbRange: (typeof DB_RANGES)[number]
  onDbRange: (r: (typeof DB_RANGES)[number]) => void
  status: Partial<Record<ParamKey, WriteStatus>>
  texts: Partial<Record<SliderKey, string>>
  setText: (key: SliderKey, value: string | undefined) => void
  shown: (key: SliderKey) => number
  range: (key: SliderKey) => { min: number; max: number }
  slide: (key: SliderKey, value: number) => void
  commit: (key: SliderKey) => void
  commitText: (key: SliderKey) => void
  apply: (key: ParamKey, value: number) => void
}

export default function TunePage({
  device,
  state,
  failed,
  bands,
  onBandsChange,
  onBandsBegin,
  onBandsCommit,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  eqStatus,
  onWriteEq,
  dbRange,
  onDbRange,
  status,
  texts,
  setText,
  shown,
  range,
  slide,
  commit,
  commitText,
  apply,
}: Props) {
  const [selected, setSelected] = useState<number | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [importing, setImporting] = useState(false)
  const [targetId, setTargetId] = useState('none')
  const [showOps, setShowOps] = useState(() => localStorage.getItem('yunji.opsHidden') !== '1')

  const target = TARGETS.find(t => t.id === targetId) ?? null
  const stats = target ? diffStats(bands, target) : null

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
    <>
      <section className="card hero">
        <div className="card-head">
          <h2>参数均衡器</h2>
          <span className="hint">proEQ · 8 段峰值 · 48 kHz 显示域</span>
          <div className="card-actions">
            <button
              className="chip"
              onClick={onUndo}
              disabled={!canUndo}
              title={`${COPY.controls.undo.hint}（Ctrl+Z）`}
            >
              {COPY.controls.undo.label}
            </button>
            <button
              className="chip"
              onClick={onRedo}
              disabled={!canRedo}
              title={`${COPY.controls.redo.hint}（Ctrl+Shift+Z）`}
            >
              {COPY.controls.redo.label}
            </button>
            <button
              className="chip"
              onClick={() => setImporting(v => !v)}
              title={COPY.controls.import.hint}
            >
              {importing ? '收起导入' : COPY.controls.import.label}
            </button>
            <button
              className="btn"
              onClick={() => setConfirming(true)}
              disabled={eqStatus.kind === 'writing' || device.kind === 'simulator'}
              title={device.kind === 'simulator' ? '模拟器不写入设备' : COPY.controls.writeEq.hint}
            >
              {eqStatus.kind === 'writing' ? COPY.controls.writeEqDone.label : COPY.controls.writeEq.label}
            </button>
          </div>
        </div>
        {importing && <ImportPanel onApply={next => onBandsChange(next, false)} />}
        {confirming && (
          <div className="confirm">
            <span>将把当前 8 段写入设备并覆盖现有 EQ，写入后设备会短暂断音。</span>
            <button
              className="chip"
              onClick={() => {
                setConfirming(false)
                onWriteEq()
              }}
            >
              {COPY.controls.confirmWrite.label}
            </button>
            <button className="chip" onClick={() => setConfirming(false)}>
              {COPY.controls.cancel.label}
            </button>
          </div>
        )}
        {eqStatus.kind !== 'idle' && eqStatus.kind !== 'writing' && (
          <div className={`banner ${eqStatus.kind === 'error' ? 'error' : 'sim'}`}>
            {eqStatus.text ?? (eqStatus.kind === 'done' ? '已写入设备' : '写入失败')}
          </div>
        )}

        <div className="row target-row">
          <span className="hint label">目标曲线</span>
          <button
            className={`chip ${targetId === 'none' ? 'on' : ''}`}
            aria-pressed={targetId === 'none'}
            onClick={() => setTargetId('none')}
            title={COPY.controls.targetNone.hint}
          >
            {COPY.controls.targetNone.label}
          </button>
          {TARGETS.map(t => (
            <button
              key={t.id}
              className={`chip ${targetId === t.id ? 'on' : ''}`}
              aria-pressed={targetId === t.id}
              onClick={() => setTargetId(t.id)}
              title={t.source}
            >
              {t.label}
            </button>
          ))}
          {stats && (
            <span className="hint diff-readout">
              最大高出 {stats.maxPos!.db.toFixed(1)} dB @{Math.round(stats.maxPos!.freq)} Hz · 最大缺口{' '}
              {stats.maxNeg!.db.toFixed(1)} dB @{Math.round(stats.maxNeg!.freq)} Hz · RMS{' '}
              {stats.rms.toFixed(1)} dB
            </span>
          )}
          <div className="view-opts">
              <span className="hint label">纵轴</span>
              {DB_RANGES.map(r => (
                <button
                  key={r}
                  className={`chip ${dbRange === r ? 'on' : ''}`}
                  aria-pressed={dbRange === r}
                  onClick={() => onDbRange(r)}
                >
                  ±{r} dB
                </button>
              ))}
          </div>
        </div>

        <EqChart
          bands={bands}
          target={target}
          range={dbRange}
          selected={selected}
          onSelect={setSelected}
          onChange={onBandsChange}
          onBegin={onBandsBegin}
          onCommit={onBandsCommit}
        />
        {showOps ? (
          <p className="hint ops">
            {COPY.ops.eq} · {COPY.ops.limit.replace('{n}', String(MAX_BANDS))}
            {bands.length >= MAX_BANDS && (
              <span className="write warn">
                {' '}
                {COPY.ops.full.replace('{n}', String(MAX_BANDS))}
              </span>
            )}
            <button
              className="link"
              onClick={() => {
                localStorage.setItem('yunji.opsHidden', '1')
                setShowOps(false)
              }}
            >
              {COPY.ops.hide}
            </button>
          </p>
        ) : (
          <p className="hint ops">
            <button
              className="link"
              onClick={() => {
                localStorage.removeItem('yunji.opsHidden')
                setShowOps(true)
              }}
            >
              {COPY.ops.show}
            </button>
          </p>
        )}
        <div className="bands">
          {bands.map((b, i) => (
            <button
              type="button"
              className={`band ${selected === i ? 'on' : ''}`}
              key={`${b.freq}-${i}`}
              aria-pressed={selected === i}
              onClick={() => setSelected(i)}
              title={`第 ${i + 1} 段：${b.freq} Hz / ${b.gain} dB / Q ${b.q}`}
            >
              <span className="band-i">{i + 1}</span>
              <span className="band-f">{b.freq >= 1000 ? `${b.freq / 1000}k` : b.freq}</span>
              <span className="band-g">{b.gain > 0 ? `+${b.gain}` : b.gain}</span>
            </button>
          ))}
        </div>

        {selected !== null && bands[selected] && (
          <BandEditor
            band={bands[selected]}
            index={selected}
            limits={freqLimits(bands, selected)}
            onChange={band => onBandsChange(replaceBand(bands, selected, band))}
            onDelete={() => {
              onBandsChange(removeBand(bands, selected))
              setSelected(null)
            }}
          />
        )}
        <p className="hint">
          {device.kind === 'simulator' ? COPY.eqSimHint : COPY.eqLocalHint}
        </p>
      </section>

      <section className="card">
        <div className="card-head">
          <h2>{COPY.sectionState}</h2>
          <span className="hint">{COPY.sectionStateHint}</span>
        </div>
        {!state ? (
          <p className="hint">{COPY.reading}</p>
        ) : (
          <div className="params">
            <span className="group-title">音量与声道</span>
            {(['volume', 'mic', 'balance'] as const).map(key => {
              const r = range(key)
              return (
                <div className="param" key={key}>
                  <div className="param-top">
                    <span className="param-label">{COPY.param[key].label}</span>
                    <input
                      className="num"
                      type="text"
                      inputMode="numeric"
                      value={texts[key] ?? String(shown(key))}
                      disabled={status[key]?.kind === 'writing'}
                      onChange={e => setText(key, e.target.value)}
                      onBlur={() => commitText(key)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') e.currentTarget.blur()
                        if (e.key === 'Escape') {
                          setText(key, undefined)
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

            <span className="group-title">输出模式与设备状态</span>
            <div className="param param-full">
              <div className="param-top">
                <span className="param-label">{COPY.param.filter.label}</span>
                <span className="param-hint">{COPY.param.filter.hint}</span>
                <div className="spacer" />
                {statusNode('filter')}
              </div>
              <FilterPicker
                value={state.filter}
                disabled={status.filter?.kind === 'writing'}
                onChange={i => apply('filter', i)}
              />
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
                    aria-pressed={state.gain === i}
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
              <strong className="param-value small">
                {failed.includes('led') ? '—' : state.led ? '开' : '关'}
              </strong>
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
        )}
      </section>
    </>
  )
}
