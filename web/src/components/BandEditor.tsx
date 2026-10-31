import { useState } from 'react'
import type { EqBand } from '../domain/eq'
import { MAX_GAIN, MAX_Q, MIN_Q, clampBand, type FreqLimits } from '../domain/eqEdit'

interface FieldProps {
  label: string
  unit: string
  value: string
  onCommit: (raw: string) => void
}

/** 单个数值输入框：Enter 或失焦提交，Esc 取消 */
function Field({ label, unit, value, onCommit }: FieldProps) {
  const [text, setText] = useState<string | null>(null)
  return (
    <label className="bf">
      <span className="bf-label">{label}</span>
      <input
        className="num bf-num"
        type="text"
        inputMode="decimal"
        value={text ?? value}
        onChange={e => setText(e.target.value)}
        onBlur={() => {
          if (text !== null) onCommit(text)
          setText(null)
        }}
        onKeyDown={e => {
          if (e.key === 'Enter') e.currentTarget.blur()
          if (e.key === 'Escape') {
            setText(null)
            e.currentTarget.blur()
          }
          if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
            e.preventDefault()
            const n = Number(text ?? value)
            if (!Number.isFinite(n)) return
            const step = e.shiftKey ? 10 : 1
            onCommit(String(n + (e.key === 'ArrowUp' ? step : -step)))
          }
        }}
      />
      <span className="bf-unit">{unit}</span>
    </label>
  )
}

interface Props {
  band: EqBand
  index: number
  limits: FreqLimits
  onChange: (band: EqBand) => void
  onDelete: () => void
}

/** 选中段的数值编辑区 */
export default function BandEditor({ band, index, limits, onChange, onDelete }: Props) {
  const commit = (patch: Partial<EqBand>) => onChange(clampBand({ ...band, ...patch }, limits))

  return (
    <div className="band-edit">
      <span className="band-edit-title">第 {index + 1} 段</span>
      <Field
        label="频率"
        unit="Hz"
        value={String(band.freq)}
        onCommit={raw => {
          const n = Number(raw)
          if (Number.isFinite(n)) commit({ freq: n })
        }}
      />
      <Field
        label="增益"
        unit="dB"
        value={band.gain.toFixed(1)}
        onCommit={raw => {
          const n = Number(raw)
          if (Number.isFinite(n)) commit({ gain: Math.max(-MAX_GAIN, Math.min(MAX_GAIN, n)) })
        }}
      />
      <Field
        label="Q"
        unit=""
        value={band.q.toFixed(2)}
        onCommit={raw => {
          const n = Number(raw)
          if (Number.isFinite(n)) commit({ q: Math.max(MIN_Q, Math.min(MAX_Q, n)) })
        }}
      />
      <span className="bf-range">
        可调范围 {Math.round(limits.minFreq)} – {Math.round(limits.maxFreq)} Hz
      </span>
      <button className="chip" onClick={onDelete} title="删掉选中的频段">
        删除这一段
      </button>
    </div>
  )
}
