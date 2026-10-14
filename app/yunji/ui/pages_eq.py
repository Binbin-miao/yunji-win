# -*- coding: utf-8 -*-
"""EQ 编辑页：大师专业调音（ProEQ）/ 金耳朵精调（EZEQ）

对照 Android 版 ProEQHelper / EZEQHelper 的交互与上传时机：
- 数值改动（滑块释放 / 弹窗确认 / 模板 / 重置 / 预设加载）→ 刷新显示 → 保存本地 → 上传设备
- 音乐/游戏配置切换仅切换界面参数（不立即上传），与 Android 版一致
"""
from __future__ import annotations

import json
from typing import List, Optional

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..config import (
    EQ_MAX_PRESET_COUNT,
    PROEQ_DEFAULT_FREQ,
    PROEQ_DEFAULT_Q,
    PROEQ_DEFAULT_TYPE,
    S,
    TTGK_MAX_EQ_GAIN,
    TTGK_MAX_EQ_OFFSET,
    TTGK_MIN_EQ_GAIN,
    TTGK_MIN_EQ_OFFSET,
)
from ..presets import EzeqPresetStore, ProEqPresetStore
from ..protocol.eqdata import EQData
from ..protocol.templates import load_ezeq_config, load_ezeq_templates, load_help_text
from .common import Toolbar, device_icon_pixmap, setting_icon
from .dialogs import (
    ConfirmDialog,
    HelpDialog,
    ImportExportDialog,
    NumberInputDialog,
    PresetDialog,
    TextInputDialog,
)
from .theme import C_SECONDARY_BG
from .widgets import EQCurveWidget, CircleValueButton, card_frame, make_divider, show_toast


def _fmt_freq(f: int) -> str:
    if f >= 1000:
        v = f / 1000.0
        s = f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{s}k"
    return str(f)


def _fmt_gain(g: float) -> str:
    return f"+{g:.1f}" if g > 0 else f"{g:.1f}"


# ============================================================ ProEQ 页
class ProEqPage(QWidget):
    def __init__(self, ctrl, session):
        super().__init__()
        self.ctrl = ctrl
        self.session = session
        self.entry = session.entry
        self.tk = session.tk
        self.store = ProEqPresetStore(self.entry.vid, self.entry.pid)

        # 载入 UI 状态（无则默认值）
        self.data = EQData(fc_list=list(PROEQ_DEFAULT_FREQ),
                           q_list=list(PROEQ_DEFAULT_Q),
                           gain_list=[0.0] * 8,
                           type_list=[PROEQ_DEFAULT_TYPE] * 8)
        if self.store.ui:
            try:
                self.data = EQData.from_json_dict(self.store.ui.get("data", {}))
            except Exception:
                pass

        self._suppress = False
        self._upload_timer = QTimer(self)
        self._upload_timer.setSingleShot(True)
        self._upload_timer.setInterval(350)
        self._upload_timer.timeout.connect(self._upload_now)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.toolbar = Toolbar(S["main_setting_eq_pro"], self.ctrl.go_back)
        self.toolbar.add_right_button("导入", self._import)
        self.toolbar.add_right_button("导出", self._export)
        root.addWidget(self.toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        host.setObjectName("listHost")
        v = QVBoxLayout(host)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        # 设备信息
        card0 = card_frame()
        c0 = QHBoxLayout(card0)
        c0.setContentsMargins(12, 8, 12, 8)
        ic = QLabel()
        ic.setPixmap(device_icon_pixmap(self.entry.icon, 36))
        c0.addWidget(ic)
        nm = QLabel(self.entry.display_name)
        nm.setObjectName("title")
        c0.addWidget(nm)
        c0.addStretch(1)
        v.addWidget(card0)

        # 8 段编辑区
        card = card_frame()
        c = QVBoxLayout(card)
        c.setContentsMargins(8, 12, 8, 12)
        cols = QHBoxLayout()
        cols.setSpacing(4)
        self.q_labels: List[QLabel] = []
        self.f_labels: List[QLabel] = []
        self.g_labels: List[QLabel] = []
        self.sliders: List[QSlider] = []
        for i in range(8):
            col = QVBoxLayout()
            col.setSpacing(6)
            q_lab = QLabel()
            q_lab.setAlignment(Qt.AlignCenter)
            q_lab.setCursor(Qt.PointingHandCursor)
            q_lab.setToolTip("点击调整 Q 值")
            q_lab.mouseReleaseEvent = lambda _e, idx=i: self._edit_q(idx)  # type: ignore
            col.addWidget(q_lab)
            f_lab = QLabel()
            f_lab.setAlignment(Qt.AlignCenter)
            f_lab.setCursor(Qt.PointingHandCursor)
            f_lab.setToolTip("点击调整频率")
            f_lab.mouseReleaseEvent = lambda _e, idx=i: self._edit_freq(idx)  # type: ignore
            col.addWidget(f_lab)
            sld = QSlider(Qt.Vertical)
            sld.setRange(0, (TTGK_MAX_EQ_GAIN - TTGK_MIN_EQ_GAIN) * 10)
            sld.setFixedHeight(220)
            sld.setValue(120)
            sld.valueChanged.connect(lambda _v, idx=i: self._on_slider_move(idx))
            sld.sliderReleased.connect(lambda idx=i: self._commit_gain(idx))
            col.addWidget(sld, 0, Qt.AlignHCenter)
            g_lab = QLabel()
            g_lab.setAlignment(Qt.AlignCenter)
            g_lab.setCursor(Qt.PointingHandCursor)
            g_lab.setToolTip("点击输入增益")
            g_lab.mouseReleaseEvent = lambda _e, idx=i: self._edit_gain(idx)  # type: ignore
            col.addWidget(g_lab)
            cols.addLayout(col)
            self.q_labels.append(q_lab)
            self.f_labels.append(f_lab)
            self.g_labels.append(g_lab)
            self.sliders.append(sld)
        c.addLayout(cols)

        # 整体偏移
        c.addWidget(make_divider())
        off_row = QHBoxLayout()
        off_lab = QLabel(S["eq_offset_label"])
        off_lab.setObjectName("rowLabel")
        off_row.addWidget(off_lab)
        off_row.addStretch(1)
        self.offset_value = QLabel("0")
        self.offset_value.setObjectName("rowValue")
        off_row.addWidget(self.offset_value)
        c.addLayout(off_row)
        self.offset_slider = QSlider(Qt.Horizontal)
        self.offset_slider.setRange(0, TTGK_MAX_EQ_OFFSET - TTGK_MIN_EQ_OFFSET)
        self.offset_slider.setValue(-TTGK_MIN_EQ_OFFSET)
        self.offset_slider.valueChanged.connect(self._on_offset_move)
        self.offset_slider.sliderReleased.connect(self._commit_offset)
        c.addWidget(self.offset_slider)
        alert = QLabel(S["main_setting_vol_alert"])
        alert.setObjectName("hint")
        alert.setWordWrap(True)
        c.addWidget(alert)
        v.addWidget(card)

        # 曲线
        card2 = card_frame()
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(8, 8, 8, 8)
        self.curve = EQCurveWidget()
        self.curve.setFixedHeight(200)
        c2.addWidget(self.curve)
        v.addWidget(card2)

        # 操作按钮
        card3 = card_frame()
        c3 = QVBoxLayout(card3)
        c3.setContentsMargins(8, 8, 8, 8)
        self.btn_reset = QPushButton(S["eq_reset"])
        self.btn_reset.setObjectName("bigAction")
        self.btn_reset.clicked.connect(self._reset)
        c3.addWidget(self.btn_reset)
        row = QHBoxLayout()
        self.btn_save = QPushButton(S["eq_save_to_file"])
        self.btn_load = QPushButton(S["eq_load_from_file"])
        for b in (self.btn_save, self.btn_load):
            b.setObjectName("bigAction")
        self.btn_save.clicked.connect(self._save_preset)
        self.btn_load.clicked.connect(self._load_preset)
        row.addWidget(self.btn_save)
        row.addWidget(self.btn_load)
        c3.addLayout(row)
        v.addWidget(card3)
        v.addStretch(1)

        self.refresh_display()
        # 载入预设文件
        self._reload_store()

    def _reload_store(self):
        self.store = ProEqPresetStore(self.entry.vid, self.entry.pid)

    # ---------------- 显示 ----------------
    def refresh_display(self):
        d = self.data
        for i in range(8):
            self.q_labels[i].setText(self._fmt_q(d.q_list[i]))
            self.f_labels[i].setText(_fmt_freq(int(d.fc_list[i])))
            self.g_labels[i].setText(_fmt_gain(d.gain_list[i]))
            self._suppress = True
            self.sliders[i].setValue(int(d.gain_list[i] * 10) + 120)
            self._suppress = False
        self._suppress = True
        self.offset_slider.setValue(int(d.offset) - TTGK_MIN_EQ_OFFSET)
        self.offset_value.setText(f"+{d.offset}" if d.offset > 0 else str(d.offset))
        self._suppress = False
        self.curve.set_data(d)

    @staticmethod
    def _fmt_q(q: float) -> str:
        s = f"{q:.3f}".rstrip("0").rstrip(".")
        return s

    # ---------------- 滑块 ----------------
    def _on_slider_move(self, idx: int):
        if self._suppress:
            return
        gain = (self.sliders[idx].value() - 120) / 10.0
        self.data.gain_list[idx] = gain
        self.g_labels[idx].setText(_fmt_gain(gain))
        self.curve.set_data(self.data)

    def _commit_gain(self, idx: int):
        self._after_change()

    def _on_offset_move(self, prog: int):
        if self._suppress:
            return
        val = prog + TTGK_MIN_EQ_OFFSET
        self.offset_value.setText(f"+{val}" if val > 0 else str(val))

    def _commit_offset(self):
        self.data.offset = self.offset_slider.value() + TTGK_MIN_EQ_OFFSET
        self._after_change()

    # ---------------- 文本编辑 ----------------
    def _edit_q(self, idx: int):
        v = NumberInputDialog.ask(self, S["number_q_value"], 0.1, 20.0,
                                  self.data.q_list[idx], decimals=3)
        if v is None:
            return
        self.data.q_list[idx] = float(v)
        self._after_change()

    def _edit_freq(self, idx: int):
        low = 20 if idx == 0 else int(self.data.fc_list[idx - 1])
        high = 20000 if idx == 7 else int(self.data.fc_list[idx + 1])
        # 严格递增（与原版边界规则一致：中段全开区间）
        if idx == 0:
            minimum, maximum = low, high - 1
        elif idx == 7:
            minimum, maximum = low + 1, high
        else:
            minimum, maximum = low + 1, high - 1
        if minimum > maximum:
            show_toast(self, "相邻频点过近，无法调整")
            return
        v = NumberInputDialog.ask(self, S["number_frequncy_value"], minimum, maximum,
                                  self.data.fc_list[idx], decimals=0)
        if v is None:
            return
        self.data.fc_list[idx] = int(v)
        self._after_change()

    def _edit_gain(self, idx: int):
        v = NumberInputDialog.ask(self, S["number_gain_value"], TTGK_MIN_EQ_GAIN,
                                  TTGK_MAX_EQ_GAIN, self.data.gain_list[idx])
        if v is None:
            return
        self.data.gain_list[idx] = float(v)
        self._after_change()

    # ---------------- 变更流程 ----------------
    def _after_change(self):
        self.refresh_display()
        self._save_ui()
        self._schedule_upload()

    def _save_ui(self):
        self.store.ui = {"data": self.data.to_json_dict()}
        self.store.save_ui()

    def _schedule_upload(self):
        self._upload_timer.start()

    def _upload_now(self):
        data = self.data.deepcopy()

        def op():
            self.tk.upload_eq(data)
            return True

        self.ctrl.run_async(op, None,
                            lambda m: show_toast(self, S["toast_eq_upload_failed"] + f" ({m})"))

    # ---------------- 操作 ----------------
    def _reset(self):
        self.data.gain_list = [0.0] * 8
        self.data.offset = 0
        self._after_change()

    def _save_preset(self):
        self._reload_store()
        action = PresetDialog.open_dialog(self, "save", self.store.eq_list)
        if not action:
            return
        kind, slot = action
        if kind == "delete":
            self.store.delete(slot)
            return
        default_name = S["eq_new_preset_name"]
        if slot < len(self.store.eq_list) and self.store.eq_list[slot]:
            default_name = self.store.eq_list[slot].get("name") or default_name
        name = TextInputDialog.ask(self, S["eq_preset_name"], default_name)
        if name is None:
            return
        self.data.name = name
        self.store.add_preset(slot, self.data)
        show_toast(self, S["toast_saved"])

    def _load_preset(self):
        self._reload_store()
        action = PresetDialog.open_dialog(self, "load", self.store.eq_list)
        if not action:
            return
        kind, slot = action
        if kind == "delete":
            self.store.delete(slot)
            return
        if slot >= len(self.store.eq_list) or not self.store.eq_list[slot]:
            return
        d = self.store.eq_list[slot]
        name = d.get("name") or ""
        if not ConfirmDialog.ask(self, S["text_load"],
                                 S["eq_config_load_confirm"] % (slot + 1, name)):
            return
        self.data = EQData.from_json_dict(d)
        self.refresh_display()
        self._save_ui()
        self._upload_now()

    def _import(self):
        if not ConfirmDialog.ask(self, S["text_confirm"], S["eq_import_alert"]):
            return
        text = ImportExportDialog.ask_import(self)
        if not text:
            return
        try:
            raw = json.loads(text)
            bands = raw.get("bands")
            if not isinstance(bands, list) or not bands:
                raise ValueError("bad")
            data = EQData()
            for i, b in enumerate(bands[:8]):
                data.fc_list[i] = int(b.get("freq", data.fc_list[i]))
                data.q_list[i] = float(b.get("q", data.q_list[i]))
                data.gain_list[i] = float(b.get("gain", 0))
                data.type_list[i] = int(b.get("type", 2))
            self.data = data
            self.refresh_display()
            self._save_ui()
            self._upload_now()
            show_toast(self, "导入成功")
        except Exception:
            show_toast(self, S["toast_invalid_data"])

    def _export(self):
        bands = []
        for i in range(8):
            bands.append({
                "freq": int(self.data.fc_list[i]),
                "q": float(self.data.q_list[i]),
                "gain": round(float(self.data.gain_list[i]), 1),
                "type": int(self.data.type_list[i]),
            })
        ImportExportDialog.get_text(self, "导出 EQ", json.dumps({"bands": bands},
                                                                ensure_ascii=False))


# ============================================================ EZEQ 页
class EzeqPage(QWidget):
    def __init__(self, ctrl, session):
        super().__init__()
        self.ctrl = ctrl
        self.session = session
        self.entry = session.entry
        self.tk = session.tk
        self.chip = session.chip_type or "cb5100"
        self.store = EzeqPresetStore(self.entry.vid, self.entry.pid, self.chip)

        self.config_name = "music"
        self.data = EQData()
        self._load_ui_state()

        self._upload_timer = QTimer(self)
        self._upload_timer.setSingleShot(True)
        self._upload_timer.setInterval(350)
        self._upload_timer.timeout.connect(self._upload_now)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.toolbar = Toolbar(S["main_setting_eq_ez"], self.ctrl.go_back)
        self.toolbar.add_right_button("导入", self._import)
        self.toolbar.add_right_button("导出", self._export)
        root.addWidget(self.toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        host.setObjectName("listHost")
        v = QVBoxLayout(host)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        # 设备信息行
        card0 = card_frame()
        c0 = QHBoxLayout(card0)
        c0.setContentsMargins(12, 8, 12, 8)
        ic = QLabel()
        ic.setPixmap(device_icon_pixmap(self.entry.icon, 36))
        c0.addWidget(ic)
        nm = QLabel(self.entry.display_name)
        nm.setObjectName("title")
        c0.addWidget(nm)
        c0.addStretch(1)
        self.config_label = QLabel()
        self.config_label.setObjectName("hint")
        c0.addWidget(self.config_label)
        v.addWidget(card0)

        card = card_frame()
        body = QHBoxLayout(card)
        body.setContentsMargins(10, 14, 10, 14)
        body.setSpacing(12)

        # 8 个圆形按钮（2 列 x 4 行，与 Android 原版 GridLayout columnCount=2 一致）
        grid = QGridLayout()
        grid.setSpacing(10)
        self.buttons: List[CircleValueButton] = []
        for i in range(8):
            btn = CircleValueButton()
            btn.clicked.connect(lambda _=False, idx=i: self._edit_value(idx))
            btn.rightClicked.connect(lambda idx=i: self._reset_one(idx))
            btn.wheelEvent = (lambda e, idx=i, b=btn: self._wheel_value(idx, e, b))  # type: ignore
            grid.addWidget(btn, i // 2, i % 2)
            self.buttons.append(btn)
        body.addLayout(grid, 5)

        # 右列操作
        btns = QVBoxLayout()
        btns.setSpacing(10)
        self.btn_help = QPushButton(S["eq_help"])
        self.btn_music = QPushButton(S["eq_ez_music"])
        self.btn_game = QPushButton(S["eq_ez_game"])
        self.btn_reset = QPushButton(S["eq_ez_reset"])
        self.btn_random = QPushButton(S["eq_ez_random"])
        self.btn_save = QPushButton(S["eq_save_preset"])
        self.btn_load = QPushButton(S["eq_load_preset"])
        self.btn_help.clicked.connect(self._help)
        self.btn_music.clicked.connect(lambda: self._switch_config("music"))
        self.btn_game.clicked.connect(lambda: self._switch_config("game"))
        self.btn_reset.clicked.connect(self._reset)
        self.btn_random.clicked.connect(self._random)
        self.btn_save.clicked.connect(self._save_preset)
        self.btn_load.clicked.connect(self._load_preset)
        for b in (self.btn_help, self.btn_music, self.btn_game, self.btn_reset,
                  self.btn_random, self.btn_save, self.btn_load):
            b.setMinimumHeight(34)
            btns.addWidget(b)
        btns.addStretch(1)
        body.addLayout(btns, 2)
        v.addWidget(card)
        v.addStretch(1)

        self.refresh_display()
        self._reload_store()

    # ---------------- 数据状态 ----------------
    def _load_ui_state(self):
        ui = self.store.ui
        cfg_name = ui.get("selectingBasicConfig") or "music"
        self.config_name = cfg_name if cfg_name in ("music", "game") else "music"
        cfg = load_ezeq_config(self.config_name)
        self.data = EQData(fc_list=list(cfg.freqs), q_list=list(cfg.qs),
                           gain_list=[0.0] * 8)
        values = ui.get("ctrlButtonValues")
        if isinstance(values, list) and len(values) == 8:
            self.data.gain_list = [float(v) for v in values]

    def _save_ui(self):
        self.store.ui = {
            "selectingBasicConfig": self.config_name,
            "ctrlButtonValues": [round(float(v), 1) for v in self.data.gain_list],
        }
        self.store.save_ui()

    def _reload_store(self):
        self.store = EzeqPresetStore(self.entry.vid, self.entry.pid, self.chip)

    # ---------------- 显示 ----------------
    def refresh_display(self):
        cfg = load_ezeq_config(self.config_name)
        for i in range(8):
            self.buttons[i].set_notice(cfg.names[i])
            self.buttons[i].set_value(self.data.gain_list[i])
        mode_text = S["eq_ez_game"] if self.config_name == "game" else S["eq_ez_music"]
        self.config_label.setText(f"当前：{mode_text}")

    # ---------------- 编辑 ----------------
    def _edit_value(self, idx: int):
        title = S["number_gain_value"]
        v = NumberInputDialog.ask(self, title, TTGK_MIN_EQ_GAIN, TTGK_MAX_EQ_GAIN,
                                  self.data.gain_list[idx])
        if v is None:
            return
        self.data.gain_list[idx] = float(v)
        self._after_change()

    def _reset_one(self, idx: int):
        self.data.gain_list[idx] = 0.0
        self._after_change()

    def _wheel_value(self, idx: int, event, btn: CircleValueButton):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        step = 0.1 if abs(delta) < 240 else 1.0
        v = self.data.gain_list[idx] + (step if delta > 0 else -step)
        v = max(TTGK_MIN_EQ_GAIN, min(TTGK_MAX_EQ_GAIN, round(v, 1)))
        self.data.gain_list[idx] = v
        self._after_change()

    def _after_change(self):
        self.refresh_display()
        self._save_ui()
        self._upload_timer.start()

    def _upload_now(self):
        if self.session.tk is None:
            return
        data = self.data.deepcopy()

        def op():
            self.tk.upload_eq(data)
            return True

        self.ctrl.run_async(op, None,
                            lambda m: show_toast(self, S["toast_eq_upload_failed"] + f" ({m})"))

    # ---------------- 配置切换 ----------------
    def _switch_config(self, name: str):
        cfg = load_ezeq_config(name)
        self.config_name = name
        self.data.fc_list = list(cfg.freqs)
        self.data.q_list = list(cfg.qs)
        self.data.gain_list = [0.0] * 8   # 与原版一致：切换配置重置数值（不立即上传）
        self.refresh_display()
        self._save_ui()
        show_toast(self, f"已切换：{S['eq_ez_game'] if name == 'game' else S['eq_ez_music']}")

    def _reset(self):
        cfg = load_ezeq_config(self.config_name)
        self.data.fc_list = list(cfg.freqs)
        self.data.q_list = list(cfg.qs)
        self.data.gain_list = [0.0] * 8
        self.refresh_display()
        self._save_ui()
        self._upload_now()

    def _random(self):
        try:
            tpls = load_ezeq_templates(self.chip, self.config_name)
        except Exception as e:  # noqa: BLE001
            show_toast(self, "模板加载失败: " + str(e))
            return
        gains = tpls.random_gains()
        if gains is None:
            show_toast(self, "No Template Loaded")
            return
        self.data.gain_list = [float(g) for g in gains]
        self.refresh_display()
        self._save_ui()
        self._upload_now()

    def _help(self):
        try:
            data = load_help_text(self.config_name)
        except Exception as e:  # noqa: BLE001
            show_toast(self, "帮助加载失败: " + str(e))
            return
        HelpDialog(self, S["eq_help"], data).exec()

    # ---------------- 预设 ----------------
    def _save_preset(self):
        self._reload_store()
        action = PresetDialog.open_dialog(self, "save", self.store.presets)
        if not action:
            return
        kind, slot = action
        if kind == "delete":
            self.store.delete(slot)
            return
        default_name = S["eq_new_preset_name"]
        if slot < len(self.store.presets) and self.store.presets[slot]:
            default_name = self.store.presets[slot].get("presetName") or default_name
        name = TextInputDialog.ask(self, S["eq_preset_name"], default_name)
        if name is None:
            return
        self.store.add_preset(slot, name, self.config_name, self.data.gain_list)
        show_toast(self, S["toast_saved"])

    def _load_preset(self):
        self._reload_store()
        action = PresetDialog.open_dialog(self, "load", self.store.presets)
        if not action:
            return
        kind, slot = action
        if kind == "delete":
            self.store.delete(slot)
            return
        if slot >= len(self.store.presets) or not self.store.presets[slot]:
            return
        unit = self.store.presets[slot]
        name = unit.get("presetName") or ""
        if not ConfirmDialog.ask(self, S["text_load"],
                                 S["eq_config_load_confirm"] % (slot + 1, name)):
            return
        cfg_name = unit.get("configName") or "music"
        if cfg_name not in ("music", "game"):
            cfg_name = "music"
        cfg = load_ezeq_config(cfg_name)
        self.config_name = cfg_name
        self.data.fc_list = list(cfg.freqs)
        self.data.q_list = list(cfg.qs)
        values = unit.get("values") or [0.0] * 8
        self.data.gain_list = [float(v) for v in values[:8]]
        while len(self.data.gain_list) < 8:
            self.data.gain_list.append(0.0)
        self.refresh_display()
        self._save_ui()
        self._upload_now()

    # ---------------- 导入导出 ----------------
    def _import(self):
        if not ConfirmDialog.ask(self, S["text_confirm"], S["eq_import_alert"]):
            return
        text = ImportExportDialog.ask_import(self)
        if not text:
            return
        try:
            raw = json.loads(text)
            cfg_name = raw.get("configName") or "music"
            values = raw.get("values")
            if not isinstance(values, list):
                raise ValueError("bad")
            if cfg_name not in ("music", "game"):
                cfg_name = "music"
            cfg = load_ezeq_config(cfg_name)
            self.config_name = cfg_name
            self.data.fc_list = list(cfg.freqs)
            self.data.q_list = list(cfg.qs)
            gains = [float(v) for v in values[:8]]
            while len(gains) < 8:
                gains.append(0.0)
            self.data.gain_list = gains
            self.refresh_display()
            self._save_ui()
            self._upload_now()
            show_toast(self, "导入成功")
        except Exception:
            show_toast(self, S["toast_invalid_data"])

    def _export(self):
        data = {
            "configName": self.config_name,
            "values": [round(float(v), 1) for v in self.data.gain_list],
        }
        ImportExportDialog.get_text(self, "导出 EQ", json.dumps(data, ensure_ascii=False))
