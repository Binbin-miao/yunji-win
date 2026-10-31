# AGENTS.md

## 网页版调音台（`web/`）

改 `web/` 之前先读 `docs/web-hid-framing.md`：HID 分帧怎么拼、设备 raw 值与界面显示值的换算、指示灯为什么只读、`01 1E 01 00` 会让设备进红灯闪烁必须重新插拔。

验证跑 `npm --prefix web run check`（tsc + vitest + oxlint）。要看渲染结果或抓渲染后的 DOM：

```bash
node web/tools/shot.mjs "?sim=1&page=tune" --out mock/tune.png   # 自带预览服务
node web/tools/shot.mjs --dom "?sim=1&page=tune"                 # 抓 DOM 文本
```

改曲线区绘制或拟合性能之前先看 `web/BENCH.md`：那是同机同口径的基线，附回归对比口径。

## 协议与机型

`docs/协议参考.md`（命令表、48k 显示域与 96k 设备系数）、`docs/设备适配.md`（8 款机型，旋润 3 款走厂商控制传输，浏览器连不上）。

## 发布边界

构建产物只写 `docs/web/`。`docs/index.html`、`docs/sitemap.xml`、`docs/robots.txt` 是落地页与 SEO 入口，网页版验收通过前不进 sitemap、不加首页入口。

## 桌面版（`app/`）

Python + PySide6。单测 `python tests/run_all.py --unit`。`tests/test_scan.py` 依赖 pyusb/libusb，没装时 10 个 error 属于环境缺失，不是回归。

## 提交门禁

`git config core.hooksPath .githooks` 启用本地钩子，改动 `web/` 或 `docs/web/` 时自动跑 `npm --prefix web run check`。CI 在 `.github/workflows/check.yml` 跑同一条命令。
