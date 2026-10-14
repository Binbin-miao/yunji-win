# -*- coding: utf-8 -*-
"""EQ 数据模型与协议打包（逐字节对照 Android 版 EQData.kt / EQcoeffData.kt 实现）

关键点（务必保持与 Android 版完全一致）：
- biquad 系数由 RBJ peaking EQ 公式以 96 kHz 采样率计算
- 系数以 int32 小端（Q30 定点，×2^30 四舍五入）打包，共 20 字节
- 增益以 [小数×256, 整数] 两个字节打包
- 单波段包总长 37 字节
"""
import math
from dataclasses import dataclass, field
from typing import List

from ..config import (
    EQ_DEVICE_SAMPLE_RATE,
    EQ_DISPLAY_SAMPLE_RATE,
    PROEQ_DEFAULT_FREQ,
    PROEQ_DEFAULT_Q,
    PROEQ_DEFAULT_TYPE,
)

TWO_POW_30 = float(1 << 30)


def _java_round(x: float) -> int:
    """Java Math.round(double) = floor(x + 0.5)"""
    return int(math.floor(x + 0.5))


def _int32_le_bytes(v: int) -> bytes:
    v &= 0xFFFFFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF])


def _int16_le_bytes(v: int) -> bytes:
    v &= 0xFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF])


@dataclass
class EQData:
    """8 段 EQ 数据（对应对照 Android EQData 类）"""
    fc_list: List[int] = field(default_factory=lambda: list(PROEQ_DEFAULT_FREQ))
    q_list: List[float] = field(default_factory=lambda: list(PROEQ_DEFAULT_Q))
    gain_list: List[float] = field(default_factory=lambda: [0.0] * 8)
    type_list: List[int] = field(default_factory=lambda: [PROEQ_DEFAULT_TYPE] * 8)
    offset: int = 0
    name: str = ""

    # ---------- 打包 ----------
    def band_packet(self, index: int) -> bytes:
        """生成第 index 段（0-7）的设备数据包，共 37 字节"""
        coeff = self._compute_peak(self.fc_list[index], self.q_list[index], self.gain_list[index])
        fc = _int16_le_bytes(self.fc_list[index])
        # Q 字段在 Android 版中恒为常量 {0xC0, 0x00}（192 = 0.75×256）
        q_bytes = b"\xC0\x00"
        # 增益：[小数因子, 整数部分]
        gain = self.gain_list[index]
        floor_v = math.floor(gain)
        frac_v = int((gain - floor_v) * 256) & 0xFF
        gain_bytes = bytes([frac_v, int(floor_v) & 0xFF])
        head = bytes([0x4B, 0x01, 0x09, 0x18, 0x00, index, 0x00, 0x00])
        return (head + coeff + fc + q_bytes + gain_bytes
                + bytes([0x02, self.offset & 0xFF, 0x00]))

    def _compute_peak(self, freq: float, q: float, gain: float) -> bytes:
        """RBJ peaking EQ biquad 系数（96 kHz），Q30 int32 LE ×5 = 20 字节"""
        sqrt_a = math.sqrt(math.pow(10.0, gain / 20.0))
        w = (6.283185307179586 * freq) / EQ_DEVICE_SAMPLE_RATE
        alpha = math.sin(w) / (2.0 * q)
        d2 = alpha * sqrt_a
        d3 = alpha / sqrt_a
        d4 = d3 + 1.0
        cos_w = math.cos(w)
        # 分子 b：b0,b1,b2 归一化
        b = [
            (d2 + 1.0) / d4,
            (cos_w * -2.0) / d4,
            (1.0 - d2) / d4,
        ]
        # 分母 a（归一化 a0=1），返回 -a1, -a2
        a1 = (cos_w * -2.0) / d4
        a2 = (1.0 - d3) / d4
        ints = [
            _java_round(b[0] * TWO_POW_30),
            _java_round(b[1] * TWO_POW_30),
            _java_round(b[2] * TWO_POW_30),
            _java_round(-a1 * TWO_POW_30),
            _java_round(-a2 * TWO_POW_30),
        ]
        out = b""
        for v in ints:
            out += _int32_le_bytes(v)
        return out

    # ---------- 曲线（对照 EQCurveView.peakResponse，48 kHz 显示用）----------
    def response_db(self, freq: float) -> float:
        total = 0.0
        for i in range(len(self.fc_list)):
            total += self._peak_response(freq, self.fc_list[i], self.q_list[i], self.gain_list[i])
        return total

    @staticmethod
    def _peak_response(freq: float, band_freq: float, q: float, gain: float) -> float:
        a = math.pow(10.0, gain / 40.0)
        w0 = (band_freq * 6.283185307179586) / EQ_DISPLAY_SAMPLE_RATE
        alpha = math.sin(w0) / (q * 2.0)
        b0 = 1.0 + alpha * a
        b1 = -2.0 * math.cos(w0)
        b2 = 1.0 - alpha * a
        a0 = 1.0 + alpha / a
        a1 = -2.0 * math.cos(w0)
        a2 = 1.0 - alpha / a
        w = (freq * 6.283185307179586) / EQ_DISPLAY_SAMPLE_RATE
        cos_w = math.cos(w)
        sin_w = math.sin(w)
        cos_2w = math.cos(2 * w)
        sin_2w = math.sin(2 * w)
        num = math.sqrt(
            (b0 + b1 * cos_w + b2 * cos_2w) ** 2 + (b1 * sin_w + b2 * sin_2w) ** 2
        )
        den = math.sqrt(
            (a0 + a1 * cos_w + a2 * cos_2w) ** 2 + (a1 * sin_w + a2 * sin_2w) ** 2
        )
        if den == 0:
            return 0.0
        return 20.0 * math.log10(num / den)

    # ---------- 序列化（与 Android Gson 字段名一致，便于互导）----------
    def to_json_dict(self) -> dict:
        return {
            "fcList": [int(v) for v in self.fc_list],
            "gainList": [round(float(v), 1) for v in self.gain_list],
            "name": self.name,
            "offset": int(self.offset),
            "qList": [float(v) for v in self.q_list],
            "typeList": [int(v) for v in self.type_list],
        }

    @classmethod
    def from_json_dict(cls, d: dict) -> "EQData":
        e = cls()
        if d.get("fcList"):
            e.fc_list = [int(v) for v in d["fcList"]]
        if d.get("qList"):
            e.q_list = [float(v) for v in d["qList"]]
        if d.get("gainList"):
            e.gain_list = [float(v) for v in d["gainList"]]
        if d.get("typeList"):
            e.type_list = [int(v) for v in d["typeList"]]
        e.offset = int(d.get("offset", 0))
        e.name = d.get("name", "") or ""
        return e

    def deepcopy(self) -> "EQData":
        return EQData(
            fc_list=list(self.fc_list),
            q_list=list(self.q_list),
            gain_list=list(self.gain_list),
            type_list=list(self.type_list),
            offset=self.offset,
            name=self.name,
        )

    def reset_gains(self):
        self.gain_list = [0.0] * len(self.gain_list)
        self.offset = 0
