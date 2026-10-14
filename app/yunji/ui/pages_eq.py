# -*- coding: utf-8 -*-
"""EQ 编辑页：大师专业调音（ProEQ）/ 金耳朵精调（EZEQ）

对照 Android 版 ProEQHelper / EZEQHelper 的交互与上传时机：
- 数值改动（滑块释放 / 弹窗确认 / 模板 / 重置 / 预设加载）→ 刷新显示 → 保存本地 → 上传设备
- 音乐/游戏配置切换仅切换界面参数（不立即上传），与 Android 版一致

本版新增：
- 旁通 / A-B 对比（工具栏按钮 + 空格键按住临时旁通）
- 增益补偿（自动按峰值增益设置整体偏移，防削波）
- 多格式导入（Equalizer APO / GraphicEQ / Wavelet / 原生）+ 任意段数自动拟合到 8 段
- 目标曲线叠加与悬停读数（见 widgets.EQCurveWidget）
- 导出分享图
- 低架/高架滤波器（实验性，默认关闭）
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
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
    EQ_TYPE_HIGH_SHELF,
    EQ_TYPE_LOW_SHELF,
    EQ_TYPE_PEAKING,
    EXPERIMENTAL_SHELF_ENABLED,
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
from ..protocol import targets as target_mod
from ..protocol.eqdata import EQData, type_name
from ..protocol.eqformat import parse_eq_text
from ..protocol.fitting import fit_parsed
from ..protocol.templates import load_ezeq_config, load_ezeq_templates, load_help_text
from .common import Toolbar, device_icon_pixmap, setting_icon
from .dialogs import (
    ConfirmDialog,
    ContentDialog,
    HelpDialog,
    ImportExportDialog,
    NumberInputDialog,
    PresetDialog,
    TextInputDialog,
)
from .theme import C_SECONDARY_BG
from .widgets import EQCurveWidget, CircleValueButton, card_frame, make_divider, show_toast

log = logging.getLogger(__name__)

#: 滤波器类型循环顺序（实验性功能开启后可用）
_TYPE_CYCLE = [EQ_TYPE_PEAKING, EQ_TYPE_LOW_SHELF, EQ_TYPE_HIGH_SHELF]
_TYPE_SHORT = {EQ_TYPE_PEAKING: "峰", EQ_TYPE_LOW_SHELF: "低", EQ_TYPE_HIGH_SHELF: "高"}


def _fmt_freq(f: int) -> str:
    if f >= 1000:
        v = f / 1000.0
        s = f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{s}k"
    return str(f)


def _fmt_gain(g: float) -> str:
    return f"+{g:.1f}" if g > 0 else f"{g:.1f}"


def _normalize_band_freqs(freqs, lo: int = 20, hi: int = 20000):
    """把频点整理成严格递增且落在 [lo, hi] 内的整数序列

    设备要求 8 个频点单调递增（UI 的 _edit_freq 也是按此约束校验的）。
    导入少于 8 段的配置时，源频点与默认频点混在一起可能乱序甚至重复，
    直接下发会产生非法参数，故必须归一化。
    """
    n = len(freqs)
    if n == 0:
        return []
    fc = sorted(float(v) for v in freqs)

    for i in range(1, n):                       # 保证严格递增
        if fc[i] <= fc[i - 1]:
            fc[i] = fc[i - 1] + 1

    if fc[-1] > hi:                             # 越上界则整体回压
        shift = fc[-1] - hi
        fc = [v - shift for v in fc]
    if fc[0] < lo:                              # 越下界则整体上推
        shift = lo - fc[0]
        fc = [v + shift for v in fc]

    for i in range(1, n):                       # 回压后可能又产生冲突
        if fc[i] <= fc[i - 1]:
            fc[i] = fc[i - 1] + 1

    return [int(round(v)) for v in fc]




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

        # 旁通状态：None=未旁通；list=保存的增益快照
        self._bypass_snapshot: Optional[list] = None
        self._bypass_offset = 0
        self._bypass_hold = False
        self._shelf_enabled = bool(EXPERIMENTAL_SHELF_ENABLED)
        self._target_id = "__none__"
        self._last_fit_note = ""

        # 曲线重绘节流（拖动滑块时合并到 ~60fps）
        self._curve_pending = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.toolbar = Toolbar(S["main_setting_eq_pro"], self.ctrl.go_back)
        self.bypass_btn = self.toolbar.add_right_button(S["bypass_button"], self._toggle_bypass)
        self.bypass_btn.setToolTip(S["bypass_hint"])
        self.toolbar.add_right_button("导入", self._import)
        self.toolbar.add_right_button("导出", self._export)
        root.addWidget(self.toolbar)
        self.setFocusPolicy(Qt.StrongFocus)

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
        self.t_labels: List[QLabel] = []
        self.sliders: List[QSlider] = []
        for i in range(8):
            col = QVBoxLayout()
            col.setSpacing(6)
            t_lab = QLabel()
            t_lab.setAlignment(Qt.AlignCenter)
            t_lab.setCursor(Qt.PointingHandCursor)
            t_lab.setToolTip("点击切换滤波器类型（实验性功能）")
            t_lab.setStyleSheet("font-size:10px; color:#888;")
            t_lab.mouseReleaseEvent = lambda _e, idx=i: self._cycle_type(idx)  # type: ignore
            t_lab.setVisible(self._shelf_enabled)
            col.addWidget(t_lab)
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
            self.t_labels.append(t_lab)
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
        self.preamp_btn = QPushButton(S["preamp_button"])
        self.preamp_btn.setToolTip("按当前曲线的峰值增益自动设置整体偏移，避免削波")
        self.preamp_btn.clicked.connect(self._auto_preamp)
        off_row.addWidget(self.preamp_btn)
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

        # 曲线 + 目标曲线选择
        card2 = card_frame()
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(8, 8, 8, 8)
        trow = QHBoxLayout()
        t_lab2 = QLabel(S["target_label"])
        t_lab2.setObjectName("rowLabel")
        trow.addWidget(t_lab2)
        trow.addStretch(1)
        self.target_box = QComboBox()
        self.target_box.setMinimumWidth(200)
        self.target_box.addItem(S["target_none"], "__none__")
        for c in target_mod.list_targets():
            self.target_box.addItem(c.label, c.id)
        self.target_box.currentIndexChanged.connect(
            lambda _i: self._set_target(self.target_box.currentData()))
        trow.addWidget(self.target_box)
        c2.addLayout(trow)
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
        row2 = QHBoxLayout()
        self.btn_share = QPushButton(S["export_image_title"])
        self.btn_share.setObjectName("bigAction")
        self.btn_share.clicked.connect(self._export_image)
        self.btn_shelf = QPushButton("滤波器类型（实验性）")
        self.btn_shelf.setObjectName("bigAction")
        self.btn_shelf.clicked.connect(self._enable_shelf)
        row2.addWidget(self.btn_share)
        row2.addWidget(self.btn_shelf)
        c3.addLayout(row2)
        v.addWidget(card3)
        v.addStretch(1)

        self.refresh_display()
        self._sync_target_buttons()
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
            if self._shelf_enabled:
                self.t_labels[i].setText(_TYPE_SHORT.get(int(d.type_list[i]), "?"))
            self._suppress = True
            self.sliders[i].setValue(int(d.gain_list[i] * 10) + 120)
            self._suppress = False
        self._suppress = True
        self.offset_slider.setValue(int(d.offset) - TTGK_MIN_EQ_OFFSET)
        self.offset_value.setText(f"+{d.offset}" if d.offset > 0 else str(d.offset))
        self._suppress = False
        self._apply_target()
        self.curve.set_data(d)

    def _apply_target(self):
        """把当前选择的目标曲线挂到曲线上"""
        if self._target_id in ("", "__none__"):
            self.curve.set_target(None)
            return
        self.curve.set_target(target_mod.load_target(self._target_id))

    def _set_target(self, target_id: str):
        self._target_id = target_id
        self._sync_target_buttons()
        self._apply_target()

    def _sync_target_buttons(self):
        """把当前选择同步到下拉框（不触发信号）"""
        idx = self.target_box.findData(self._target_id)
        if idx < 0:
            idx = 0
        self.target_box.blockSignals(True)
        self.target_box.setCurrentIndex(idx)
        self.target_box.blockSignals(False)

    def _schedule_curve(self):
        """16ms 合并重绘，避免滑块每个像素都重算曲线"""
        if self._curve_pending:
            return
        self._curve_pending = True
        QTimer.singleShot(16, self._flush_curve)

    def _flush_curve(self):
        self._curve_pending = False
        self.curve.set_data(self.data)

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
        self._schedule_curve()

    def _commit_gain(self, idx: int):
        self._flush_curve()          # 松手立刻定格到最终值
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
            # upload_eq 返回是否完成「生效确认」；False 表示已写入但确认失败
            return self.tk.upload_eq(data)

        def ok(confirmed):
            if confirmed is False:
                show_toast(self, "EQ 已写入，但生效确认失败，请手动调整一次音量")

        self.ctrl.run_async(op, ok,
                            lambda m: show_toast(self, S["toast_eq_upload_failed"] + f" ({m})"))

    # ---------------- 旁通 / A-B 对比 ----------------
    def _toggle_bypass(self):
        if self._bypass_snapshot is None:
            self._enter_bypass()
        else:
            self._exit_bypass()

    def _enter_bypass(self):
        """保存当前增益并写入平直曲线"""
        if self._bypass_snapshot is not None:
            return
        self._bypass_snapshot = list(self.data.gain_list)
        self._bypass_offset = self.data.offset

        flat = self.data.deepcopy()
        flat.gain_list = [0.0] * len(flat.gain_list)
        flat.offset = 0

        def op():
            return self.tk.upload_eq(flat)

        self.ctrl.run_async(op, None,
                            lambda m: show_toast(self, "旁通失败：" + str(m)))
        self.bypass_btn.setText("已旁通")
        self.bypass_btn.setStyleSheet("color:#c53030; font-weight:bold;")
        # 界面同步显示平直曲线，避免与设备状态不符
        self.data.gain_list = [0.0] * 8
        self.data.offset = 0
        self.refresh_display()
        show_toast(self, S["bypass_on"])

    def _exit_bypass(self):
        """恢复旁通前的增益"""
        snapshot = self._bypass_snapshot
        if snapshot is None:
            return
        offset = getattr(self, "_bypass_offset", 0)
        self._bypass_snapshot = None

        self.data.gain_list = list(snapshot)
        self.data.offset = offset
        self.bypass_btn.setText(S["bypass_button"])
        self.bypass_btn.setStyleSheet("")
        self.refresh_display()
        self._save_ui()
        self._schedule_upload()
        show_toast(self, S["bypass_off"])

    # 空格键：按住临时旁通，松开恢复（焦点在按钮上时事件被按钮消费，不会误触发）
    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if self._bypass_snapshot is None:
                self._bypass_hold = True
                self._enter_bypass()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if self._bypass_hold:
                self._bypass_hold = False
                self._exit_bypass()
            event.accept()
            return
        super().keyReleaseEvent(event)

    # ---------------- 增益补偿（防削波）----------------
    def _auto_preamp(self):
        peak = self.data.peak_gain_db()
        if peak <= 0.05:
            ContentDialog(self, S["preamp_title"],
                          f"<p>{S['preamp_none_needed']}</p>"
                          f"<p style='color:#888'>峰值增益 {peak:+.1f} dB</p>").exec()
            return

        target = -int(round(peak))            # 向上取整为负
        target = max(TTGK_MIN_EQ_OFFSET, min(TTGK_MAX_EQ_OFFSET, target))

        if target > -peak + 0.05:
            # 下限不够，无法完全补偿
            html = (f"<p>{S['preamp_clamped'] % (peak, TTGK_MIN_EQ_OFFSET)}</p>"
                    f"<p style='color:#888'>已将整体偏移设为 {target} dB</p>")
            ContentDialog(self, S["preamp_title"], html).exec()
        else:
            show_toast(self, S["preamp_applied"] % (target, peak))

        self.data.offset = int(target)
        self._after_change()

    # ---------------- 滤波器类型（实验性）----------------
    def _enable_shelf(self):
        if self._shelf_enabled:
            self._shelf_enabled = False
            for lab in self.t_labels:
                lab.setVisible(False)
            self.btn_shelf.setText("滤波器类型（实验性）")
            show_toast(self, "已隐藏滤波器类型选择")
            return
        if not ConfirmDialog.ask(self, S["shelf_warning_title"], S["shelf_warning_body"]):
            return
        self._shelf_enabled = True
        for lab in self.t_labels:
            lab.setVisible(True)
        self.btn_shelf.setText("隐藏滤波器类型")
        self.refresh_display()
        show_toast(self, "已启用；官方从未使用过峰值以外的类型，请谨慎验证")

    def _cycle_type(self, idx: int):
        if not self._shelf_enabled:
            return
        cur = int(self.data.type_list[idx])
        try:
            nxt = _TYPE_CYCLE[(_TYPE_CYCLE.index(cur) + 1) % len(_TYPE_CYCLE)]
        except ValueError:
            nxt = EQ_TYPE_PEAKING
        self.data.type_list[idx] = nxt
        self._after_change()

    # ---------------- 导出分享图 ----------------
    def _export_image(self):
        from PySide6.QtWidgets import QFileDialog
        from .share_card import render_share_card

        default = f"YunjiEQ_{self.entry.display_name}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, S["export_image_title"], default, "PNG 图片 (*.png)")
        if not path:
            return
        try:
            target = target_mod.load_target(self._target_id) \
                if self._target_id not in ("", "__none__") else None
            pm = render_share_card(self.data, self.entry.display_name, target)
            if not pm.save(path, "PNG"):
                raise RuntimeError("保存失败")
            show_toast(self, S["export_image_saved"] % path)
        except Exception as e:  # noqa: BLE001
            log.exception("导出分享图失败")
            show_toast(self, S["export_image_failed"] % e)

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
        text = ImportExportDialog.ask_import(self, hint=S["import_hint"])
        if not text:
            return
        self.apply_import_text(text)

    def apply_import_text(self, text: str) -> bool:
        """解析并应用导入文本（与 UI 解耦，便于测试）

        返回是否成功。
        """
        try:
            parsed = parse_eq_text(text)
            if parsed.is_empty:
                show_toast(self, S["import_no_bands"])
                return False

            # 源就是 8 段以内的参数式配置 → 直接采用，不做拟合
            direct = (bool(parsed.bands) and not parsed.graphic
                      and len(parsed.bands) <= 8)
            if direct:
                # 以默认 8 段为骨架，把源段填进去后按频率排序，
                # 再归一化频点（设备要求严格递增）
                tuples = [
                    (float(PROEQ_DEFAULT_FREQ[i]), float(PROEQ_DEFAULT_Q[i]),
                     0.0, EQ_TYPE_PEAKING)
                    for i in range(8)
                ]
                for i, b in enumerate(sorted(parsed.bands, key=lambda x: x.freq)):
                    tuples[i] = (float(b.freq), float(b.q), float(b.gain), int(b.type))
                tuples.sort(key=lambda t: t[0])

                data = EQData()
                data.fc_list = _normalize_band_freqs([t[0] for t in tuples])
                data.q_list = [float(t[1]) for t in tuples]
                data.gain_list = [round(float(t[2]), 1) for t in tuples]
                data.type_list = [int(t[3]) for t in tuples]
                note = S["import_ok_exact"] % len(parsed.bands)
            else:
                result = fit_parsed(parsed)
                data = EQData()
                for i in range(8):
                    data.fc_list[i] = int(round(result.centers[i]))
                    data.q_list[i] = float(result.qs[i])
                    data.gain_list[i] = float(result.gains[i])
                    data.type_list[i] = int(result.types[i])
                note = S["import_ok"] % (result.source_bands, result.rms_error)
                if result.needs_fit:
                    log.info("源曲线 %d 段，已拟合为 8 段（RMS %.2f dB）",
                             result.source_bands, result.rms_error)

            if parsed.preamp is not None:
                pre = int(round(parsed.preamp))
                data.offset = max(TTGK_MIN_EQ_OFFSET,
                                  min(TTGK_MAX_EQ_OFFSET, pre))

            self.data = data
            self.refresh_display()
            self._save_ui()
            self._upload_now()
            show_toast(self, note)
            log.info("导入完成: 格式=%s 源段数=%s 直接采用=%s",
                     parsed.fmt, len(parsed.bands) or len(parsed.graphic), direct)
            return True
        except Exception as e:  # noqa: BLE001
            log.exception("导入失败")
            show_toast(self, S["import_failed"] % e)
            return False


    def _export(self):
        ImportExportDialog.get_text(
            self, "导出 EQ",
            json.dumps({"bands": [
                {"freq": int(self.data.fc_list[i]),
                 "q": float(self.data.q_list[i]),
                 "gain": round(float(self.data.gain_list[i]), 1),
                 "type": int(self.data.type_list[i])}
                for i in range(8)
            ], "offset": int(self.data.offset)}, ensure_ascii=False, indent=2))



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
