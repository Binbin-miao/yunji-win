# -*- coding: utf-8 -*-
"""目标曲线（参考曲线）加载与叠加

内置曲线数据来自 AutoEQ 项目（jaakkopasanen/AutoEq，MIT License），
已归一化到 1 kHz = 0 dB，并截断至测量有效范围（≤10 kHz，其后平延）。

用途：在 EQ 曲线上叠一条参考线，直观看出「当前调音离目标差多少」。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from ..storage import resolve_asset

log = logging.getLogger(__name__)

TARGETS_DIR = "targets"

#: 内置曲线清单：(文件 id, 显示名)
BUILTIN_TARGETS: List[Tuple[str, str]] = [
    ("harman_ie2019", "Harman 入耳式 2019"),
    ("harman_oe2018", "Harman 头戴式 2018"),
    ("autoeq_ie", "AutoEq 入耳式（中性）"),
]


@dataclass
class TargetCurve:
    id: str
    label: str
    points: List[Tuple[float, float]]
    source: str = ""
    valid_max_hz: float = 10000.0

    def value_at(self, freq: float) -> float:
        """对数轴线性插值"""
        pts = self.points
        if not pts:
            return 0.0
        if freq <= pts[0][0]:
            return pts[0][1]
        if freq >= pts[-1][0]:
            return pts[-1][1]
        lo, hi = 0, len(pts) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if pts[mid][0] <= freq:
                lo = mid
            else:
                hi = mid
        f0, g0 = pts[lo]
        f1, g1 = pts[hi]
        if f1 <= f0:
            return g0
        import math
        t = (math.log10(freq) - math.log10(f0)) / (math.log10(f1) - math.log10(f0))
        return g0 + (g1 - g0) * t

    def sample(self, freqs: Sequence[float]) -> List[float]:
        return [self.value_at(f) for f in freqs]


_cache: dict = {}


def load_target(target_id: str) -> Optional[TargetCurve]:
    """载入内置目标曲线；不存在或解析失败返回 None"""
    if target_id in _cache:
        return _cache[target_id]
    path = resolve_asset(f"{TARGETS_DIR}/{target_id}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        pts = [(float(p[0]), float(p[1])) for p in raw.get("points", [])
               if isinstance(p, (list, tuple)) and len(p) >= 2]
        pts.sort(key=lambda p: p[0])
        if not pts:
            return None
        curve = TargetCurve(
            id=str(raw.get("id", target_id)),
            label=str(raw.get("label", target_id)),
            points=pts,
            source=str(raw.get("source", "")),
            valid_max_hz=float(raw.get("valid_max_hz", 10000.0)),
        )
        _cache[target_id] = curve
        return curve
    except Exception:
        log.warning("目标曲线载入失败: %s", target_id, exc_info=True)
        return None


def list_targets() -> List[TargetCurve]:
    out = []
    for tid, _label in BUILTIN_TARGETS:
        c = load_target(tid)
        if c is not None:
            out.append(c)
    return out


def make_curve_from_points(points: Sequence[Tuple[float, float]],
                           label: str = "自定义") -> Optional[TargetCurve]:
    """从任意 (freq, dB) 点构造临时曲线（例如导入的 GraphicEQ）"""
    pts = [(float(a), float(b)) for a, b in points if a > 0]
    if not pts:
        return None
    pts.sort(key=lambda p: p[0])
    return TargetCurve(id="__custom__", label=label, points=pts)
