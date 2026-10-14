# -*- coding: utf-8 -*-
"""UI 公共设施：异步任务、图标加载、工具栏"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from ..storage import resolve_asset
from .theme import C_MAIN_BG, C_MAIN_TEXT

_pix_cache = {}


def asset_path(rel: str):
    return resolve_asset(rel)


def load_pixmap(rel: str) -> QPixmap:
    if rel not in _pix_cache:
        p = resolve_asset(rel)
        pix = QPixmap(str(p))
        _pix_cache[rel] = pix
    return _pix_cache[rel]


def device_icon_pixmap(icon_name: str, size: int = 64) -> QPixmap:
    for ext in (".png", ".webp"):
        pm = load_pixmap(f"icons/{icon_name}{ext}")
        if not pm.isNull():
            return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    pm = load_pixmap("icons/ic_dev_null.png")
    return pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def setting_icon(rel: str, size: int = 22) -> QIcon:
    pm = load_pixmap(rel)
    if pm.isNull():
        return QIcon()
    return QIcon(pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))


class _TaskSignals(QObject):
    ok = Signal(object)
    err = Signal(str)


class _Task(QRunnable):
    def __init__(self, fn: Callable):
        super().__init__()
        self.fn = fn
        self.signals = _TaskSignals()

    def run(self):
        try:
            result = self.fn()
        except Exception as e:  # noqa: BLE001
            try:
                self.signals.err.emit(str(e) or e.__class__.__name__)
            except RuntimeError:
                pass
            return
        try:
            self.signals.ok.emit(result)
        except RuntimeError:
            pass


class AsyncRunner(QObject):
    """简化异步执行：fn 在工作线程运行，回调在主线程"""

    def __init__(self, pool: Optional[QThreadPool] = None):
        super().__init__()
        self.pool = pool or QThreadPool.globalInstance()
        self._keep = []

    def run(self, fn: Callable, on_ok: Optional[Callable] = None,
            on_err: Optional[Callable] = None):
        task = _Task(fn)
        self._keep.append(task)

        def cleanup():
            try:
                self._keep.remove(task)
            except ValueError:
                pass

        if on_ok:
            task.signals.ok.connect(lambda r: (on_ok(r), cleanup()))
        else:
            task.signals.ok.connect(lambda _r: cleanup())
        if on_err:
            task.signals.err.connect(lambda m: (on_err(m), cleanup()))
        else:
            task.signals.err.connect(lambda _m: cleanup())
        self.pool.start(task)
        return task


class Toolbar(QWidget):
    """顶部工具栏：返回箭头 + 标题 + 右侧按钮"""

    def __init__(self, title: str, back_handler: Optional[Callable] = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("toolbar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(2)
        self.back_btn = QPushButton("‹")
        self.back_btn.setObjectName("flat")
        f = self.back_btn.font()
        f.setPointSize(22)
        self.back_btn.setFont(f)
        self.back_btn.setFixedSize(44, 44)
        self.back_btn.setStyleSheet(f"color:{C_MAIN_TEXT};")
        if back_handler is None:
            self.back_btn.hide()
        else:
            self.back_btn.clicked.connect(back_handler)
        lay.addWidget(self.back_btn)
        self.title = QLabel(title)
        self.title.setObjectName("toolbarTitle")
        self.title.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.title, 1)
        self.right_box = QWidget()
        rb = QHBoxLayout(self.right_box)
        rb.setContentsMargins(0, 0, 0, 0)
        rb.setSpacing(2)
        lay.addWidget(self.right_box)
        self.setStyleSheet(f"QWidget#toolbar {{ background: {C_MAIN_BG}; }}")

    def add_right_button(self, text: str, handler: Callable) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("flat")
        b.setFixedHeight(36)
        b.clicked.connect(handler)
        self.right_box.layout().addWidget(b)
        return b

    def set_right_widget(self, w: QWidget):
        self.right_box.layout().addWidget(w)
