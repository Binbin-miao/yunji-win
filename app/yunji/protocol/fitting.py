# -*- coding: utf-8 -*-
"""把任意段数的 EQ 目标曲线拟合为设备的 8 段参数均衡

为什么需要：AutoEQ 导出的配置常见 10 段，GraphicEQ 则是上百个频响点，
而设备只接受 8 段。旧实现是 `bands[:8]` 直接截断 —— 第 9 段之后被静默丢弃，
用户完全不知道。

算法（纯 Python，不引入 numpy/scipy 以免打包体积膨胀）
------------------------------------------------------
以 8 个 biquad 的响应为基函数，在 dB 域做带岭正则的最小二乘：

    R(f) ≈ Σ g_i · B_i(f)

其中 B_i 用**数值导数**求得（对第 i 段增益 ±0.5dB 求差分），
比「单位增益近似」更准确，并能通过外层次迭代吸收 biquad 的非线性。

每次迭代解 8×8 正规方程（高斯消元 + 部分主元），迭代 4 次即收敛。

注意：拟合在**显示域（48 kHz）**进行，与官方 App 的曲线显示保持一致，
因此屏幕上「拟合结果 vs 目标曲线」的对照是可信的。
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from ..config import (
    EQ_DISPLAY_SAMPLE_RATE,
    EQ_TYPE_HIGH_SHELF,
    EQ_TYPE_LOW_SHELF,
    EQ_TYPE_PEAKING,
    PROEQ_DEFAULT_Q,
    TTGK_MAX_EQ_GAIN,
    TTGK_MIN_EQ_GAIN,
)
from .eqdata import band_coeffs_normalized, response_db_from_coeffs
from .eqformat import ParsedEQ

log = logging.getLogger(__name__)

#: 拟合用的频点数量（对数轴均匀分布）
FIT_POINTS = 160
#: 迭代次数
FIT_ITERATIONS = 5
#: 岭正则系数（相对矩阵迹的比例），避免基函数共线导致奇异
RIDGE = 1e-4


@dataclass
class FitResult:
    gains: List[float]
    centers: List[float]
    qs: List[float]
    types: List[int]
    max_error: float = 0.0
    rms_error: float = 0.0
    source_bands: int = 0
    target_curve: Optional[Tuple[List[float], List[float]]] = None

    @property
    def needs_fit(self) -> bool:
        return self.source_bands > len(self.centers)


# ---------------- 工具 ----------------
def _log_grid(f_min: float, f_max: float, n: int) -> List[float]:
    ratio = math.log10(f_max / f_min)
    return [f_min * math.pow(10.0, (i / (n - 1.0)) * ratio) for i in range(n)]


def _interp_log(points: Sequence[Tuple[float, float]], f: float) -> float:
    """在对数频率轴上线性插值；超出范围取端点值"""
    if not points:
        return 0.0
    if f <= points[0][0]:
        return points[0][1]
    if f >= points[-1][0]:
        return points[-1][1]
    lo, hi = 0, len(points) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if points[mid][0] <= f:
            lo = mid
        else:
            hi = mid
    f0, g0 = points[lo]
    f1, g1 = points[hi]
    if f1 <= f0:
        return g0
    t = (math.log10(f) - math.log10(f0)) / (math.log10(f1) - math.log10(f0))
    return g0 + (g1 - g0) * t


def _band_response(freqs: Sequence[float], center: float, q: float,
                   gain: float, ftype: int) -> List[float]:
    c = band_coeffs_normalized(center, q, gain, ftype, EQ_DISPLAY_SAMPLE_RATE)
    return [response_db_from_coeffs(f, c, EQ_DISPLAY_SAMPLE_RATE) for f in freqs]


def _sum_response(freqs: Sequence[float], centers, qs, types,
                  gains) -> List[float]:
    n = len(freqs)
    total = [0.0] * n
    for i in range(len(centers)):
        r = _band_response(freqs, centers[i], qs[i], gains[i], types[i])
        for k in range(n):
            total[k] += r[k]
    return total


# ---------------- 线性代数 ----------------
def _gauss_solve(A: List[List[float]], b: List[float]) -> Optional[List[float]]:
    """高斯消元（部分主元）解 A x = b"""
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        if piv != col:
            M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        for r in range(col + 1, n):
            factor = M[r][col] / pv
            if factor == 0.0:
                continue
            for c in range(col, n + 1):
                M[r][c] -= factor * M[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = M[r][n] - sum(M[r][c] * x[c] for c in range(r + 1, n))
        x[r] = s / M[r][r]
    return x


def _ridge_lstsq(basis: List[List[float]], y: List[float]) -> Optional[List[float]]:
    """带岭正则的最小二乘：min ||B^T g - y||² + λ||g||²"""
    m = len(basis)
    n = len(y)
    A = [[0.0] * m for _ in range(m)]
    rhs = [0.0] * m
    for i in range(m):
        bi = basis[i]
        for j in range(i, m):
            bj = basis[j]
            s = 0.0
            for k in range(n):
                s += bi[k] * bj[k]
            A[i][j] = s
            A[j][i] = s
        rhs[i] = sum(bi[k] * y[k] for k in range(n))

    trace = sum(A[i][i] for i in range(m))
    lam = RIDGE * (trace / m if m else 1.0)
    for i in range(m):
        A[i][i] += lam
    return _gauss_solve(A, rhs)


# ---------------- 主流程 ----------------
def build_target_curve(parsed: ParsedEQ, freqs: Sequence[float]) -> List[float]:
    """把解析结果转成目标频响（dB）"""
    if parsed.graphic:
        pts = parsed.graphic
        return [_interp_log(pts, f) for f in freqs]
    if parsed.bands:
        centers = [b.freq for b in parsed.bands]
        qs = [b.q for b in parsed.bands]
        types = [b.type for b in parsed.bands]
        gains = [b.gain for b in parsed.bands]
        return _sum_response(freqs, centers, qs, types, gains)
    return [0.0] * len(freqs)


def _pick_centers(parsed: ParsedEQ) -> List[float]:
    """选择 8 个中心频率

    - 源是参数段且不超过 8 段：直接沿用其频率（保真最高）
    - 否则：在 30Hz–16kHz 对数轴上均匀取 8 个点（覆盖更均衡）
    """
    if parsed.bands and len(parsed.bands) <= 8:
        cs = sorted(b.freq for b in parsed.bands)
        return [max(20.0, min(20000.0, c)) for c in cs]
    return _log_grid(30.0, 16000.0, 8)


def _source_defaults(parsed: ParsedEQ):
    """源是 <=8 段的参数式配置时，连 Q 与类型一并沿用

    否则一个 Q=1.5 的窄带会被强行用 Q=0.75 的宽带去凑，
    增益与听感都会偏离（低频段尤其明显）。
    """
    if not parsed.bands or len(parsed.bands) > 8:
        return None
    ordered = sorted(parsed.bands, key=lambda b: b.freq)
    centers = [max(20.0, min(20000.0, b.freq)) for b in ordered]
    qs = [float(b.q) if b.q > 0 else 0.75 for b in ordered]
    types = [int(b.type) for b in ordered]
    return centers, qs, types


def fit_parsed(parsed: ParsedEQ,
               centers: Optional[Sequence[float]] = None,
               qs: Optional[Sequence[float]] = None,
               types: Optional[Sequence[int]] = None) -> FitResult:
    """把 ParsedEQ 拟合成 8 段参数均衡"""
    src = _source_defaults(parsed)

    if centers is None:
        centers = src[0] if src else _pick_centers(parsed)
    centers = list(centers)
    n_bands = len(centers)

    default_q = float(PROEQ_DEFAULT_Q[0]) if PROEQ_DEFAULT_Q else 0.75
    if qs is None:
        qs = src[1] if src else [default_q] * n_bands
    qs = list(qs)
    if types is None:
        types = src[2] if src else [EQ_TYPE_PEAKING] * n_bands
    types = list(types)



    freqs = _log_grid(20.0, 20000.0, FIT_POINTS)
    target = build_target_curve(parsed, freqs)

    src_count = len(parsed.bands) if parsed.bands else len(parsed.graphic)

    gains = [0.0] * n_bands
    for _ in range(FIT_ITERATIONS):
        cur = _sum_response(freqs, centers, qs, types, gains)
        resid = [target[k] - cur[k] for k in range(FIT_POINTS)]

        basis = []
        for i in range(n_bands):
            gp = list(gains)
            gp[i] += 0.5
            gm = list(gains)
            gm[i] -= 0.5
            rp = _sum_response(freqs, centers, qs, types, gp)
            rm = _sum_response(freqs, centers, qs, types, gm)
            basis.append([(rp[k] - rm[k]) for k in range(FIT_POINTS)])

        delta = _ridge_lstsq(basis, resid)
        if delta is None:
            log.warning("拟合求解失败，保留当前结果")
            break

        new_gains = [max(float(TTGK_MIN_EQ_GAIN),
                         min(float(TTGK_MAX_EQ_GAIN), g + d))
                     for g, d in zip(gains, delta)]
        moved = max(abs(a - b) for a, b in zip(new_gains, gains))
        gains = new_gains
        if moved < 1e-4:
            break

    final = _sum_response(freqs, centers, qs, types, gains)
    errs = [target[k] - final[k] for k in range(FIT_POINTS)]
    max_err = max(abs(e) for e in errs) if errs else 0.0
    rms_err = math.sqrt(sum(e * e for e in errs) / len(errs)) if errs else 0.0

    # 量化到 0.1 dB（与设备写入精度一致）
    gains = [round(g, 1) for g in gains]

    return FitResult(gains=gains, centers=[float(c) for c in centers],
                     qs=[float(q) for q in qs], types=[int(t) for t in types],
                     max_error=max_err, rms_error=rms_err,
                     source_bands=src_count,
                     target_curve=(list(freqs), target))
