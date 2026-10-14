# -*- coding: utf-8 -*-
"""自定义控件：
- EQCurveWidget   EQ 曲线图（含悬停读数、目标曲线叠加、频段标记）
- CircleValueButton  EZEQ 圆形数值按钮（对照 ControlEZEQValueButton）
- Row 帮助函数：设置行 / 开关 / 滑块行
- Toast 轻提示（跟随窗口缩放）
"""
from __future__ import annotations

import math
from typing import List, Optional

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
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
from ..protocol.eqdata import EQData, log_freqs
from .theme import (
    C_ACCENT,
    C_DIVIDER,
    C_HIGHLIGHT_TEXT,
    C_MAIN_ICON,
    C_SECONDARY_BG,
    C_SECONDARY_TEXT,
    toast_style,
)

# ---------------- 绘图常量 ----------------
F_MIN = 20.0
F_MAX = 20000.0
DB_MIN = -12.0
DB_MAX = 12.0
CURVE_POINTS = 200          # 曲线采样点数（对数轴均匀）
CURVE_COLOR = "#ff00ff"
TARGET_COLOR = "#008b8b"
HOVER_COLOR = "#555555"
MARKER_COLOR = "#c000c0"


# ---------------- EQ 曲线 ----------------
class EQCurveWidget(QWidget):
    """EQ 频响曲线（20Hz-20kHz 对数轴，-12..+12dB）

    - 曲线在 set_data() 时一次性算好并缓存，悬停重绘不再触发重算
    - 可叠加目标参考曲线
    - 鼠标悬停显示十字准线与频点读数
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: Optional[EQData] = None
        self._target = None                 # TargetCurve | None
        self._freqs: List[float] = []
        self._dbs: List[float] = []
        self._target_dbs: List[float] = []
        self._hover_freq: Optional[float] = None
        self._hover_pos: Optional[QPointF] = None

        self.setMinimumHeight(180)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)

        self._grid_pen = QPen(QColor("#bbbbbb"), 1)
        self._axis_pen = QPen(QColor("#888888"), 1)
        self._curve_pen = QPen(QColor(CURVE_COLOR), 2.5)
        self._curve_pen.setJoinStyle(Qt.RoundJoin)
        self._target_pen = QPen(QColor(TARGET_COLOR), 1.6)
        self._target_pen.setStyle(Qt.DashLine)
        self._hover_pen = QPen(QColor(HOVER_COLOR), 1)
        self._hover_pen.setStyle(Qt.DotLine)
        self._marker_pen = QPen(QColor("#ffffff"), 1)
        self._text_pen = QPen(QColor("#888888"))
        self._label_pen = QPen(QColor("#777777"))

    # ---------------- 数据 ----------------
    def set_data(self, data: Optional[EQData]):
        self._data = data
        self._recompute()
        self.update()

    def set_target(self, target):
        """target: TargetCurve | None"""
        self._target = target
        self._recompute_target()
        self.update()

    def _recompute(self):
        """一次性计算整条曲线（避免逐点重算三角函数）"""
        if self._data is None:
            self._freqs, self._dbs = [], []
            return
        self._freqs = log_freqs(F_MIN, F_MAX, CURVE_POINTS)
        try:
            self._dbs = self._data.response_curve(self._freqs)
        except Exception:
            self._dbs = [0.0] * len(self._freqs)
        self._recompute_target()

    def _recompute_target(self):
        if self._target is None or not self._freqs:
            self._target_dbs = []
            return
        try:
            self._target_dbs = self._target.sample(self._freqs)
        except Exception:
            self._target_dbs = []

    # ---------------- 坐标换算 ----------------
    @staticmethod
    def _freq_to_x(freq: float, w: int) -> float:
        return (math.log10(max(freq, 1e-6)) - math.log10(F_MIN)) / (
            math.log10(F_MAX) - math.log10(F_MIN)) * w

    @staticmethod
    def _x_to_freq(x: float, w: int) -> float:
        if w <= 0:
            return F_MIN
        t = min(max(x / w, 0.0), 1.0)
        return F_MIN * math.pow(10.0, t * (math.log10(F_MAX) - math.log10(F_MIN)))

    @staticmethod
    def _db_to_y(db: float, h: int) -> float:
        return h * (1.0 - (db - DB_MIN) / (DB_MAX - DB_MIN))

    # ---------------- 绘制 ----------------
    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(C_SECONDARY_BG))

        # 网格
        font = QFont(self.font())
        font.setPointSize(8)
        p.setFont(font)
        for db in (-12, -6, 0, 6, 12):
            y = self._db_to_y(db, h)
            p.setPen(self._grid_pen)
            p.drawLine(0, int(y), w, int(y))
            p.setPen(self._label_pen)
            p.drawText(4, int(y) - 4, f"{db} dB")
        for f in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
            x = self._freq_to_x(f, w)
            p.setPen(self._grid_pen)
            p.drawLine(int(x), 0, int(x), h)
            p.setPen(self._label_pen)
            label = f"{f // 1000}k" if f >= 1000 else str(f)
            # 两端标签需内收，避免被控件边缘裁切
            lx = min(max(int(x) - 14, 2), max(2, w - 26))
            p.drawText(lx, h - 4, label)


        # 0dB 轴线
        p.setPen(self._axis_pen)
        p.drawLine(0, int(self._db_to_y(0, h)), w, int(self._db_to_y(0, h)))

        # 目标曲线
        if self._target_dbs and len(self._target_dbs) == len(self._freqs):
            p.setPen(self._target_pen)
            path = QPainterPath()
            for i, f in enumerate(self._freqs):
                x = self._freq_to_x(f, w)
                y = self._db_to_y(self._target_dbs[i], h)
                path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
            p.drawPath(path)

        # 主曲线（用缓存，不重算）
        if self._dbs and len(self._dbs) == len(self._freqs):
            p.setPen(self._curve_pen)
            path = QPainterPath()
            for i, f in enumerate(self._freqs):
                x = self._freq_to_x(f, w)
                y = self._db_to_y(self._dbs[i], h)
                path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
            p.drawPath(path)

            # 频段标记
            if self._data is not None:
                p.setPen(self._marker_pen)
                p.setBrush(QColor(MARKER_COLOR))
                for i in range(len(self._data.fc_list)):
                    x = self._freq_to_x(self._data.fc_list[i], w)
                    y = self._db_to_y(self._data.gain_list[i], h)
                    p.drawEllipse(QPointF(x, y), 3.0, 3.0)
                p.setBrush(Qt.NoBrush)

        # 悬停十字准线 + 读数
        if self._hover_freq is not None and self._dbs:
            self._paint_hover(p, w, h)

        p.end()

    def _paint_hover(self, p: QPainter, w: int, h: int):
        f = self._hover_freq
        x = self._freq_to_x(f, w)
        p.setPen(self._hover_pen)
        p.drawLine(int(x), 0, int(x), h)

        cur = self._interp_cached(f)
        y = self._db_to_y(cur, h)
        p.setPen(QPen(QColor(CURVE_COLOR), 1))
        p.setBrush(QColor(CURVE_COLOR))
        p.drawEllipse(QPointF(x, y), 3.5, 3.5)
        p.setBrush(Qt.NoBrush)

        lines = [f"{f:.0f} Hz", f"EQ {cur:+.1f} dB"]
        if self._target_dbs:
            tv = self._interp_target(f)
            lines.append(f"目标 {tv:+.1f} dB")
            lines.append(f"偏差 {cur - tv:+.1f} dB")
            ty = self._db_to_y(tv, h)
            p.setPen(QPen(QColor(TARGET_COLOR), 1))
            p.setBrush(QColor(TARGET_COLOR))
            p.drawEllipse(QPointF(x, ty), 3.0, 3.0)
            p.setBrush(Qt.NoBrush)

        font = QFont(self.font())
        font.setPointSize(8)
        p.setFont(font)
        metrics = p.fontMetrics()
        tw = max(metrics.horizontalAdvance(s) for s in lines) + 12
        th = metrics.height() * len(lines) + 8

        bx = x + 10
        if bx + tw > w:
            bx = x - tw - 10
        bx = max(2.0, bx)
        by = min(max(6.0, y - th / 2), h - th - 6)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRoundedRect(QRectF(bx, by, tw, th), 4, 4)
        p.setPen(QPen(QColor("#cccccc"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(bx, by, tw, th), 4, 4)

        p.setPen(QPen(QColor("#333333")))
        for i, s in enumerate(lines):
            p.drawText(int(bx + 6), int(by + metrics.height() * (i + 1)), s)

    def _interp_cached(self, freq: float) -> float:
        return self._interp(self._freqs, self._dbs, freq)

    def _interp_target(self, freq: float) -> float:
        return self._interp(self._freqs, self._target_dbs, freq)

    @staticmethod
    def _interp(freqs: List[float], vals: List[float], freq: float) -> float:
        if not freqs or not vals or len(freqs) != len(vals):
            return 0.0
        if freq <= freqs[0]:
            return vals[0]
        if freq >= freqs[-1]:
            return vals[-1]
        lo, hi = 0, len(freqs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if freqs[mid] <= freq:
                lo = mid
            else:
                hi = mid
        f0, v0 = freqs[lo], vals[lo]
        f1, v1 = freqs[hi], vals[hi]
        if f1 <= f0:
            return v0
        t = (math.log10(freq) - math.log10(f0)) / (math.log10(f1) - math.log10(f0))
        return v0 + (v1 - v0) * t

    # ---------------- 交互 ----------------
    def mouseMoveEvent(self, event):  # noqa: N802
        if self._dbs:
            self._hover_freq = self._x_to_freq(event.position().x(), self.width())
            self._hover_pos = event.position()
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover_freq = None
        self._hover_pos = None
        self.update()
        super().leaveEvent(event)


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
    """屏幕内轻提示（跟随父窗口缩放重新定位）"""

    _active: List["Toast"] = []

    def __init__(self, parent, text: str, msec: int = 2200):
        super().__init__(text, parent)
        self.setStyleSheet(toast_style())
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.adjustSize()
        self._reposition()
        self.show()
        if parent is not None:
            parent.installEventFilter(self)
        Toast._active.append(self)
        QTimer.singleShot(msec, self._dismiss)

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Resize:
            self._reposition()
        return False

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
        parent = self.parentWidget()
        if parent is not None:
            try:
                parent.removeEventFilter(self)
            except Exception:
                pass
        self.deleteLater()


def show_toast(parent_widget, text: str):
    if not text:
        return
    Toast(parent_widget.window() if parent_widget else None, text)
