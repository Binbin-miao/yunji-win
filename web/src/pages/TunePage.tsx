import { useState } from 'react'
import { COPY } from '../copy'
import EqChart from '../components/EqChart'
import { DB_RANGES, type EqBand } from '../domain/eq'
import { MAX_BANDS } from '../domain/eqEdit'
import type { ConnectedDevice, DeviceState } from '../transport/types'
import type { ParamKey, SliderKey, WriteStatus } from '../types/ui'

interface Props {
  device: ConnectedDevice
  state: DeviceState | null
  failed: Array<keyof DeviceState>
  bands: EqBand[]
  onBandsChange: (bands: EqBand[]) => void
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
      <section className="card">
        <div className="card-head">
          <h2>参数均衡器</h2>
          <span className="hint">proEQ · 8 段峰值 · 48 kHz 显示域</span>
          <div className="spacer" />
          <div className="chips">
            {DB_RANGES.map(r => (
              <button key={r} className={`chip ${dbRange === r ? 'on' : ''}`} onClick={() => onDbRange(r)}>
                ±{r} dB
              </button>
            ))}
          </div>
        </div>
        <EqChart
          bands={bands}
          range={dbRange}
          selected={selected}
          onSelect={setSelected}
          onChange={onBandsChange}
        />
        <p className="hint ops">
          拖动锚点改频率与增益 · Ctrl 拖动锁单轴 · 滚轮／Shift+滚轮调 Q · 点空白加段（最多 {MAX_BANDS} 段）·
          双击归零 · 右键删除 · 方向键微调 · Delete 删除
          {bands.length >= MAX_BANDS && <span className="write warn"> 已满 {MAX_BANDS} 段，删掉一段才能再加</span>}
        </p>
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
            ? '模拟器示例曲线，改完不会写入任何设备'
            : '曲线改动只存在本地，写入设备在 09 号工单接入'}
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
