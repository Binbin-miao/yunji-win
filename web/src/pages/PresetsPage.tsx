import { useEffect, useRef, useState } from 'react'
import MiniCurve from '../components/MiniCurve'
import type { EqBand } from '../domain/eq'
import { createPreset, parsePresets, serializePresets, type Preset } from '../domain/presets'
import { loadPresets, savePresets } from '../storage/presets'

interface Props {
  bands: EqBand[]
  deviceName: string | null
  onApply: (bands: EqBand[]) => void
}

export default function PresetsPage({ bands, deviceName, onApply }: Props) {
  const [presets, setPresets] = useState<Preset[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [renaming, setRenaming] = useState<string | null>(null)
  const [renameText, setRenameText] = useState('')
  const fileRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    const { presets: list, error } = loadPresets()
    setPresets(list)
    if (error) setNotice(error)
  }, [])

  function persist(next: Preset[]) {
    setPresets(next)
    const err = savePresets(next)
    if (err) setNotice(err)
  }

  function saveCurrent() {
    const preset = createPreset(name || `预设 ${presets.length + 1}`, bands)
    persist([preset, ...presets])
    setName('')
    setNotice(`已保存「${preset.name}」`)
  }

  function exportAll() {
    const blob = new Blob([serializePresets(presets)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `yunji-presets-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function importFile(file: File) {
    const text = await file.text()
    const { presets: incoming, error } = parsePresets(text)
    if (error) {
      setNotice(`导入失败：${error}`)
      return
    }
    const merged = [...incoming, ...presets]
    persist(merged)
    setNotice(`已导入 ${incoming.length} 个预设`)
  }

  return (
    <>
      <section className="card">
        <div className="card-head">
          <h2>预设</h2>
          <span className="hint">把当前 8 段曲线存成命名快照，可随时切回来</span>
        </div>
        <div className="row">
          <input
            className="text"
            placeholder={`预设名称（默认「预设 ${presets.length + 1}」）`}
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') saveCurrent()
            }}
            aria-label="预设名称"
          />
          <button className="btn" onClick={saveCurrent}>
            保存当前曲线
          </button>
          <span className="hint">当前设备：{deviceName ?? '未连接'}</span>
        </div>
        <p className="hint warn-text">
          预设只存在这台浏览器里，换电脑或清缓存会丢。重要调音请用「导出」备份。
        </p>
        {notice && <div className="banner sim">{notice}</div>}
      </section>

      <section className="card">
        <div className="card-head">
          <h2>已有预设（{presets.length}）</h2>
          <div className="spacer" />
          <button className="chip" onClick={exportAll} disabled={!presets.length}>
            导出全部
          </button>
          <button className="chip" onClick={() => fileRef.current?.click()}>
            导入 JSON
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={e => {
              const file = e.target.files?.[0]
              if (file) void importFile(file)
              e.target.value = ''
            }}
          />
        </div>

        {!presets.length ? (
          <p className="hint">还没有预设。调好曲线后点上面的「保存当前曲线」。</p>
        ) : (
          <div className="preset-list">
            {presets.map(p => (
              <div className="preset" key={p.id}>
                <MiniCurve bands={p.bands} />
                <div className="preset-main">
                  {renaming === p.id ? (
                    <input
                      className="text small"
                      value={renameText}
                      autoFocus
                      onChange={e => setRenameText(e.target.value)}
                      onBlur={() => {
                        const next = presets.map(x =>
                          x.id === p.id ? { ...x, name: renameText.trim() || x.name } : x,
                        )
                        persist(next)
                        setRenaming(null)
                      }}
                      onKeyDown={e => {
                        if (e.key === 'Enter') e.currentTarget.blur()
                        if (e.key === 'Escape') setRenaming(null)
                      }}
                    />
                  ) : (
                    <strong className="preset-name">{p.name}</strong>
                  )}
                  <span className="hint">
                    {p.bands.length} 段 · {new Date(p.createdAt).toLocaleString()}
                  </span>
                </div>
                <div className="preset-actions">
                  <button className="chip" onClick={() => onApply(p.bands)}>
                    应用
                  </button>
                  <button
                    className="chip"
                    onClick={() => {
                      setRenaming(p.id)
                      setRenameText(p.name)
                    }}
                  >
                    改名
                  </button>
                  <button
                    className="chip"
                    onClick={() => persist([{ ...p, id: `${p.id}c${Date.now().toString(36)}`, name: `${p.name} 副本`, createdAt: Date.now() }, ...presets])}
                  >
                    复制
                  </button>
                  <button className="chip" onClick={() => persist(presets.filter(x => x.id !== p.id))}>
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  )
}
