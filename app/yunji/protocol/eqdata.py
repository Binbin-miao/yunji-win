# -*- coding: utf-8 -*-
"""EQ 数据模型与协议打包（逐字节对照 Android 版 EQData.kt / EQcoeffData.kt 实现）

关键点（务必保持与 Android 版完全一致）：
- biquad 系数由 RBJ peaking EQ 公式以 96 kHz 采样率计算
- 系数以 int32 小端（Q30 定点，×2^30 四舍五入）打包，共 20 字节
- 增益以 [小数×256, 整数] 两个字节打包
- 单波段包总长 37 字节

关于滤波器类型（type）
----------------------
逆向确认：官方 Android 版 `typeList` 是**死数据** —— 初始化为全 2，仅参与 JSON
导入导出的字段搬运，系数计算只有 `computePeak` 一个函数，发包时硬编码写入 2。
即官方从未向设备发送过 2 以外的类型，硬件是否支持 shelf **完全未知**。

因此：默认恒为 peaking(2)，行为与官方完全一致；shelf 仅在用户显式开启
实验性选项后才会被写入，且编码值是推测值（见 config.EQ_TYPE_*）。
"""
import math
from dataclasses import dataclass, field
from typing import List, Sequence

from ..config import (
    EQ_DEVICE_SAMPLE_RATE,
    EQ_DISPLAY_SAMPLE_RATE,
    EQ_TYPE_HIGH_SHELF,
    EQ_TYPE_LOW_SHELF,
    EQ_TYPE_PEAKING,
    PROEQ_DEFAULT_FREQ,
    PROEQ_DEFAULT_Q,
    PROEQ_DEFAULT_TYPE,
)

TWO_POW_30 = float(1 << 30)
TAU = 6.283185307179586


def _java_round(x: float) -> int:
    """Java Math.round(double) = floor(x + 0.5)"""
    return int(math.floor(x + 0.5))


def _int32_le_bytes(v: int) -> bytes:
    v &= 0xFFFFFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF])


def _int16_le_bytes(v: int) -> bytes:
    v &= 0xFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF])


def type_name(t: int) -> str:
    return {EQ_TYPE_PEAKING: "峰值", EQ_TYPE_LOW_SHELF: "低架",
            EQ_TYPE_HIGH_SHELF: "高架"}.get(int(t), f"未知({t})")


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
        coeff = self._compute_band(self.fc_list[index], self.q_list[index],
                                   self.gain_list[index], self.type_list[index])
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
                + bytes([self.type_list[index] & 0xFF, self.offset & 0xFF, 0x00]))

    def _compute_band(self, freq: float, q: float, gain: float, ftype: int) -> bytes:
        """按滤波器类型生成 Q30 int32 LE ×5 = 20 字节系数"""
        b0, b1, b2, a1, a2 = band_coeffs_normalized(freq, q, gain, ftype,
                                                    EQ_DEVICE_SAMPLE_RATE)
        ints = [
            _java_round(b0 * TWO_POW_30),
            _java_round(b1 * TWO_POW_30),
            _java_round(b2 * TWO_POW_30),
            _java_round(-a1 * TWO_POW_30),
            _java_round(-a2 * TWO_POW_30),
        ]
        out = b""
        for v in ints:
            out += _int32_le_bytes(v)
        return out

    def _compute_peak(self, freq: float, q: float, gain: float) -> bytes:
        """兼容旧接口：peaking 系数"""
        return self._compute_band(freq, q, gain, EQ_TYPE_PEAKING)

    # ---------- 曲线 ----------
    def band_coeffs(self, sample_rate: float = EQ_DISPLAY_SAMPLE_RATE):
        """预计算 8 段系数（与求值频点无关），供批量绘制复用"""
        return [band_coeffs_normalized(self.fc_list[i], self.q_list[i],
                                       self.gain_list[i], self.type_list[i],
                                       sample_rate)
                for i in range(len(self.fc_list))]

    def response_curve(self, freqs: Sequence[float]) -> List[float]:
        """批量求值：系数只算一次，避免逐点重算三角函数"""
        coeffs = self.band_coeffs()
        out = []
        for f in freqs:
            total = 0.0
            for c in coeffs:
                total += response_db_from_coeffs(f, c, EQ_DISPLAY_SAMPLE_RATE)
            out.append(total)
        return out

    def response_db(self, freq: float) -> float:
        """单点响应（保留旧接口）"""
        total = 0.0
        for c in self.band_coeffs():
            total += response_db_from_coeffs(freq, c, EQ_DISPLAY_SAMPLE_RATE)
        return total

    @staticmethod
    def _peak_response(freq: float, band_freq: float, q: float, gain: float) -> float:
        """兼容旧接口：单段 peaking 响应"""
        c = band_coeffs_normalized(band_freq, q, gain, EQ_TYPE_PEAKING,
                                   EQ_DISPLAY_SAMPLE_RATE)
        return response_db_from_coeffs(freq, c, EQ_DISPLAY_SAMPLE_RATE)

    # ---------- 增益分析（防削波）----------
    def peak_gain_db(self, n: int = 400) -> float:
        """返回 20Hz-20kHz 上 8 段叠加后的最大正增益（dB）

        用于推荐 offset 补偿。仅统计正值；全负则返回 0。
        """
        if n < 2:
            n = 2
        f_min, f_max = 20.0, 20000.0
        ratio = math.log10(f_max / f_min)
        freqs = [f_min * math.pow(10.0, (i / (n - 1.0)) * ratio) for i in range(n)]
        peak = 0.0
        for db in self.response_curve(freqs):
            if db > peak:
                peak = db
        return peak

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


# ---------------- 系数与响应（模块级函数，便于复用与测试）----------------
def band_coeffs_normalized(freq: float, q: float, gain: float, ftype: int,
                           sample_rate: float):
    """返回归一化后的 (b0, b1, b2, a1, a2)，a0 恒为 1

    - peaking(2)：与 Android `computePeak` 完全一致
    - low/high shelf：RBJ Audio EQ Cookbook，alpha = sin(w0)/(2Q)
      （与 Web Audio BiquadFilterNode 的 lowshelf/highshelf 同式）
    """
    if q <= 0:
        q = 0.75
    w0 = (TAU * freq) / sample_rate
    cos_w0 = math.cos(w0)
    sin_w0 = math.sin(w0)
    a = math.pow(10.0, gain / 40.0)      # = sqrt(10^(gain/20))
    alpha = sin_w0 / (2.0 * q)
    sqrt_a = math.sqrt(a)

    if ftype == EQ_TYPE_LOW_SHELF:
        b0 = a * ((a + 1.0) - (a - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha)
        b1 = 2.0 * a * ((a - 1.0) - (a + 1.0) * cos_w0)
        b2 = a * ((a + 1.0) - (a - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha)
        a0 = (a + 1.0) + (a - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha
        a1 = -2.0 * ((a - 1.0) + (a + 1.0) * cos_w0)
        a2 = (a + 1.0) + (a - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha
    elif ftype == EQ_TYPE_HIGH_SHELF:
        b0 = a * ((a + 1.0) + (a - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha)
        b1 = -2.0 * a * ((a - 1.0) + (a + 1.0) * cos_w0)
        b2 = a * ((a + 1.0) + (a - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha)
        a0 = (a + 1.0) - (a - 1.0) * cos_w0 + 2.0 * sqrt_a * alpha
        a1 = 2.0 * ((a - 1.0) - (a + 1.0) * cos_w0)
        a2 = (a + 1.0) - (a - 1.0) * cos_w0 - 2.0 * sqrt_a * alpha
    else:
        # peaking（与 Android computePeak 逐项对应）
        d2 = alpha * a
        d3 = alpha / a
        d4 = d3 + 1.0
        return ((d2 + 1.0) / d4,
                (cos_w0 * -2.0) / d4,
                (1.0 - d2) / d4,
                (cos_w0 * -2.0) / d4,
                (1.0 - d3) / d4)

    if a0 == 0.0:
        return (1.0, 0.0, 0.0, 0.0, 0.0)
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def response_db_from_coeffs(freq: float, c, sample_rate: float) -> float:
    """由归一化系数计算某频点的幅频响应（dB）"""
    b0, b1, b2, a1, a2 = c
    w = (freq * TAU) / sample_rate
    cos_w = math.cos(w)
    sin_w = math.sin(w)
    cos_2w = math.cos(2.0 * w)
    sin_2w = math.sin(2.0 * w)
    num = math.hypot(b0 + b1 * cos_w + b2 * cos_2w, b1 * sin_w + b2 * sin_2w)
    den = math.hypot(1.0 + a1 * cos_w + a2 * cos_2w, a1 * sin_w + a2 * sin_2w)
    if den == 0.0:
        return 0.0
    if num == 0.0:
        return -120.0
    return 20.0 * math.log10(num / den)


def log_freqs(f_min: float = 20.0, f_max: float = 20000.0, n: int = 200) -> List[float]:
    """对数轴采样频点，供曲线绘制复用"""
    if n < 2:
        n = 2
    ratio = math.log10(f_max / f_min)
    return [f_min * math.pow(10.0, (i / (n - 1.0)) * ratio) for i in range(n)]
