# -*- coding: utf-8 -*-
"""主窗口：页面导航、设备会话、热插拔监测、启动流程"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from ..config import APP_NAME_FULL, S, VENDER_ID_TTGK, VENDER_ID_XUAN_RUN, WINDOW_TITLE
from ..devices.ttgk import TtgkDevice
from ..devices.xuanrun import XuanRunDevice
from ..storage import AppState
from ..usb import scanner
from ..usb.base import BaseTransport, DeviceEntry, TransportError
from ..usb.simulator import SimulatedTransport
from .common import AsyncRunner
from .dialogs import ContentDialog
from .pages_device import DeviceListPage, FilterPage, TtgkPage, XuanRunPage
from .pages_eq import EzeqPage, ProEqPage
from .pages_misc import AboutPage, PolicyDialog
from .widgets import show_toast

APP_STYLE_INIT = None


class DeviceSession:
    """一次设备连接会话（传输层 + 协议对象）"""

    def __init__(self, entry: DeviceEntry, transport: BaseTransport):
        self.entry = entry
        self.transport = transport
        self.brand = scanner.brand_of(entry.vid)
        self.chip_type = entry.chip_type
        self.xr: Optional[XuanRunDevice] = None
        self.tk: Optional[TtgkDevice] = None
        if self.brand == "xuanrun":
            self.xr = XuanRunDevice(transport)
        else:
            self.tk = TtgkDevice(transport)
        self.sp = {}

    def close(self):
        try:
            self.transport.close()
        except Exception:
            pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(500, 840)
        self.setMinimumSize(420, 640)

        self.state = AppState()
        self.runner = AsyncRunner()
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.use_simulator = False
        self.pages: List[QWidget] = []
        self.session: Optional[DeviceSession] = None
        self._sim_session_seq = 0

        self.list_page = DeviceListPage(self)
        self._push(self.list_page)

        # 热插拔监测
        self._hotplug_timer = QTimer(self)
        self._hotplug_timer.setInterval(2000)
        self._hotplug_timer.timeout.connect(self._check_hotplug)
        self._hotplug_timer.start()

    # ================= 导航 =================
    def run_async(self, fn, on_ok=None, on_err=None):
        """页面通过控制器调用：在工作线程执行设备 IO"""
        return self.runner.run(fn, on_ok, on_err)

    def _push(self, page: QWidget):
        self.stack.addWidget(page)
        self.pages.append(page)
        self.stack.setCurrentWidget(page)

    def _pop(self):
        if len(self.pages) <= 1:
            return
        page = self.pages.pop()
        self.stack.removeWidget(page)
        page.deleteLater()
        self.stack.setCurrentWidget(self.pages[-1])
        if isinstance(self.pages[-1], DeviceListPage):
            self.pages[-1].refresh()

    def go_back(self):
        self._pop()

    # ================= 设备 =================
    def scan(self) -> List[DeviceEntry]:
        try:
            return scanner.scan_devices(include_known=True)
        except Exception:
            return []

    def simulated_entries(self) -> List[DeviceEntry]:
        return [
            DeviceEntry(vid=VENDER_ID_XUAN_RUN, pid=61693, name="模拟·YUNJI43198ULTRA",
                        icon="ic_dev_yj43198ultra", valid=True, connected=True,
                        additional_info=[1234], is_sim=True),
            DeviceEntry(vid=VENDER_ID_TTGK, pid=4687, name="模拟·Q25",
                        icon="ic_dev_q25", valid=True, connected=True,
                        additional_info=["cb1200"], is_sim=True),
            DeviceEntry(vid=VENDER_ID_TTGK, pid=17388, name="模拟·凌云剑",
                        icon="ic_dev_sky_reaching_sword", valid=True, connected=True,
                        additional_info=["cb5100"], is_sim=True),
        ]

    def forget_device(self, entry: DeviceEntry):
        self.state.forget_device(entry.name, entry.pid)

    def open_device(self, entry: DeviceEntry):
        if entry.is_sim:
            brand = scanner.brand_of(entry.vid)
            chip = entry.chip_type or "cb5100"
            transport = SimulatedTransport(brand=brand, chip_type=chip)
            session = DeviceSession(entry, transport)
            self.session = session
            self._open_brand_page(session)
            return

        def op():
            return scanner.open_transport(entry)

        def ok(transport):
            self.state.remember_device(entry.name, entry.pid, entry.vid)
            session = DeviceSession(entry, transport)
            self.session = session
            self._open_brand_page(session)

        def err(msg):
            self._show_open_error(entry, msg)

        show_toast(self, S["toast_linking"])
        self.runner.run(op, ok, err)

    def _open_brand_page(self, session: DeviceSession):
        if session.brand == "xuanrun":
            self._push(XuanRunPage(self, session))
        else:
            self._push(TtgkPage(self, session))

    def _show_open_error(self, entry: DeviceEntry, msg: str):
        if entry.vid == VENDER_ID_XUAN_RUN:
            text = (f"<p><b>无法打开设备：{entry.name}</b></p>"
                    "<p>旋润设备的调音通道需要安装 WinUSB 驱动（一次性操作）：</p>"
                    "<ol>"
                    "<li>下载 Zadig（zadig.akeo.ie）</li>"
                    "<li>插入设备，打开 Zadig 并勾选 Options → List All Devices</li>"
                    f"<li>在下拉框中选择 VID 为 {entry.vid} 的设备接口</li>"
                    "<li>目标驱动选择 <b>WinUSB</b>，点击 Install Driver</li>"
                    "<li>完成后回到本软件重新连接设备</li>"
                    "</ol>"
                    f"<p style='color:#999'>详细信息：{msg}</p>")
        else:
            text = (f"<p><b>无法打开设备：{entry.name}</b></p>"
                    f"<p>{msg}</p>"
                    "<p>请确认：</p><ul>"
                    "<li>设备已插入且未被其它调音软件占用</li>"
                    "<li>已在 Zadig 中为该设备的 HID 接口安装 WinUSB 驱动</li>"
                    "</ul>")
        ContentDialog(self, "连接失败", text).exec()

    def open_filter_page(self, session: DeviceSession):
        self._push(FilterPage(self, session))

    def open_proeq_page(self, session: DeviceSession):
        if session.tk is None:
            return
        self._push(ProEqPage(self, session))

    def open_ezeq_page(self, session: DeviceSession):
        if session.tk is None:
            return
        self._push(EzeqPage(self, session))

    def show_about(self):
        self._push(AboutPage(self))

    # ================= 热插拔 =================
    def _check_hotplug(self):
        session = self.session
        if session is None:
            return
        if session.entry.is_sim:
            return
        entries = self.scan()
        still = any(e.connected and e.vid == session.entry.vid
                    and e.pid == session.entry.pid for e in entries)
        if not still:
            self._close_session()
            # 关闭设备相关页面，回到列表
            while len(self.pages) > 1 and not isinstance(self.pages[-1], DeviceListPage):
                page = self.pages.pop()
                self.stack.removeWidget(page)
                page.deleteLater()
            self.stack.setCurrentWidget(self.list_page)
            self.list_page.refresh()
            show_toast(self, "设备已断开")

    def _close_session(self):
        if self.session is not None:
            self.session.close()
            self.session = None

    def closeEvent(self, event):  # noqa: N802
        self._close_session()
        super().closeEvent(event)

    # ================= 启动流程 =================
    def run_startup(self):
        # 1) 首启非官方开源声明确认
        if not self._policy_ok():
            dlg = PolicyDialog(self)
            dlg.exec()
            if dlg.agreed:
                self.state.notice.data.update({"agreed": True, "notice_version": 1})
                self.state.notice.save()
            else:
                QApplication.instance().quit()
                return

    def _policy_ok(self) -> bool:
        d = self.state.notice.data
        return bool(d.get("agreed")) and d.get("notice_version") == 1
