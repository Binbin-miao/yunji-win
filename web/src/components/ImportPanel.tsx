import { useRef, useState } from 'react'
import MiniCurve from './MiniCurve'
import type { EqBand } from '../domain/eq'
import { fitParsed, type FitResult } from '../domain/eqFit'
import { parseEqText, type ParseResult } from '../domain/eqImport'
import { MAX_BANDS } from '../domain/eqEdit'

interface Props {
  onApply: (bands: EqBand[]) => void
}

/** 导入面板：粘贴或拖文件，支持四种格式，应用前先预览 */
export default function ImportPanel({ onApply }: Props) {
  const [text, setText] = useState('')
  const [result, setResult] = useState<ParseResult | null>(null)
  const [dragging, setDragging] = useState(false)
  const [fit, setFit] = useState<FitResult | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)

  function parse(src: string) {
    setText(src)
    setResult(src.trim() ? parseEqText(src) : null)
    setFit(null)
  }

  async function readFile(file: File) {
    parse(await file.text())
  }

  function apply() {
    if (!result?.ok) return
    const bands = result.result.bands
    if (!bands.length) return
    onApply(bands.slice(0, MAX_BANDS))
    setResult(null)
    setText('')
  }

  function runFit() {
    if (!result?.ok) return
    setFit(fitParsed(result.result))
  }

  const ok = result?.ok === true
  const bandCount = ok ? result.result.bands.length : 0
  const pointCount = ok ? result.result.graphic.length : 0
  const tooMany = bandCount > MAX_BANDS
  const needFit = ok && (pointCount > 0 || tooMany)
  const canApply = ok && bandCount > 0 && !tooMany

  return (
    <div
      className={`import-panel ${dragging ? 'dragging' : ''}`}
      onDragOver={e => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => {
        e.preventDefault()
        setDragging(false)
        const file = e.dataTransfer.files?.[0]
        if (file) void readFile(file)
      }}
    >
      <div className="row">
        <textarea
          className="import-text"
          placeholder={
            '把配置粘在这里，或把文件拖进这个框：\n' +
            'Equalizer APO / AutoEQ 参数式、GraphicEQ、Wavelet JSON、本工具 JSON 都可以'
          }
          value={text}
          onChange={e => parse(e.target.value)}
          rows={6}
          spellCheck={false}
        />
      </div>
      <div className="row">
        <button className="chip" onClick={() => fileRef.current?.click()}>
          选择文件
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.json,application/json,text/plain"
          hidden
          onChange={e => {
            const file = e.target.files?.[0]
            if (file) void readFile(file)
            e.target.value = ''
          }}
        />
        {result && !result.ok && <span className="write error">解析失败：{result.error}</span>}
        {ok && (
          <span className="hint">
            识别为「{result.result.format}」
            {bandCount > 0 && ` · ${bandCount} 段`}
            {pointCount > 0 && ` · ${pointCount} 个频点`}
            {result.result.preamp !== undefined && ` · Preamp ${result.result.preamp} dB`}
          </span>
        )}
        <div className="spacer" />
        <button className="chip" onClick={apply} disabled={!canApply}>
          应用到曲线
        </button>
      </div>

      {ok && result.result.warnings.map(w => (
        <p className="hint warn-text" key={w}>
          {w}
        </p>
      ))}
      {needFit && !fit && (
        <div className="row">
          <span className="hint warn-text">
            {pointCount > 0
              ? `这是 ${pointCount} 个频点的折线，设备只吃 ${MAX_BANDS} 段，需要先拟合`
              : `导入 ${bandCount} 段，超过设备 ${MAX_BANDS} 段上限，需要先拟合`}
          </span>
          <div className="spacer" />
          <button className="chip" onClick={runFit}>
            拟合成 {MAX_BANDS} 段
          </button>
        </div>
      )}

      {fit && (
        <div className="fit-preview">
          <div className="fit-charts">
            <div className="fit-chart">
              <span className="hint">目标</span>
              <MiniCurve series={fit.target} width={140} height={52} color="#79E0D0" />
            </div>
            <div className="fit-chart">
              <span className="hint">拟合结果</span>
              <MiniCurve series={fit.fitted} width={140} height={52} />
            </div>
            <div className="fit-metrics">
              <span>
                最大误差 <b>{fit.maxError.toFixed(2)} dB</b>
              </span>
              <span>
                RMS 误差 <b>{fit.rmsError.toFixed(2)} dB</b>
              </span>
              <span className="hint">源 {fit.sourceCount} → {fit.bands.length} 段</span>
            </div>
            <div className="spacer" />
            <button className="chip" onClick={() => setFit(null)}>
              放弃拟合
            </button>
            <button
              className="btn"
              onClick={() => {
                onApply(fit.bands)
                setFit(null)
                setResult(null)
                setText('')
              }}
            >
              应用拟合结果
            </button>
          </div>
          <div className="fit-bands">
            {fit.bands.map((b, i) => (
              <span key={i} className="mono dim">
                {b.freq >= 1000 ? `${(b.freq / 1000).toFixed(1)}k` : b.freq}Hz {b.gain > 0 ? '+' : ''}
                {b.gain}dB Q{b.q}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
