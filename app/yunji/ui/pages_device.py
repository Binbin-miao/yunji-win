# -*- coding: utf-8 -*-
"""设备相关页面：设备列表 / 旋润设置页 / TTGK 设置页 / 滤波器页"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..config import (
    CHIP_CB1200,
    FILTER_MODE_NAMES,
    S,
    TTGK_DAC_VOL_OFFSET,
    TTGK_DAC_VOL_RESOLUTION,
    TTGK_MAX_DAC_VOL,
    TTGK_MIN_DAC_VOL,
    VENDER_ID_TTGK,
    VENDER_ID_XUAN_RUN,
)
from ..usb.scanner import brand_of
from .common import Toolbar, device_icon_pixmap, load_pixmap, setting_icon
from .theme import C_SECONDARY_BG
from .widgets import card_frame, make_divider, make_row, show_toast


# ============================================================ 设备列表
class DeviceRow(QWidget):
    def __init__(self, entry, parent_page: "DeviceListPage"):
        super().__init__()
        self.entry = entry
        self.page = parent_page
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(device_icon_pixmap(entry.icon, 56))
        icon.setFixedSize(60, 60)
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)
        info = QVBoxLayout()
        info.setSpacing(2)
        name = QLabel(entry.display_name)
        name.setObjectName("title")
        info.addWidget(name)
        status = QLabel(S["device_status_connected"] if entry.connected else S["device_status_unconnected"])
        status.setObjectName("statusLinked" if entry.connected else "statusUnlink")
        info.addWidget(status)
        lay.addLayout(info, 1)
        if parent_page.edit_mode:
            dele = QPushButton(S["text_delete"])
            dele.setFixedWidth(64)
            dele.clicked.connect(lambda: parent_page.delete_entry(entry))
            lay.addWidget(dele)
        elif entry.connected:
            chevron = QLabel("›")
            chevron.setStyleSheet("font-size:22px; color:#999;")
            lay.addWidget(chevron)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.page.click_entry(self.entry)


class DeviceListPage(QWidget):
    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        self.edit_mode = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.toolbar = Toolbar(S["title_device_list"], None)
        self.toolbar.add_right_button("≡", self._show_menu)
        root.addWidget(self.toolbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.host = QWidget()
        self.host.setObjectName("listHost")
        self.vbox = QVBoxLayout(self.host)
        self.vbox.setContentsMargins(12, 12, 12, 12)
        self.vbox.setSpacing(8)
        self.scroll.setWidget(self.host)
        root.addWidget(self.scroll, 1)
        self.empty = QLabel(S["device_empty_list"])
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet("color:#777; font-size:14px;")
        self.vbox.addWidget(self.empty)
        self.vbox.addStretch(1)
        self.menu = QMenu(self)
        self.menu.addAction(S["title_about"], self.ctrl.show_about)
        self.menu.addAction(S["title_edit"], self._toggle_edit)
        self.menu.addSeparator()
        self._sim_action = self.menu.addAction("模拟设备模式", self._toggle_sim)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1500)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start()
        self.refresh()

    def _show_menu(self):
        self.menu.popup(self.mapToGlobal(self.toolbar.rect().topRight()))

    def _toggle_edit(self):
        self.edit_mode = not self.edit_mode
        self.refresh()
        if self.edit_mode:
            show_toast(self, "删除模式下点击设备条目可移除历史记录")

    def _toggle_sim(self):
        self.ctrl.use_simulator = not self.ctrl.use_simulator
        self._sim_action.setChecked(self.ctrl.use_simulator)
        show_toast(self, "模拟设备模式：" + ("开" if self.ctrl.use_simulator else "关"))
        self.refresh()

    def refresh(self):
        # 清空（保留 empty 与 stretch）；先隐藏再延迟删除，避免刷新瞬间的渲染残留
        while self.vbox.count() > 2:
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.deleteLater()
        entries = self.ctrl.scan()
        if self.ctrl.use_simulator:
            entries += self.ctrl.simulated_entries()
        visible = [e for e in entries if e.connected or (self.edit_mode and not e.connected) or not self.edit_mode]
        shown = 0
        for e in entries:
            # 未连接设备始终显示（与原版一致：历史设备保留在列表中）
            row = DeviceRow(e, self)
            frame = card_frame()
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(0, 0, 0, 0)
            fl.addWidget(row)
            self.vbox.insertWidget(shown, frame)
            shown += 1
        self.empty.setVisible(shown == 0)

    def click_entry(self, entry):
        if self.edit_mode:
            if not entry.connected:
                self.ctrl.forget_device(entry)
                self.refresh()
            else:
                show_toast(self, "已连接的设备无法删除")
            return
        if not entry.connected:
            show_toast(self, S["toast_unlink"])
            return
        self.ctrl.open_device(entry)

    def delete_entry(self, entry):
        if not entry.connected:
            self.ctrl.forget_device(entry)
            self.refresh()


# ============================================================ 公共行组件
class SliderRow(QWidget):
    """滑块行：标签 + [-] 值 [+] + 滑块"""

    def __init__(self, label: str, icon: str = "", minimum=0, maximum=100,
                 initial=0, on_commit=None, value_fmt=str):
        super().__init__()
        self.minimum, self.maximum = minimum, maximum
        self.on_commit = on_commit
        self.value_fmt = value_fmt
        self._suppress = False
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(4)
        head = QHBoxLayout()
        if icon:
            ic = QLabel()
            ic.setPixmap(load_pixmap(icon).scaled(20, 20, Qt.KeepAspectRatio,
                                                  Qt.SmoothTransformation))
            head.addWidget(ic)
        lab = QLabel(label)
        lab.setObjectName("rowLabel")
        head.addWidget(lab)
        head.addStretch(1)
        self.minus = QPushButton("−")
        self.minus.setFixedSize(30, 30)
        self.value_label = QLabel()
        self.value_label.setObjectName("rowValue")
        self.value_label.setMinimumWidth(56)
        self.value_label.setAlignment(Qt.AlignCenter)
        self.plus = QPushButton("+")
        self.plus.setFixedSize(30, 30)
        head.addWidget(self.minus)
        head.addWidget(self.value_label)
        head.addWidget(self.plus)
        root.addLayout(head)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(initial)
        root.addWidget(self.slider)
        self.slider.valueChanged.connect(self._on_changed)
        self.slider.sliderReleased.connect(self._commit)
        self.minus.clicked.connect(lambda: self._step(-1, commit=True))
        self.plus.clicked.connect(lambda: self._step(1, commit=True))
        self._update_label()

    def _on_changed(self, _v):
        self._update_label()

    def _commit(self):
        if self.on_commit and not self._suppress:
            self.on_commit(self.slider.value())

    def _step(self, delta, commit=True):
        v = max(self.minimum, min(self.maximum, self.slider.value() + delta))
        self.slider.setValue(v)
        if commit and self.on_commit and not self._suppress:
            self.on_commit(v)

    def set_value(self, v: int):
        self._suppress = True
        self.slider.setValue(int(v))
        self._update_label()
        self._suppress = False

    def value(self) -> int:
        return self.slider.value()

    def _update_label(self):
        self.value_label.setText(self.value_fmt(self.slider.value()))

    def set_enabled(self, on: bool):
        self.slider.setEnabled(on)
        self.minus.setEnabled(on)
        self.plus.setEnabled(on)


class SwitchRow(QWidget):
    """开关行：标签 + 状态文字 + 开关"""

    def __init__(self, label: str, icon: str = "", on_text="开", off_text="关",
                 on_changed=None):
        super().__init__()
        self.on_changed = on_changed
        self.on_text, self.off_text = on_text, off_text
        self._suppress = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        if icon:
            ic = QLabel()
            ic.setPixmap(load_pixmap(icon).scaled(20, 20, Qt.KeepAspectRatio,
                                                  Qt.SmoothTransformation))
            lay.addWidget(ic)
        lab = QLabel(label)
        lab.setObjectName("rowLabel")
        lay.addWidget(lab)
        lay.addStretch(1)
        self.state_label = QLabel(on_text)
        self.state_label.setObjectName("rowValue")
        lay.addWidget(self.state_label)
        self.check = QCheckBox()
        lay.addWidget(self.check)
        self.check.toggled.connect(self._on_toggle)
        self._update_text(False)

    def _on_toggle(self, checked: bool):
        self._update_text(checked)
        if self.on_changed and not self._suppress:
            self.on_changed(checked)

    def _update_text(self, checked: bool):
        if checked is not None:
            self.state_label.setText(self.on_text if checked else self.off_text)

    def set_checked(self, checked: bool):
        self._suppress = True
        self.check.setChecked(bool(checked))
        self.state_label.setText(self.on_text if checked else self.off_text)
        self._suppress = False


# ============================================================ 旋润设置页
class XuanRunPage(QWidget):
    def __init__(self, ctrl, session):
        super().__init__()
        self.ctrl = ctrl
        self.session = session
        self.entry = session.entry
        self.xr = session.xr
        self.vol_now = 20
        self.balance_now = 18

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.toolbar = Toolbar(self.entry.display_name, self.ctrl.go_back)
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

        # 设备信息卡
        card = card_frame()
        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        ic = QLabel()
        ic.setPixmap(device_icon_pixmap(self.entry.icon, 48))
        cl.addWidget(ic)
        nl = QVBoxLayout()
        nl.setSpacing(2)
        nm = QLabel(self.entry.display_name)
        nm.setObjectName("title")
        nl.addWidget(nm)
        self.conn_label = QLabel(S["device_status_connected"])
        self.conn_label.setObjectName("statusLinked")
        nl.addWidget(self.conn_label)
        cl.addLayout(nl, 1)
        v.addWidget(card)

        # 音量
        card2 = card_frame()
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(0, 0, 0, 0)
        self.vol_row = SliderRow(S["main_setting_vol"], "icons/ic_setting_vol.png",
                                 0, 60, 20, on_commit=self._on_vol)
        self.vol_row.value_fmt = lambda v: str(v)
        c2.addWidget(self.vol_row)
        c2.addWidget(make_divider())
        self.bal_row = SliderRow(S["main_setting_balance"], "icons/ic_setting_balance.png",
                                 0, 36, 18, on_commit=self._on_balance)
        self.bal_row.value_fmt = self._bal_text
        c2.addWidget(self.bal_row)
        v.addWidget(card2)

        # 开关
        card3 = card_frame()
        c3 = QVBoxLayout(card3)
        c3.setContentsMargins(0, 0, 0, 0)
        self.gain_row = SwitchRow(S["main_setting_elelevel"], "icons/ic_setting_level.png",
                                  on_text=S["main_setting_sw_high"], off_text=S["main_setting_sw_low"],
                                  on_changed=self._on_gain)
        c3.addWidget(self.gain_row)
        c3.addWidget(make_divider())
        self.led_row = SwitchRow(S["main_setting_led"], "icons/ic_setting_led.png",
                                 on_changed=self._on_led)
        c3.addWidget(self.led_row)
        c3.addWidget(make_divider())
        self.depop_row = SwitchRow(S["main_setting_depop"], "icons/ic_setting_filter.png",
                                   on_changed=self._on_depop)
        c3.addWidget(self.depop_row)
        v.addWidget(card3)

        # 固件 + 高级
        card4 = card_frame()
        c4 = QVBoxLayout(card4)
        c4.setContentsMargins(0, 0, 0, 0)
        self.firm_value = QLabel("Rev. -")
        fw = make_row(S["main_setting_firmware"], QWidget(), self.firm_value)
        c4.addWidget(fw)
        c4.addWidget(make_divider())
        self.more_btn = QPushButton(S["main_setting_more"] + " ›")
        self.more_btn.setObjectName("bigAction")
        self.more_btn.clicked.connect(self._open_filter)
        c4.addWidget(self.more_btn)
        v.addWidget(card4)
        v.addStretch(1)

        self._sync_enabled(False)
        QTimer.singleShot(50, self.load)

    # ---- 数据加载 ----
    def load(self):
        self.ctrl.run_async(self._read_all, self._apply, self._load_err)

    def _read_all(self):
        firm = self.xr.read_firmware()
        vol_idx, l, r = self.xr.read_vol_balance()
        filt, elevel, led, depop = self.xr.read_status()
        return {"firm": firm, "vol": vol_idx, "l": l, "r": r,
                "filter": filt, "elevel": elevel, "led": led, "depop": depop}

    def _apply(self, d):
        self._sync_enabled(True)
        self.firm_value.setText("Rev. " + str(d["firm"]))
        self.vol_now = d["vol"]
        self.vol_row.set_value(d["vol"])
        # 平衡：由 L/R 码反查滑块（对照原版逻辑）
        bal = 18
        if d["l"] == 0 and d["r"] == 0:
            bal = 18
        elif d["l"] > 0:
            from ..config import XUANRUN_BALANCE_VALUE_L
            for i, v in enumerate(XUANRUN_BALANCE_VALUE_L):
                if v == d["l"]:
                    bal = i
        elif d["r"] > 0:
            from ..config import XUANRUN_BALANCE_VALUE_R
            for i, v in enumerate(XUANRUN_BALANCE_VALUE_R):
                if v == d["r"]:
                    bal = i
        self.balance_now = bal
        self.bal_row.set_value(bal)
        self.gain_row.set_checked(d["elevel"] == 1)
        self.led_row.set_checked(d["led"] == 0)
        self.depop_row.set_checked(d["depop"] == 0)
        self.session.sp = d
        # 持久化（对照 Android SharedPreferences "DEVICE_SETTING"）
        self.ctrl.state.set_device_settings(self.entry.name, self.entry.pid, {
            "filter": d["filter"], "eleLevel": d["elevel"], "volNow": d["vol"],
            "balanceNow": bal, "led": d["led"], "depop": d["depop"],
            "firm": str(d["firm"]),
        })

    def _load_err(self, msg):
        show_toast(self, S["toast_empty_device"])
        self.conn_label.setText(S["device_status_unconnected"])
        self.conn_label.setObjectName("statusUnlink")
        self.conn_label.setStyleSheet("color:#333;")
        self._sync_enabled(False)

    def _sync_enabled(self, on: bool):
        for w in (self.vol_row, self.bal_row, self.gain_row, self.led_row,
                  self.depop_row, self.more_btn):
            w.setEnabled(on)

    # ---- 操作 ----
    def _wrap(self, fn, ok_text=None):
        def u(msg):
            show_toast(self, "操作失败: " + msg)
        self.ctrl.run_async(fn, (lambda _r: show_toast(self, ok_text)) if ok_text else None, u)

    def _on_vol(self, v: int):
        self.vol_now = v
        self._wrap(lambda: self.xr.set_volume_index(v))

    def _on_balance(self, v: int):
        self.balance_now = v
        self._wrap(lambda: self.xr.set_balance_index(v))

    def _on_gain(self, on: bool):
        self._wrap(lambda: self.xr.set_ele_level(1 if on else 0))

    def _on_led(self, on: bool):
        self._wrap(lambda: self.xr.set_led(on))

    def _on_depop(self, on: bool):
        self._wrap(lambda: self.xr.set_depop(on))

    def _open_filter(self):
        self.ctrl.open_filter_page(self.session)

    def _bal_text(self, v: int) -> str:
        if v < 18:
            return f"L{18 - v}"
        if v > 18:
            return f"R{v - 18}"
        return "0"


# ============================================================ TTGK 设置页
class TtgkPage(QWidget):
    def __init__(self, ctrl, session):
        super().__init__()
        self.ctrl = ctrl
        self.session = session
        self.entry = session.entry
        self.tk = session.tk
        self.chip = entry_chip = session.chip_type
        self.vol_min = TTGK_MIN_DAC_VOL.get(entry_chip, -60)
        self.vol_max = TTGK_MAX_DAC_VOL.get(entry_chip, 0)
        self.vol_res = TTGK_DAC_VOL_RESOLUTION.get(entry_chip, 1)
        self.vol_offset = TTGK_DAC_VOL_OFFSET.get(entry_chip, 60)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.toolbar = Toolbar(self.entry.display_name, self.ctrl.go_back)
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
        card = card_frame()
        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        ic = QLabel()
        ic.setPixmap(device_icon_pixmap(self.entry.icon, 48))
        cl.addWidget(ic)
        nl = QVBoxLayout()
        nl.setSpacing(2)
        nm = QLabel(self.entry.display_name)
        nm.setObjectName("title")
        nl.addWidget(nm)
        self.conn_label = QLabel(S["device_status_connected"])
        self.conn_label.setObjectName("statusLinked")
        nl.addWidget(self.conn_label)
        cl.addLayout(nl, 1)
        v.addWidget(card)

        # 音量 + 麦克风 + （cb5100: 平衡/增益/LED）
        card2 = card_frame()
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(0, 0, 0, 0)
        vol_max_slider = (self.vol_max - self.vol_min) // self.vol_res
        self.vol_row = SliderRow(S["main_setting_vol_gain"], "icons/ic_setting_vol.png",
                                 0, vol_max_slider, 0, on_commit=self._on_vol)
        self.vol_row.value_fmt = self._vol_text
        c2.addWidget(self.vol_row)
        c2.addWidget(make_divider())
        self.mic_row = SliderRow(S["main_setting_mic_vol"], "icons/ic_setting_vol.png",
                                 0, 60, 30, on_commit=self._on_mic)
        self.mic_row.value_fmt = lambda v: f"+{v - 30}" if v - 30 > 0 else str(v - 30)
        c2.addWidget(self.mic_row)
        self.bal_row = None
        self.gain_row = None
        self.led_row = None
        if self.chip != CHIP_CB1200:
            c2.addWidget(make_divider())
            self.bal_row = SliderRow(S["main_setting_balance"], "icons/ic_setting_balance.png",
                                     0, 40, 20, on_commit=self._on_balance)
            self.bal_row.value_fmt = self._bal_text
            c2.addWidget(self.bal_row)
            c2.addWidget(make_divider())
            self.gain_row = SwitchRow(S["main_setting_elelevel"], "icons/ic_setting_level.png",
                                      on_text=S["main_setting_sw_high"],
                                      off_text=S["main_setting_sw_low"],
                                      on_changed=self._on_gain)
            c2.addWidget(self.gain_row)
            c2.addWidget(make_divider())
            self.led_row = SwitchRow(S["main_setting_led"], "icons/ic_setting_led.png",
                                     on_changed=self._on_led)
            c2.addWidget(self.led_row)
        v.addWidget(card2)

        # 固件
        card3 = card_frame()
        c3 = QVBoxLayout(card3)
        c3.setContentsMargins(0, 0, 0, 0)
        self.firm_value = QLabel("-")
        c3.addWidget(make_row(S["main_setting_firmware"], QWidget(), self.firm_value))
        v.addWidget(card3)

        # 高级：滤波器 / 金耳朵精调 / 大师专业调音
        card4 = card_frame()
        c4 = QVBoxLayout(card4)
        c4.setContentsMargins(0, 0, 0, 0)
        self.btn_filter = QPushButton(S["main_setting_filter"])
        self.btn_ezeq = QPushButton(S["main_setting_eq_ez"])
        self.btn_proeq = QPushButton(S["main_setting_eq_pro"])
        for b in (self.btn_filter, self.btn_ezeq, self.btn_proeq):
            b.setObjectName("bigAction")
            c4.addWidget(b)
            c4.addWidget(make_divider())
        self.btn_filter.clicked.connect(lambda: self.ctrl.open_filter_page(self.session))
        self.btn_ezeq.clicked.connect(lambda: self.ctrl.open_ezeq_page(self.session))
        self.btn_proeq.clicked.connect(lambda: self.ctrl.open_proeq_page(self.session))
        more_lab = QLabel(S["main_setting_more"])
        more_lab.setObjectName("sectionTitle")
        c4.insertWidget(0, more_lab)
        v.addWidget(card4)
        v.addStretch(1)

        self._sync_enabled(False)
        QTimer.singleShot(50, self.load)

    # ---- 加载 ----
    def load(self):
        self.ctrl.run_async(self._read_all, self._apply, self._load_err)

    def _read_all(self):
        d = {}
        d["firm"] = self.tk.read_firmware()
        d["vol"] = self.tk.read_vol()
        d["mic"] = self.tk.read_mic()
        if self.chip != CHIP_CB1200:
            d["bal"] = self.tk.read_balance()
            d["gain"] = self.tk.read_gain()
            d["led"] = self.tk.read_led()
        return d

    def _apply(self, d):
        self._sync_enabled(True)
        self.firm_value.setText(d["firm"] or "-")
        self.vol_row.set_value((d["vol"] - self.vol_min) // self.vol_res)
        self.mic_row.set_value(max(0, min(60, d["mic"] + 30)))
        if self.bal_row is not None:
            self.bal_row.set_value(max(0, min(40, d["bal"] + 20)))
            self.gain_row.set_checked(d["gain"] == 1)
            self.led_row.set_checked(d["led"] != 0)
        # 持久化（对照 Android SharedPreferences "DEVICE_SETTING"）
        cfg = {"volNow": d["vol"], "micVolNow": d["mic"], "firm": str(d["firm"])}
        if self.bal_row is not None:
            cfg.update({"balanceNow": d["bal"], "gainLevel": d["gain"], "led": d["led"]})
        self.ctrl.state.set_device_settings(self.entry.name, self.entry.pid, cfg)

    def _load_err(self, msg):
        show_toast(self, S["toast_empty_device"])
        self.conn_label.setText(S["device_status_unconnected"])
        self.conn_label.setStyleSheet("color:#333;")
        self._sync_enabled(False)

    def _sync_enabled(self, on: bool):
        ws = [self.vol_row, self.mic_row, self.btn_filter, self.btn_ezeq, self.btn_proeq]
        if self.bal_row:
            ws += [self.bal_row, self.gain_row, self.led_row]
        for w in ws:
            w.setEnabled(on)

    # ---- 操作 ----
    def _wrap(self, fn):
        self.ctrl.run_async(fn, None, lambda m: show_toast(self, "操作失败: " + m))

    def _vol_text(self, prog: int) -> str:
        val = prog * self.vol_res + self.vol_min
        shown = val + self.vol_offset
        return f"+{shown}" if shown > 0 else str(shown)

    def _on_vol(self, prog: int):
        val = prog * self.vol_res + self.vol_min
        self._wrap(lambda: self.tk.set_vol(val))

    def _on_mic(self, prog: int):
        self._wrap(lambda: self.tk.set_mic(prog - 30))

    def _bal_text(self, prog: int) -> str:
        v = prog - 20
        if v < 0:
            return f"L{abs(v)}"
        if v > 0:
            return f"R{v}"
        return "0"

    def _on_balance(self, prog: int):
        self._wrap(lambda: self.tk.set_balance(prog - 20))

    def _on_gain(self, on: bool):
        self._wrap(lambda: self.tk.set_gain(1 if on else 0))

    def _on_led(self, on: bool):
        self._wrap(lambda: self.tk.set_led(on))


# ============================================================ 滤波器页（共用）
class FilterPage(QWidget):
    def __init__(self, ctrl, session):
        super().__init__()
        self.ctrl = ctrl
        self.session = session
        self.entry = session.entry
        self.brand = session.brand
        self.current = -1

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.toolbar = Toolbar(S["main_setting_filter_mode"], self.ctrl.go_back)
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

        card = card_frame()
        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        ic = QLabel()
        ic.setPixmap(device_icon_pixmap(self.entry.icon, 44))
        cl.addWidget(ic)
        nl = QVBoxLayout()
        nl.setSpacing(2)
        nm = QLabel(self.entry.display_name)
        nm.setObjectName("title")
        nl.addWidget(nm)
        self.conn_label = QLabel(S["device_status_connected"])
        self.conn_label.setObjectName("statusLinked")
        nl.addWidget(self.conn_label)
        cl.addLayout(nl, 1)
        v.addWidget(card)

        self.rows = []
        card2 = card_frame()
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(0, 0, 0, 0)
        for i, name in enumerate(FILTER_MODE_NAMES):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 8, 12, 8)
            name_lab = QLabel(name)
            name_lab.setObjectName("rowLabel")
            rl.addWidget(name_lab)
            rl.addStretch(1)
            pic = QLabel()
            pm = load_pixmap(f"icons/pic_filter_mode{i + 1}.png")
            if not pm.isNull():
                pic.setPixmap(pm.scaledToWidth(90, Qt.SmoothTransformation))
            rl.addWidget(pic)
            status = QLabel()
            status.setFixedSize(26, 26)
            rl.addWidget(status)
            row.setCursor(Qt.PointingHandCursor)
            row.mouseReleaseEvent = (lambda _e, idx=i: self._select(idx))  # type: ignore
            self.rows.append((row, status))
            c2.addWidget(row)
            if i < len(FILTER_MODE_NAMES) - 1:
                c2.addWidget(make_divider())
        v.addWidget(card2)
        v.addStretch(1)
        QTimer.singleShot(50, self.load)

    def load(self):
        self.ctrl.run_async(self._read, self._apply,
                            lambda m: show_toast(self, S["toast_empty_device"]))

    def _read(self):
        if self.brand == "xuanrun":
            _f, _e, _l, _d = self.session.xr.read_status()
            return _f
        return self.session.tk.read_filter()

    def _apply(self, filt: int):
        self._update_marks(int(filt))

    def _update_marks(self, current: int):
        self.current = current
        for i, (row, status) in enumerate(self.rows):
            if i == current:
                status.setStyleSheet(
                    "border-radius:13px; background:#202020; border:2px solid #202020;")
            else:
                status.setStyleSheet(
                    "border-radius:13px; background:transparent; border:1px solid #202020;")

    def _select(self, idx: int):
        if idx == self.current:
            return

        def op():
            if self.brand == "xuanrun":
                self.session.xr.set_filter(idx)
            else:
                self.session.tk.set_filter(idx)
            return idx

        def ok(_r):
            self._update_marks(idx)
            show_toast(self, f"已切换滤波器：{FILTER_MODE_NAMES[idx]}")

        self.ctrl.run_async(op, ok, lambda m: show_toast(self, "设置失败: " + m))
