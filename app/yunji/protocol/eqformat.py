# -*- coding: utf-8 -*-
"""EQ 导入格式解析

支持社区实际流通的四种格式：

1. Equalizer APO / AutoEQ ParametricEQ.txt
       Filter 1: ON PK Fc 105 Hz Gain -3.2 dB Q 0.70
       Preamp: -6.0 dB
2. GraphicEQ（squig.link / Wavelet 导出）
       GraphicEQ: 20 -3.5; 25 -3.2; 31 -2.9; ...
3. Wavelet JSON
       {"graphicEQ": [[20, -3.5], [25, -3.2], ...]}
4. 本工具原生格式
       {"bands": [{"freq": 60, "q": 0.75, "gain": 0, "type": 2}]}

解析结果统一为 ParsedEQ：要么是若干参数段（bands），要么是一条频响折线（graphic）。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..config import EQ_TYPE_HIGH_SHELF, EQ_TYPE_LOW_SHELF, EQ_TYPE_PEAKING

log = logging.getLogger(__name__)


@dataclass
class ParsedBand:
    freq: float
    q: float
    gain: float
    type: int


@dataclass
class ParsedEQ:
    bands: List[ParsedBand] = field(default_factory=list)
    graphic: List[Tuple[float, float]] = field(default_factory=list)
    preamp: Optional[float] = None
    fmt: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.bands and not self.graphic


# ---------------- 类型映射 ----------------
# Equalizer APO 的滤波器类型记号 → 本工具类型码
_APO_TYPES = {
    "PK": EQ_TYPE_PEAKING, "PEQ": EQ_TYPE_PEAKING, "MODAL": EQ_TYPE_PEAKING,
    "LS": EQ_TYPE_LOW_SHELF, "LSC": EQ_TYPE_LOW_SHELF, "LSH": EQ_TYPE_LOW_SHELF,
    "HS": EQ_TYPE_HIGH_SHELF, "HSC": EQ_TYPE_HIGH_SHELF, "HSH": EQ_TYPE_HIGH_SHELF,
}


# ---------------- 各格式解析 ----------------
_APO_LINE = re.compile(
    r"Filter\s*\d*\s*:\s*(?P<on>ON|OFF)?\s*(?P<type>[A-Za-z]+)"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)
# 数值允许带显式正号（部分工具导出为 Gain +5.5 dB）
_APO_KV = re.compile(r"(Fc|Gain|Q|BW)\s+([+-]?\d+(?:\.\d+)?)", re.IGNORECASE)



def _parse_apo(text: str) -> ParsedEQ:
    """Equalizer APO / AutoEQ 参数式文本"""
    out = ParsedEQ(fmt="Equalizer APO")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        m_pre = re.match(r"Preamp\s*:\s*(-?\d+(?:\.\d+)?)\s*dB", line, re.IGNORECASE)
        if m_pre:
            out.preamp = float(m_pre.group(1))
            continue

        m = _APO_LINE.match(line)
        if not m:
            continue
        if (m.group("on") or "ON").upper() == "OFF":
            continue
        apo_type = m.group("type").upper()
        if apo_type not in _APO_TYPES:
            log.debug("跳过不支持的 APO 滤波器类型: %s", apo_type)
            continue

        kv = {k.upper(): float(v) for k, v in _APO_KV.findall(m.group("rest"))}
        freq = kv.get("FC")
        if freq is None:
            continue
        gain = kv.get("GAIN", 0.0)
        q = kv.get("Q")
        if q is None:
            bw = kv.get("BW")
            q = _bw_to_q(bw) if bw else 0.75
        out.bands.append(ParsedBand(freq=freq, q=q, gain=gain,
                                    type=_APO_TYPES[apo_type]))
    return out


def _bw_to_q(bw: float) -> float:
    """带宽（八度）→ Q 值"""
    if bw <= 0:
        return 0.75
    return 1.0 / (2.0 * (2.0 ** (bw / 2.0) - 2.0 ** (-bw / 2.0))) if bw else 0.75


_GRAPHIC_HEAD = re.compile(r"GraphicEQ\s*:\s*", re.IGNORECASE)
_GRAPHIC_PAIR = re.compile(r"([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)")



def _parse_graphic_eq(text: str) -> ParsedEQ:
    """GraphicEQ: 20 -3.5; 25 -3.2; ...（分号或换行分隔均可）"""
    m = _GRAPHIC_HEAD.search(text)
    if not m:
        return ParsedEQ()
    body = text[m.end():]
    out = ParsedEQ(fmt="GraphicEQ")
    for a, b in _GRAPHIC_PAIR.findall(body):
        try:
            out.graphic.append((float(a), float(b)))
        except ValueError:
            continue
    out.graphic.sort(key=lambda p: p[0])
    return out


def _parse_wavelet(text: str) -> ParsedEQ:
    """Wavelet 导出的 JSON：{"graphicEQ": [[freq, gain], ...]}"""
    try:
        obj = json.loads(text)
    except Exception:
        return ParsedEQ()
    if not isinstance(obj, dict):
        return ParsedEQ()
    pts = obj.get("graphicEQ")
    if not isinstance(pts, list) or not pts:
        return ParsedEQ()
    out = ParsedEQ(fmt="Wavelet")
    for p in pts:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                out.graphic.append((float(p[0]), float(p[1])))
            except (TypeError, ValueError):
                continue
    out.graphic.sort(key=lambda p: p[0])
    return out


def _parse_native(text: str) -> ParsedEQ:
    """本工具原生格式：{"bands":[{"freq","q","gain","type"}]}"""
    try:
        obj = json.loads(text)
    except Exception:
        return ParsedEQ()
    if not isinstance(obj, dict):
        return ParsedEQ()
    raw = obj.get("bands")
    if not isinstance(raw, list) or not raw:
        return ParsedEQ()
    out = ParsedEQ(fmt="本工具格式")
    for b in raw:
        if not isinstance(b, dict):
            continue
        try:
            out.bands.append(ParsedBand(
                freq=float(b.get("freq", 1000)),
                q=float(b.get("q", 0.75)),
                gain=float(b.get("gain", 0.0)),
                type=int(b.get("type", EQ_TYPE_PEAKING)),
            ))
        except (TypeError, ValueError):
            continue
    if obj.get("preamp") is not None:
        try:
            out.preamp = float(obj["preamp"])
        except (TypeError, ValueError):
            pass
    return out


# ---------------- 统一入口 ----------------
def parse_eq_text(text: str) -> ParsedEQ:
    """自动嗅探格式并解析；无法识别时返回空的 ParsedEQ"""
    if not text or not text.strip():
        return ParsedEQ()
    text = text.strip()

    # JSON 优先（原生 / Wavelet 都是 JSON）
    if text[0] in "{[":
        native = _parse_native(text)
        if not native.is_empty:
            return native
        wavelet = _parse_wavelet(text)
        if not wavelet.is_empty:
            return wavelet

    # GraphicEQ 文本
    if _GRAPHIC_HEAD.search(text):
        g = _parse_graphic_eq(text)
        if not g.is_empty:
            return g

    # Equalizer APO 文本
    apo = _parse_apo(text)
    if not apo.is_empty:
        return apo

    return ParsedEQ()


# ---------------- 导出 ----------------
def to_apo_text(bands, preamp: Optional[float] = None) -> str:
    """导出为 Equalizer APO 文本（便于分享到社区）

    数值不带显式正号，与 AutoEQ 官方导出风格一致。
    """
    name = {EQ_TYPE_PEAKING: "PK", EQ_TYPE_LOW_SHELF: "LSC",
            EQ_TYPE_HIGH_SHELF: "HSC"}
    lines = ["Preamp: %.1f dB" % (preamp if preamp is not None else 0.0)]
    for i, b in enumerate(bands, 1):
        lines.append("Filter %d: ON %s Fc %d Hz Gain %.1f dB Q %.2f"
                     % (i, name.get(int(b.type), "PK"), int(round(b.freq)),
                        float(b.gain), float(b.q)))
    return "\n".join(lines)


def to_native_json(bands, preamp: Optional[float] = None) -> str:
    obj = {
        "bands": [{"freq": int(round(b.freq)), "q": round(float(b.q), 3),
                   "gain": round(float(b.gain), 1), "type": int(b.type)}
                  for b in bands],
    }
    if preamp is not None:
        obj["preamp"] = round(float(preamp), 1)
    return json.dumps(obj, ensure_ascii=False, indent=2)
