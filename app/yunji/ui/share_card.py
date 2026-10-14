# -*- coding: utf-8 -*-
"""导出分享图：把当前 EQ 曲线与参数渲染成一张 PNG

布局：
    ┌ 标题 / 设备名 / 日期 ────────────────┐
    │  频响曲线（含目标曲线叠加）           │
    │  8 段参数表                          │
    │  页脚：项目地址 + 非官方声明          │
    └──────────────────────────────────────┘
"""
from __future__ import annotations

import datetime
import math
from typing import List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from ..protocol.eqdata import EQData, log_freqs, type_name
from .fonts import ensure_cjk_font

W, H = 960, 720
F_MIN, F_MAX = 20.0, 20000.0
DB_MIN, DB_MAX = -12.0, 12.0

CURVE_COLOR = QColor("#d81b8c")
TARGET_COLOR = QColor("#008b8b")
GRID_COLOR = QColor("#e0e0e0")
AXIS_COLOR = QColor("#9e9e9e")
TEXT_COLOR = QColor("#263238")
MUTED_COLOR = QColor("#78909c")


def _font(size: int, bold: bool = False) -> QFont:
    family = ensure_cjk_font()
    f = QFont(family) if family else QFont()
    f.setPointSize(size)
    f.setBold(bold)
    return f



def _freq_to_x(freq: float, x0: float, x1: float) -> float:
    t = (math.log10(max(freq, 1e-6)) - math.log10(F_MIN)) / (
        math.log10(F_MAX) - math.log10(F_MIN))
    return x0 + t * (x1 - x0)


def _db_to_y(db: float, y0: float, y1: float) -> float:
    t = (db - DB_MIN) / (DB_MAX - DB_MIN)
    return y1 - t * (y1 - y0)


def render_share_card(data: EQData, device_name: str,
                      target=None) -> QPixmap:
    """渲染分享图并返回 QPixmap"""
    pm = QPixmap(W, H)
    pm.fill(QColor("#ffffff"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    # ---------------- 页眉 ----------------
    p.setPen(QPen(TEXT_COLOR))
    p.setFont(_font(16, bold=True))
    p.drawText(QRectF(40, 24, W - 80, 30), Qt.AlignLeft | Qt.AlignVCenter,
               "云姬电脑版 · EQ 调音曲线")

    p.setFont(_font(11))
    p.setPen(QPen(MUTED_COLOR))
    p.drawText(QRectF(40, 54, W - 80, 24), Qt.AlignLeft | Qt.AlignVCenter,
               f"设备：{device_name}")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    p.drawText(QRectF(40, 54, W - 80, 24), Qt.AlignRight | Qt.AlignVCenter, stamp)

    # ---------------- 曲线区 ----------------
    cx0, cx1 = 78.0, W - 42.0
    cy0, cy1 = 100.0, 380.0

    p.setPen(QPen(GRID_COLOR, 1))
    p.setFont(_font(9))
    for db in (-12, -6, 0, 6, 12):
        y = _db_to_y(db, cy0, cy1)
        p.setPen(QPen(GRID_COLOR, 1))
        p.drawLine(QPointF(cx0, y), QPointF(cx1, y))
        p.setPen(QPen(MUTED_COLOR))
        p.drawText(QRectF(30, y - 9, 44, 18), Qt.AlignRight | Qt.AlignVCenter,
                   f"{db:+d}" if db else "0")
    for f in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000):
        x = _freq_to_x(f, cx0, cx1)
        p.setPen(QPen(GRID_COLOR, 1))
        p.drawLine(QPointF(x, cy0), QPointF(x, cy1))
        p.setPen(QPen(MUTED_COLOR))
        label = f"{f // 1000}k" if f >= 1000 else str(f)
        p.drawText(QRectF(x - 24, cy1 + 4, 48, 18), Qt.AlignHCenter | Qt.AlignTop, label)

    # 0dB 轴线
    p.setPen(QPen(AXIS_COLOR, 1, Qt.DashLine))
    y0 = _db_to_y(0, cy0, cy1)
    p.drawLine(QPointF(cx0, y0), QPointF(cx1, y0))

    freqs = log_freqs(F_MIN, F_MAX, 260)

    # 目标曲线
    if target is not None:
        tdb = target.sample(freqs)
        p.setPen(QPen(TARGET_COLOR, 1.6, Qt.DashLine))
        path = QPainterPath()
        for i, f in enumerate(freqs):
            pt = QPointF(_freq_to_x(f, cx0, cx1), _db_to_y(tdb[i], cy0, cy1))
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        p.drawPath(path)

    # 主曲线
    try:
        dbs = data.response_curve(freqs)
    except Exception:
        dbs = [0.0] * len(freqs)
    p.setPen(QPen(CURVE_COLOR, 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    path = QPainterPath()
    for i, f in enumerate(freqs):
        pt = QPointF(_freq_to_x(f, cx0, cx1), _db_to_y(dbs[i], cy0, cy1))
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    p.drawPath(path)

    # 频段标记
    p.setPen(QPen(QColor("#ffffff"), 1.4))
    p.setBrush(CURVE_COLOR)
    for i in range(len(data.fc_list)):
        x = _freq_to_x(data.fc_list[i], cx0, cx1)
        y = _db_to_y(data.gain_list[i], cy0, cy1)
        p.drawEllipse(QPointF(x, y), 3.4, 3.4)
    p.setBrush(Qt.NoBrush)

    # 图例
    lx, ly = cx0, cy0 - 18
    p.setPen(QPen(CURVE_COLOR, 2.6))
    p.drawLine(QPointF(lx, ly), QPointF(lx + 22, ly))
    p.setPen(QPen(TEXT_COLOR))
    p.setFont(_font(9))
    p.drawText(QRectF(lx + 28, ly - 9, 60, 18), Qt.AlignLeft | Qt.AlignVCenter, "当前 EQ")
    if target is not None:
        lx2 = lx + 110
        p.setPen(QPen(TARGET_COLOR, 1.6, Qt.DashLine))
        p.drawLine(QPointF(lx2, ly), QPointF(lx2 + 22, ly))
        p.setPen(QPen(TEXT_COLOR))
        p.drawText(QRectF(lx2 + 28, ly - 9, 200, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   f"目标：{target.label}")

    # ---------------- 参数表 ----------------
    ty = cy1 + 30
    p.setFont(_font(11, bold=True))
    p.setPen(QPen(TEXT_COLOR))
    p.drawText(QRectF(40, ty, W - 80, 22), Qt.AlignLeft | Qt.AlignVCenter, "参数")
    ty += 24

    cols = ["#", "频率", "Q", "增益", "类型"]
    weights = [0.10, 0.24, 0.20, 0.22, 0.24]
    xs = [40.0]
    for w in weights:
        xs.append(xs[-1] + w * (W - 80))

    p.setFont(_font(10, bold=True))
    p.setPen(QPen(MUTED_COLOR))
    for i, c in enumerate(cols):
        p.drawText(QRectF(xs[i], ty, xs[i + 1] - xs[i], 20),
                   Qt.AlignLeft | Qt.AlignVCenter, c)
    ty += 21
    p.setPen(QPen(GRID_COLOR, 1))
    p.drawLine(QPointF(40, ty), QPointF(W - 40, ty))
    ty += 4

    p.setFont(_font(10))
    row_h = 19.0
    for i in range(8):
        vals = [str(i + 1),
                f"{int(data.fc_list[i])} Hz",
                f"{data.q_list[i]:.2f}",
                f"{data.gain_list[i]:+.1f} dB",
                type_name(int(data.type_list[i]))]
        p.setPen(QPen(TEXT_COLOR))
        for j, v in enumerate(vals):
            p.drawText(QRectF(xs[j], ty, xs[j + 1] - xs[j], row_h),
                       Qt.AlignLeft | Qt.AlignVCenter, v)
        ty += row_h

    ty += 6
    p.setFont(_font(10))
    p.setPen(QPen(TEXT_COLOR))
    p.drawText(QRectF(40, ty, W - 80, 20), Qt.AlignLeft | Qt.AlignVCenter,
               f"整体偏移：{data.offset:+d} dB    峰值增益：{data.peak_gain_db():+.1f} dB")


    # ---------------- 页脚 ----------------
    p.setPen(QPen(GRID_COLOR, 1))
    p.drawLine(QPointF(40, H - 52), QPointF(W - 40, H - 52))
    p.setFont(_font(9))
    p.setPen(QPen(MUTED_COLOR))
    p.drawText(QRectF(40, H - 44, W - 80, 18), Qt.AlignLeft | Qt.AlignVCenter,
               "云姬电脑版（非官方 Windows 移植） · https://github.com/Binbin-miao/yunji-win")
    p.drawText(QRectF(40, H - 26, W - 80, 18), Qt.AlignLeft | Qt.AlignVCenter,
               "本项目与各音频硬件品牌官方无商业关联；品牌与型号名称仅用于指示硬件兼容性。")

    p.end()
    return pm
