# 云姬电脑版 · yunji-win

> **云姬 Windows 版（非官方开源移植）** —— 让云姬小尾巴 / Type-C 解码耳放在电脑上也能自由调音：8 段参数均衡器、DAC 硬件音量、麦克风增益、声道平衡、数字滤波器切换。

**关键词**：云姬电脑版 · 云姬 Windows 版 · 云姬 PC 版 · 云姬电脑端下载 · 小尾巴调音软件 · 解码耳放 EQ 工具 · TTGK · 旋润 · USB DAC 调音

🌐 **官网落地页**：<https://binbin-miao.github.io/yunji-win/> ｜ ⬇ **下载**：[Releases](https://github.com/Binbin-miao/yunji-win/releases/latest)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-brightgreen.svg)]()
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)]()

---

## 📖 项目简介

本项目为独立开发的第三方 Windows 桌面端移植版本（移植参考自官方 Android 端 v1.7.5 架构与通信协议），即社区常说的「**云姬电脑版**」。

由于市面上多数便携式解码耳放（小尾巴）仅提供了移动端 App，Windows 用户在连接电脑使用时往往无法便捷地调节 DAC 滤波模式、耳放增益档位、麦克风输入电平，更无法调用设备内置的硬件 DSP 进行专业 Parametric EQ / Easy EQ 调音。

**本项目实现了：**
- **免驱直通 (TTGK 阵营)**：利用 Windows 内置 HID 驱动，无需安装 WinUSB 或任何第三方驱动，即插即用。
- **全参数硬件 EQ 调节 (ProEQ)**：8 段双二阶 Peaking EQ 实时曲线拟合计算，一键写入硬件 DSP。
- **简易均衡器 (EZEQ)**：针对音乐与游戏场景定制特征频点与调音模板。
- **DAC 与硬件参数精细调节**：硬件音量、声道平衡、麦克风电平、高低增益、滤波器类型、LED 开关。
- **设备热插拔自动侦测**：即插即认，状态自动同步。
- **开源合规与中性设计**：本仓库完全剔除原厂商业资源与专有位图，提供自研中性数据并支持用户外部资源覆盖。

### 调音相关特性

| 功能 | 说明 |
| :--- | :--- |
| **旁通 / A-B 对比** | 一键把 EQ 置为平直以便对比原声，再按一次恢复；也可**按住空格键**临时旁通 |
| **多格式导入** | 支持 Equalizer APO、GraphicEQ、Wavelet、本工具 JSON 四种格式，可直接从 AutoEQ / squig.link 复制粘贴 |
| **自动拟合到 8 段** | 导入 10 段甚至上百点的曲线时，自动用最小二乘拟合为设备的 8 段，并给出拟合误差 |
| **增益补偿（防削波）** | 按当前曲线的峰值增益自动设置整体偏移；超出设备下限时给出明确警告 |
| **目标曲线叠加** | 内置 Harman 入耳式 2019 / 头戴式 2018 / AutoEq 中性三条参考曲线（数据来自 AutoEQ 项目），可直观对比当前调音与目标的差距 |
| **曲线悬停读数** | 鼠标在曲线上移动即显示频点、当前 EQ 值、目标值与偏差 |
| **导出分享图** | 一键导出 PNG（曲线 + 8 段参数表 + 设备名），便于社区分享 |
| **低架 / 高架滤波器** | 实验性功能，默认关闭。见下方说明 |

> ⚠️ **关于低架/高架滤波器（实验性）**
>
> 经逆向确认，官方 Android 版的 `typeList` 字段是**死数据** —— 它只参与 JSON 导入导出的字段搬运，
> 系数计算只有 peaking 一个函数，发包时硬编码写入类型 `2`。也就是说**官方从未向设备发送过峰值以外的类型**，
> 硬件是否识别低架/高架**完全未知**。
>
> 因此该功能默认关闭，需在 ProEQ 页点击「滤波器类型（实验性）」并确认风险提示后才会启用。
> 若设备实际不支持，屏幕上显示的曲线与真实听感会不一致。**请谨慎使用。**

---

## 🖼️ 界面预览

| 设备列表 | TTGK 设备主页 | 参数均衡器 (ProEQ) |
| :---: | :---: | :---: |
| ![设备列表](screenshots/01_device_list.png) | ![TTGK 主页](screenshots/04_ttgk_main.png) | ![ProEQ](screenshots/05_proeq.png) |

| 曲线悬停读数 | 简易均衡器 (EZEQ) | 关于与声明 |
| :---: | :---: | :---: |
| ![悬停读数](screenshots/06_proeq_hover.png) | ![EZEQ](screenshots/07_ezeq.png) | ![关于](screenshots/08_about.png) |

导出的分享图（曲线 + 参数表，可直接发到社区）：

![分享图](screenshots/09_share_card.png)

---

## 🎧 支持硬件

| 品牌 / 协议阵营 | 代表型号 | 通信方式 | 驱动要求 | 核心特性 |
| :--- | :--- | :--- | :--- | :--- |
| **TTGK 系列** | 凌云剑、Q25 等 (CB1200 / CB5100 架构) | USB HID 中断传输 | **Windows 原生免驱** | 8 段硬件 EQ、增益、滤波、LED、声道平衡、麦克风 |
| **旋润 系列** | YUNJI43198PRO、YUNJI43198ULTRA、You Got Me 等 | USB 控制传输 | WinUSB / libusb | 硬件音量、平衡、增益、5 档滤波、LED、防爆音 |

---

## 🚀 快速上手

### 方式一：下载开箱即用的 Release 版本（推荐）

前往 [GitHub Releases](https://github.com/Binbin-miao/yunji-win/releases) 页面，下载最新的 `YunjiSettings-v1.7.5-win64.zip`，解压后双击运行 `YunjiSettings.exe` 即可使用。

### 方式二：从源码运行

要求 Python 3.10 及以上环境：

```bash
# 1. 克隆本仓库
git clone https://github.com/Binbin-miao/yunji-win.git
cd yunji-win

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行桌面端应用
python app/main.py
```

---

## 🛠️ 打包独立 EXE

本项目支持使用 `PyInstaller` 打包为免安装的单目录/单文件程序：

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed \
    --name YunjiSettings \
    --icon app/assets/icons/app.ico \
    --add-data "app/assets;assets" \
    --collect-binaries hidapi \
    --collect-all libusb_package \
    --paths app \
    --distpath dist \
    app/main.py
```

---

## 🎨 资源覆盖机制 (Assets Override)

本开源项目已将所有图标、预设与配置完全中性化。如果高级用户拥有合法提取的原厂或自定义资源包，只需将对应文件夹放置于用户数据目录下：

```text
%APPDATA%\YunjiSettings\assets-override\
  ├── icons\
  ├── ezeq-config\
  ├── ezeq-template\
  └── product-list\
```

软件在启动与读取资源时，将自动优先加载 `assets-override\` 下的内容；若不存在则回退至开源中性资源。

---

## 📚 技术文档

- [硬件通信与 DSP 协议规范](docs/协议参考.md)：包含 TTGK 64 字节 HID 报文定义、旋润 7 字节控制传输协议、8 段 Biquad EQ 定点系数计算公式。

---

## 🧪 测试

```bash
python tests/run_all.py          # 全部（单测 + GUI 冒烟）
python tests/run_all.py --unit   # 仅单元测试
python tests/run_all.py --smoke  # 仅 GUI 冒烟
```

测试**无需硬件**，全部可在离屏模式运行：

| 文件 | 覆盖内容 |
| :--- | :--- |
| `test_protocol.py` | 字节级协议往返（TTGK / 旋润） |
| `test_eq_coeffs.py` | EQ 系数数值回归（重构前后逐字节一致）、peaking/shelf 解析性质、滤波器稳定性（极点半径） |
| `test_eqformat.py` | 四种导入格式的解析与导出往返 |
| `test_fitting.py` | 任意段数 → 8 段的拟合精度（RMS 偏差） |
| `test_scan.py` | 产品表缓存、扫描合并、响应校验、HID 描述符解析、存储原子写入 |
| `smoke_gui.py` | 离屏 GUI 全流程：导航、旁通、增益补偿、四种格式导入、目标曲线、类型切换、分享图导出 |

`tests/screenshots.py` 可重新生成 README 配图。

---

## ❓ 常见问题 (FAQ)

**Q：云姬电脑版是官方软件吗？**
不是。本项目是独立开发者出于学习与跨平台便利性所做的**非官方开源移植**，与任何音频硬件品牌官方均无商业合作、赞助或授权关系，相关商标归原权利人所有。

**Q：云姬电脑版要装驱动吗？**
TTGK 阵营设备使用 Windows 原生 HID 驱动，**无需额外安装任何驱动**，插上即用；旋润阵营设备基于 USB 控制传输，若未识别可参考本文档上方的驱动说明。

**Q：云姬电脑版支持哪些设备？**
目前支持 TTGK 阵营（凌云剑、Q25 等，CB1200 / CB5100 架构）与旋润阵营（YUNJI43198PRO、YUNJI43198ULTRA、You Got Me 等）。若你的设备未在列表内，欢迎在 [Issues](https://github.com/Binbin-miao/yunji-win/issues) 提交设备信息协助适配。

**Q：怎么把 AutoEQ 的调音曲线导入进来？**
在 ProEQ 页点「导入」，把从 AutoEQ / squig.link 复制的内容粘进去即可。支持 Equalizer APO（`Filter 1: ON PK Fc ...`）、GraphicEQ（`GraphicEQ: 20 -3.5; ...`）、Wavelet JSON 以及本工具格式。若源配置超过 8 段，会自动拟合为设备的 8 段并显示拟合误差。

**Q：为什么导入 10 段配置后频点和原来不一样？**
设备只接受 8 段，所以程序会用最小二乘把 10 段目标曲线拟合为 8 段最接近的近似。导入后弹出的提示会给出 RMS 拟合误差，通常在 1 dB 以内。

**Q：调完 EQ 后声音变小/变闷了？**
可能是增益叠加导致削波。点「增益补偿」按钮，程序会按当前曲线的峰值增益自动设置整体偏移。注意整体偏移下限是 −8 dB，若某段增益过高会提示无法完全补偿。

**Q：旁通按钮怎么用？**
点击「旁通」把 EQ 临时置为平直，再点一次恢复。也可以**按住空格键**临时旁通、松开即恢复（焦点在按钮上时空格会触发按钮，不会误触旁通）。

**Q：为什么滤波器类型默认只有「峰值」？**
因为官方 App 从未向设备发送过其他类型（详见上文说明），硬件是否支持低架/高架未经验证。该功能需手动开启并确认风险提示。

**Q：会不会刷坏我的设备固件？**
不会。软件只会按你的操作读写设备的可配置参数（音量、EQ、滤波档位等），不会刷写固件；所有写入操作都需要你主动点击保存。

**Q：云姬电脑版和手机 App 的调音效果一致吗？**
一致。本项目复刻了设备端的 8 段双二阶滤波器计算方式（固定 96 kHz 基准采样率、Q30 定点量化），并已在真机上完成读写与提交验证，参数与手机端表现相同。

**Q：可以在 Linux / macOS 上用吗？**
协议层与 UI 均为 Python 实现，理论上可移植，但目前仅在 Windows 10 / 11 上完成测试与打包。欢迎社区提交跨平台适配 PR。

---

## ⚠️ 免责声明 (Disclaimer)

1. 本项目为个人爱好者的开源移植与研究成果，**与「云姬」、「旋润」、「TTGK」或任何关联音频硬件制造商官方无商业合作或授权关系**。
2. 文档与界面中出现的品牌名称与设备型号仅用于客观标示硬件兼容范围，其商标与知识产权归原合法权利人所有。
3. 软件按 MIT 许可证「按现状 (AS-IS)」提供。开发者对使用本工具调节设备可能带来的任何硬件异常不承担担保责任。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源。
