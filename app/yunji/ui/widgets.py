# -*- coding: utf-8 -*-
"""自定义控件：
- EQCurveWidget   EQ 曲线图（对照 Android EQCurveView）
- CircleValueButton  EZEQ 圆形数值按钮（对照 ControlEZEQValueButton）
- Row 帮助函数：设置行 / 开关 / 滑块行
- Toast 轻提示
"""
from __future__ import annotations

import math
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..config import EQ_DISPLAY_SAMPLE_RATE
from ..protocol.eqdata import EQData
from .theme import (
    C_ACCENT,
    C_DIVIDER,
    C_HIGHLIGHT_TEXT,
    C_MAIN_ICON,
    C_SECONDARY_BG,
    C_SECONDARY_TEXT,
    toast_style,
)


# ---------------- EQ 曲线 ----------------
class EQCurveWidget(QWidget):
    """EQ 频响曲线（20Hz-20kHz 对数轴，-12..+12dB）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: Optional[EQData] = None
        self.setMinimumHeight(180)
        self.setAutoFillBackground(False)
        self._grid_pen = QPen(QColor("#bbbbbb"), 1)
        self._axis_pen = QPen(QColor("#888888"), 1)
        self._curve_pen = QPen(QColor("#ff00ff"), 3)
        self._text_pen = QPen(QColor("#888888"))

    def set_data(self, data: Optional[EQData]):
        self._data = data
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        # 背景
        p.fillRect(self.rect(), QColor(C_SECONDARY_BG))

        f_min, f_max = 20.0, 20000.0
        db_min, db_max = -12.0, 12.0

        def freq_to_x(freq: float) -> float:
            return (math.log10(freq) - math.log10(f_min)) / (
                math.log10(f_max) - math.log10(f_min)) * w

        def db_to_y(db: float) -> float:
            return h * (1 - (db - db_min) / (db_max - db_min))

        # 网格
        font = QFont(self.font())
        font.setPointSize(8)
        p.setFont(font)
        p.setPen(self._grid_pen)
        for db in (-12, -6, 0, 6, 12):
            y = db_to_y(db)
            p.drawLine(0, int(y), w, int(y))
            p.setPen(QPen(QColor("#888888")))
            p.drawText(4, int(y) - 4, f"{db} dB")
            p.setPen(self._grid_pen)
        for f in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
            x = freq_to_x(f)
            p.drawLine(int(x), 0, int(x), h)
            label = f"{f // 1000}k" if f >= 1000 else str(f)
            p.setPen(QPen(QColor("#888888")))
            p.drawText(int(x) - 14, h - 4, label)
            p.setPen(self._grid_pen)

        # 0dB 轴线
        p.setPen(self._axis_pen)
        p.drawLine(0, int(db_to_y(0)), w, int(db_to_y(0)))

        # 曲线
        if self._data is not None:
            p.setPen(self._curve_pen)
            path = QPainterPath()
            n = 300
            for i in range(n):
                freq = f_min * math.pow(10.0, (i / (n - 1.0)) * math.log10(f_max / f_min))
                try:
                    db = self._data.response_db(freq)
                except Exception:
                    db = 0.0
                x, y = freq_to_x(freq), db_to_y(db)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.drawPath(path)
        p.end()


# ---------------- 圆形数值按钮（EZEQ） ----------------
class CircleValueButton(QWidget):
    """圆形数值按钮：显示数值，单击 +，右键/双击输入；对应 Android ControlEZEQValueButton"""

    clicked = Signal()
    rightClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._notice = ""
        self.setFixedSize(96, 108)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("左键 +1 / 右键 -1 / 双击输入数值")

    def set_value(self, v: float):
        self._value = float(v)
        self.update()

    def value(self) -> float:
        return self._value

    def set_notice(self, text: str):
        self._notice = text
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        diameter = 76
        cx = self.width() / 2
        cy = diameter / 2 + 6
        # 圆底
        p.setBrush(QColor(0x30, 0x23, 0xFF, 0x30))
        p.setPen(QPen(QColor("#000000"), 3))
        p.drawEllipse(QRectF(cx - diameter / 2, cy - diameter / 2, diameter, diameter))
        # 数值
        f = QFont(self.font())
        f.setPointSize(17)
        p.setFont(f)
        p.setPen(QPen(QColor(C_HIGHLIGHT_TEXT)))
        txt = f"{self._value:+.1f}" if abs(self._value) > 1e-9 else "0.0"
        p.drawText(QRectF(0, cy - 18, self.width(), 36), Qt.AlignCenter, txt)
        # 名称
        f2 = QFont(self.font())
        f2.setPointSize(9)
        p.setFont(f2)
        p.setPen(QPen(QColor(C_SECONDARY_TEXT)))
        p.drawText(QRectF(0, diameter + 12, self.width(), 30),
                   Qt.AlignHCenter | Qt.AlignTop, self._notice)
        p.end()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            pass
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.RightButton:
            self.rightClicked.emit()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        self.rightClicked.emit()
        super().mouseDoubleClickEvent(event)


# ---------------- 常用行组件 ----------------
def card_frame() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f


def make_row(label: str, control: QWidget, value_label: Optional[QLabel] = None) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(12, 8, 12, 8)
    lab = QLabel(label)
    lab.setObjectName("rowLabel")
    lay.addWidget(lab)
    lay.addStretch(1)
    if value_label is not None:
        value_label.setObjectName("rowValue")
        value_label.setMinimumWidth(48)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(value_label)
    lay.addWidget(control)
    return row


def make_divider() -> QFrame:
    d = QFrame()
    d.setObjectName("hr")
    d.setFrameShape(QFrame.HLine)
    return d


class Toast(QLabel):
    """屏幕内轻提示"""

    _active: List["Toast"] = []

    def __init__(self, parent, text: str, msec: int = 2200):
        super().__init__(text, parent)
        self.setStyleSheet(toast_style())
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.adjustSize()
        self._reposition()
        self.show()
        Toast._active.append(self)
        QTimer.singleShot(msec, self._dismiss)

    def _reposition(self):
        parent = self.parentWidget()
        if parent:
            x = (parent.width() - self.width()) // 2
            y = int(parent.height() * 0.78)
            self.move(max(0, x), max(0, y))

    def _dismiss(self):
        try:
            Toast._active.remove(self)
        except ValueError:
            pass
        self.deleteLater()


def show_toast(parent_widget, text: str):
    if not text:
        return
    Toast(parent_widget.window() if parent_widget else None, text)
