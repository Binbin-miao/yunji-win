# -*- coding: utf-8 -*-
"""设备扫描服务：把 USB 枚举从 GUI 线程移走

原实现里 `DeviceListPage` 每 1.5 秒、`MainWindow` 每 2 秒都在 GUI 线程直接
调用 `scanner.scan_devices()`，其中包含 `hid.enumerate()` 与 libusb 全量枚举，
会造成周期性界面卡顿。本模块把它收敛为「后台线程 + 单飞 + 结果缓存」。

GUI 线程只调用 `entries()` 读缓存，绝不触发枚举。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import List, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from . import scanner
from .base import DeviceEntry

log = logging.getLogger(__name__)


class _ScanSignals(QObject):
    done = Signal(list, str)   # entries, error


class _ScanTask(QRunnable):
    def __init__(self, signals: _ScanSignals):
        super().__init__()
        self.signals = signals

    def run(self):
        t0 = time.monotonic()
        try:
            entries = scanner.scan_devices(include_known=True)
            err = ""
        except Exception as e:  # noqa: BLE001
            log.warning("设备扫描失败: %s", e)
            entries, err = [], str(e)
        log.debug("扫描耗时 %.1f ms，发现 %d 个条目",
                  (time.monotonic() - t0) * 1000.0, len(entries))
        self.signals.done.emit(entries, err)


class ScanService(QObject):
    """后台扫描 + 结果缓存 + 单飞（同一时刻最多一个扫描任务）

    信号：
        updated(list)      扫描完成且成功
        failed(str)        扫描失败（枚举通道异常）
    """

    updated = Signal(list)
    failed = Signal(str)

    def __init__(self, interval_ms: int = 1500, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._entries: List[DeviceEntry] = []
        self._lock = threading.Lock()
        self._inflight = False
        self._last_error = ""

        self._signals = _ScanSignals()
        self._signals.done.connect(self._on_done)

        # 独立线程池：不与 AsyncRunner（设备 IO）抢线程
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.request)

    # ---------------- 对外 ----------------
    def entries(self) -> List[DeviceEntry]:
        """读缓存（非阻塞，GUI 线程安全）"""
        with self._lock:
            return list(self._entries)

    @property
    def last_error(self) -> str:
        return self._last_error

    def start(self) -> None:
        self._timer.start()
        self.request()

    def stop(self) -> None:
        self._timer.stop()

    def pause(self) -> None:
        """窗口最小化时暂停，省电"""
        self._timer.stop()

    def resume(self) -> None:
        self._timer.start()
        self.request()

    def set_interval(self, ms: int) -> None:
        """调整扫描间隔

        已打开设备页时应放慢扫描：频繁的 USB 枚举会与活跃会话争用设备，
        在部分设备/隔离器组合上会引发 LIBUSB_ERROR_NO_DEVICE。
        """
        if ms <= 0 or ms == self._timer.interval():
            return
        self._timer.setInterval(ms)

    def request(self) -> None:
        """请求一次扫描；若已有任务在跑则忽略，避免堆积"""
        if self._inflight:
            return
        self._inflight = True
        self._pool.start(_ScanTask(self._signals))

    def shutdown(self) -> None:
        self._timer.stop()
        self._pool.waitForDone(1500)

    # ---------------- 内部 ----------------
    def _on_done(self, entries, err: str):
        with self._lock:
            self._entries = list(entries)
        self._inflight = False
        self._last_error = err
        if err:
            self.failed.emit(err)
        else:
            self.updated.emit(list(entries))
