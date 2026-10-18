# -*- coding: utf-8 -*-
"""主窗口：页面导航、设备会话、热插拔监测、启动流程

性能要点（相对旧实现）：
- 设备扫描统一交给 ScanService（后台线程 + 缓存 + 单飞），
  GUI 线程不再做 USB 枚举；原先「列表页 1.5s 定时器 + 主窗口 2s 热插拔定时器」
  两个阻塞定时器合并为一个后台扫描服务。
- 每个设备会话持有独立的单线程执行器，保证 USB 事务不交错。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from PySide6.QtCore import QEvent, QThreadPool, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from ..config import APP_NAME_FULL, S, VENDER_ID_TTGK, VENDER_ID_XUAN_RUN, WINDOW_TITLE
from ..devices.ttgk import TtgkDevice
from ..devices.xuanrun import XuanRunDevice
from ..storage import get_app_state
from ..usb import scanner
from ..usb.base import BaseTransport, DeviceEntry, TransportError
from ..usb.scan_service import ScanService
from ..usb.simulator import SimulatedTransport
from .common import AsyncRunner
from .dialogs import ContentDialog
from .pages_device import DeviceListPage, FilterPage, TtgkPage, XuanRunPage
from .pages_eq import EzeqPage, ProEqPage
from .pages_misc import AboutPage, PolicyDialog
from .widgets import show_toast

log = logging.getLogger(__name__)

APP_STYLE_INIT = None

#: 判定「设备已断开」需要连续多少次扫描都看不到设备
#: 取 3 次（约 4.5s）以容忍 USB 枚举抖动，避免误销毁会话
DISCONNECT_CONFIRM_SCANS = 3

#: 扫描间隔：列表页 / 已打开设备页
SCAN_INTERVAL_LIST = 1500
SCAN_INTERVAL_SESSION = 5000


class DeviceSession:
    """一次设备连接会话（传输层 + 协议对象 + 串行执行器）"""

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
        # 单线程池：同一设备的 USB 事务严格串行，避免读写交错
        # （DeviceSession 非 QObject，故线程池不挂父对象，由 runner 持有引用）
        self.runner = AsyncRunner(QThreadPool())
        self.runner.pool.setMaxThreadCount(1)

    def close(self):
        try:
            self.runner.pool.waitForDone(2000)
        except Exception:
            pass
        try:
            self.transport.close()
        except Exception:
            log.debug("关闭传输层失败", exc_info=True)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(500, 840)
        self.setMinimumSize(420, 640)

        self.state = get_app_state()
        self.runner = AsyncRunner()          # 非设备任务（打开设备、更新检查等）
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.use_simulator = False
        self.pages: List[QWidget] = []
        self.session: Optional[DeviceSession] = None
        self._sim_session_seq = 0
        self._miss_count = 0

        # 后台扫描服务（取代原先两个阻塞定时器）—— 需先于列表页创建
        self.scan_service = ScanService(parent=self)

        self.list_page = DeviceListPage(self)
        self._push(self.list_page)

        self.scan_service.updated.connect(self._on_devices_updated)
        self.scan_service.failed.connect(self._on_scan_failed)
        self.scan_service.start()

    # ================= 导航 =================
    def run_async(self, fn, on_ok=None, on_err=None):
        """页面通过控制器调用：设备 IO 走会话串行队列，保证不交错"""
        runner = self.session.runner if self.session is not None else self.runner
        return runner.run(fn, on_ok, on_err)

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
            self.pages[-1].apply_entries(self.scan())

    def go_back(self):
        self._pop()

    # ================= 设备 =================
    def scan(self) -> List[DeviceEntry]:
        """读扫描缓存（非阻塞）"""
        return self.scan_service.entries()

    def request_scan(self):
        self.scan_service.request()

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
        self.request_scan()

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
        # 已进入设备页：放慢扫描，减少 USB 枚举对活跃会话的干扰
        self._miss_count = 0
        self.scan_service.set_interval(SCAN_INTERVAL_SESSION)
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

    # ================= 热插拔（由扫描信号驱动）=================
    def _on_devices_updated(self, entries: List[DeviceEntry]):
        if self.pages and isinstance(self.pages[-1], DeviceListPage):
            self.pages[-1].apply_entries(entries)
        self._check_hotplug(entries)

    def _on_scan_failed(self, msg: str):
        log.warning("扫描失败: %s", msg)
        if self.pages and isinstance(self.pages[-1], DeviceListPage):
            self.pages[-1].show_scan_error(msg)

    def _check_hotplug(self, entries: List[DeviceEntry]):
        """热插拔检测

        重要：必须连续多次扫描都看不到设备才判定断开。
        旧实现「一次没看到就销毁会话」会在 USB 枚举偶发抖动时（隔离器、集线器、
        WinUSB 打开瞬间）误判为拔出，随即 dispose 句柄，导致正在进行的
        控制传输报 LIBUSB_ERROR_NO_DEVICE —— 表现为「点进去就读取失败」。
        """
        session = self.session
        if session is None or session.entry.is_sim:
            self._miss_count = 0
            return

        still = any(e.connected and e.vid == session.entry.vid
                    and e.pid == session.entry.pid for e in entries)
        if still:
            self._miss_count = 0
            return

        self._miss_count += 1
        if self._miss_count < DISCONNECT_CONFIRM_SCANS:
            log.debug("扫描未发现设备（连续第 %d/%d 次），暂不判定断开",
                      self._miss_count, DISCONNECT_CONFIRM_SCANS)
            return

        log.info("连续 %d 次扫描未发现设备，判定已断开", self._miss_count)
        self._miss_count = 0
        self._close_session()
        while len(self.pages) > 1 and not isinstance(self.pages[-1], DeviceListPage):
            page = self.pages.pop()
            self.stack.removeWidget(page)
            page.deleteLater()
        self.stack.setCurrentWidget(self.list_page)
        self.list_page.apply_entries(entries)
        show_toast(self, "设备已断开")

    def _close_session(self):
        if self.session is not None:
            self.session.close()
            self.session = None
        self._miss_count = 0
        try:
            self.scan_service.set_interval(SCAN_INTERVAL_LIST)
        except Exception:
            pass

    # ================= 生命周期 =================
    def changeEvent(self, event):  # noqa: N802
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                self.scan_service.pause()
            else:
                self.scan_service.resume()
        super().changeEvent(event)

    def closeEvent(self, event):  # noqa: N802
        self._close_session()
        try:
            self.scan_service.shutdown()
        except Exception:
            pass
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
