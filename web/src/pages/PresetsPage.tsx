export default function PresetsPage() {
  return (
    <section className="card">
      <div className="card-head">
        <h2>预设</h2>
        <span className="hint">存一组 8 段参数 + 全局参数，可命名、导出 JSON</span>
      </div>
      <p className="hint">
        这部分还没做（13 号工单）。计划：预设列表带缩略曲线、一键切换、重命名/复制/删除、
        导出与导入 JSON，数据存在浏览器本地并在界面上明确提示「换电脑或清缓存会丢」。
      </p>
    </section>
  )
}
