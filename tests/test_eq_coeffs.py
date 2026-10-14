# -*- coding: utf-8 -*-
"""EQ 系数与响应的数值回归测试

最重要的一条：EQData 重构（系数预计算 + 支持 shelf）之后，
**peaking 类型的字节输出必须与重构前逐字节一致** —— 否则真机行为会变。

这里把重构前的实现原样复制为参照实现，做逐点比对。
"""
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

from yunji.config import (  # noqa: E402
    EQ_DISPLAY_SAMPLE_RATE,
    EQ_TYPE_HIGH_SHELF,
    EQ_TYPE_LOW_SHELF,
    EQ_TYPE_PEAKING,
    TTGK_MAX_EQ_GAIN,
    TTGK_MIN_EQ_GAIN,
)
from yunji.protocol.eqdata import (  # noqa: E402
    EQData,
    band_coeffs_normalized,
    log_freqs,
    response_db_from_coeffs,
)

TAU = 6.283185307179586


# ---------------- 重构前的参照实现（原样复制，勿改）----------------
def old_java_round(x):
    return int(math.floor(x + 0.5))


def old_int32_le(v):
    v &= 0xFFFFFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF])


def old_int16_le(v):
    v &= 0xFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF])


def old_compute_peak(freq, q, gain):
    sqrt_a = math.sqrt(math.pow(10.0, gain / 20.0))
    w = (TAU * freq) / 96000.0
    alpha = math.sin(w) / (2.0 * q)
    d2 = alpha * sqrt_a
    d3 = alpha / sqrt_a
    d4 = d3 + 1.0
    cos_w = math.cos(w)
    b = [(d2 + 1.0) / d4, (cos_w * -2.0) / d4, (1.0 - d2) / d4]
    a1 = (cos_w * -2.0) / d4
    a2 = (1.0 - d3) / d4
    ints = [
        old_java_round(b[0] * 1073741824.0),
        old_java_round(b[1] * 1073741824.0),
        old_java_round(b[2] * 1073741824.0),
        old_java_round(-a1 * 1073741824.0),
        old_java_round(-a2 * 1073741824.0),
    ]
    out = b""
    for v in ints:
        out += old_int32_le(v)
    return out


def old_band_packet(data, index):
    coeff = old_compute_peak(data.fc_list[index], data.q_list[index], data.gain_list[index])
    fc = old_int16_le(data.fc_list[index])
    gain = data.gain_list[index]
    floor_v = math.floor(gain)
    frac_v = int((gain - floor_v) * 256) & 0xFF
    gain_bytes = bytes([frac_v, int(floor_v) & 0xFF])
    head = bytes([0x4B, 0x01, 0x09, 0x18, 0x00, index, 0x00, 0x00])
    return (head + coeff + fc + b"\xC0\x00" + gain_bytes
            + bytes([0x02, data.offset & 0xFF, 0x00]))


def old_peak_response(freq, band_freq, q, gain):
    a = math.pow(10.0, gain / 40.0)
    w0 = (band_freq * TAU) / EQ_DISPLAY_SAMPLE_RATE
    alpha = math.sin(w0) / (q * 2.0)
    b0 = 1.0 + alpha * a
    b1 = -2.0 * math.cos(w0)
    b2 = 1.0 - alpha * a
    a0 = 1.0 + alpha / a
    a1 = -2.0 * math.cos(w0)
    a2 = 1.0 - alpha / a
    w = (freq * TAU) / EQ_DISPLAY_SAMPLE_RATE
    cos_w = math.cos(w)
    sin_w = math.sin(w)
    cos_2w = math.cos(2 * w)
    sin_2w = math.sin(2 * w)
    num = math.sqrt((b0 + b1 * cos_w + b2 * cos_2w) ** 2 + (b1 * sin_w + b2 * sin_2w) ** 2)
    den = math.sqrt((a0 + a1 * cos_w + a2 * cos_2w) ** 2 + (a1 * sin_w + a2 * sin_2w) ** 2)
    if den == 0:
        return 0.0
    return 20.0 * math.log10(num / den)


def old_response_db(data, freq):
    total = 0.0
    for i in range(len(data.fc_list)):
        total += old_peak_response(freq, data.fc_list[i], data.q_list[i], data.gain_list[i])
    return total


# ---------------- 测试 ----------------
class TestByteCompat(unittest.TestCase):
    """字节级兼容：peaking 包必须与重构前完全一致"""

    def _sample(self):
        d = EQData()
        d.fc_list = [25, 63, 160, 400, 1000, 2500, 6300, 12500]
        d.q_list = [0.5, 0.75, 1.2, 2.0, 3.5, 6.0, 8.0, 0.9]
        d.gain_list = [-12.0, -7.3, -2.5, -0.4, 0.0, 3.7, 8.2, 12.0]
        d.offset = -3
        return d

    def test_band_packet_identical(self):
        d = self._sample()
        for i in range(8):
            self.assertEqual(d.band_packet(i), old_band_packet(d, i),
                             f"第 {i} 段包体与重构前不一致")

    def test_band_packet_offset_range(self):
        d = self._sample()
        for off in (-8, -1, 0, 2, 4):
            d.offset = off
            for i in range(8):
                self.assertEqual(d.band_packet(i), old_band_packet(d, i))

    def test_band_packet_length(self):
        d = self._sample()
        for i in range(8):
            self.assertEqual(len(d.band_packet(i)), 37)

    def test_band_packet_type_byte_default(self):
        """默认 type 全为 2 时，包内 type 字节应为 2"""
        d = self._sample()
        for i in range(8):
            self.assertEqual(d.band_packet(i)[34], 2)

    def test_gain_quantization_edge(self):
        """负增益的小数部分必须按 floor 语义处理（Java 行为）"""
        d = self._sample()
        for g in (-12.0, -0.1, -0.5, 0.0, 0.1, 0.5, 11.9):
            d.gain_list = [g] * 8
            self.assertEqual(d.band_packet(0), old_band_packet(d, 0), f"增益 {g} 不一致")


class TestResponseRegression(unittest.TestCase):
    """曲线数值回归：新旧算法在 1000 个频点上必须一致"""

    def test_response_db_matches_old(self):
        d = EQData()
        d.fc_list = [22, 125, 300, 500, 1400, 2800, 5500, 10000]
        d.q_list = [0.75, 3.5, 6.5, 3.6, 1.8, 8.0, 5.0, 4.0]
        d.gain_list = [6.0, 4.5, -3.0, 1.5, 2.5, -1.0, 3.5, 5.0]

        freqs = log_freqs(20.0, 20000.0, 1000)
        worst = 0.0
        for f in freqs:
            worst = max(worst, abs(d.response_db(f) - old_response_db(d, f)))
        self.assertLess(worst, 1e-9, f"新旧响应最大偏差 {worst:.3e} dB")

    def test_response_curve_batch_matches_single(self):
        """批量接口与单点接口结果必须一致"""
        d = EQData()
        d.gain_list = [3.0, -2.0, 1.0, 0.0, -1.5, 4.0, 2.0, -3.0]
        freqs = log_freqs(20.0, 20000.0, 300)
        batch = d.response_curve(freqs)
        for f, b in zip(freqs, batch):
            self.assertAlmostEqual(b, d.response_db(f), places=10)

    def test_flat_curve_is_zero(self):
        d = EQData()
        d.gain_list = [0.0] * 8
        for db in d.response_curve(log_freqs(20.0, 20000.0, 100)):
            self.assertAlmostEqual(db, 0.0, places=9)


class TestPeakingMath(unittest.TestCase):
    """peaking 滤波器的解析性质"""

    def test_center_gain_equals_setting(self):
        """峰值滤波器在中心频率处的增益应精确等于设定值"""
        for gain in (-12.0, -6.0, -1.5, 0.5, 3.0, 12.0):
            c = band_coeffs_normalized(1000.0, 1.0, gain, EQ_TYPE_PEAKING,
                                       EQ_DISPLAY_SAMPLE_RATE)
            self.assertAlmostEqual(response_db_from_coeffs(1000.0, c,
                                                           EQ_DISPLAY_SAMPLE_RATE),
                                   gain, places=6)

    def test_far_field_flat(self):
        """远离中心频率处应趋近 0 dB"""
        c = band_coeffs_normalized(1000.0, 2.0, 6.0, EQ_TYPE_PEAKING,
                                   EQ_DISPLAY_SAMPLE_RATE)
        self.assertLess(abs(response_db_from_coeffs(20.0, c, EQ_DISPLAY_SAMPLE_RATE)), 0.2)
        self.assertLess(abs(response_db_from_coeffs(20000.0, c, EQ_DISPLAY_SAMPLE_RATE)), 0.5)


class TestShelfMath(unittest.TestCase):
    """低架/高架滤波器的解析性质（F8）"""

    def test_low_shelf_plateau(self):
        """低架：远低于 fc 处应达到设定增益，远高于 fc 处应趋近 0"""
        gain = 6.0
        c = band_coeffs_normalized(1000.0, 0.75, gain, EQ_TYPE_LOW_SHELF,
                                   EQ_DISPLAY_SAMPLE_RATE)
        low = response_db_from_coeffs(25.0, c, EQ_DISPLAY_SAMPLE_RATE)
        high = response_db_from_coeffs(20000.0, c, EQ_DISPLAY_SAMPLE_RATE)
        self.assertAlmostEqual(low, gain, delta=0.6)
        self.assertAlmostEqual(high, 0.0, delta=0.6)

    def test_high_shelf_plateau(self):
        gain = -7.0
        c = band_coeffs_normalized(1000.0, 0.75, gain, EQ_TYPE_HIGH_SHELF,
                                   EQ_DISPLAY_SAMPLE_RATE)
        low = response_db_from_coeffs(25.0, c, EQ_DISPLAY_SAMPLE_RATE)
        high = response_db_from_coeffs(20000.0, c, EQ_DISPLAY_SAMPLE_RATE)
        self.assertAlmostEqual(low, 0.0, delta=0.6)
        self.assertAlmostEqual(high, gain, delta=0.6)

    def test_shelf_center_is_half_gain(self):
        """在中心频率处，架式滤波器约为设定增益的一半"""
        for t, gain in ((EQ_TYPE_LOW_SHELF, 8.0), (EQ_TYPE_HIGH_SHELF, -8.0)):
            c = band_coeffs_normalized(1000.0, 0.75, gain, t,
                                       EQ_DISPLAY_SAMPLE_RATE)
            mid = response_db_from_coeffs(1000.0, c, EQ_DISPLAY_SAMPLE_RATE)
            self.assertAlmostEqual(mid, gain / 2.0, delta=0.9)

    def test_shelf_is_stable(self):
        """系数必须构成稳定滤波器：极点须在单位圆内

        这是 shelf 能否安全下发给硬件的关键前提 —— 不稳定的 biquad
        会产生自激振荡（刺耳噪音）。
        """
        for t in (EQ_TYPE_LOW_SHELF, EQ_TYPE_HIGH_SHELF):
            for gain in (-12.0, -6.0, 0.0, 6.0, 12.0):
                for fc in (30.0, 200.0, 1000.0, 5000.0, 12000.0):
                    b0, b1, b2, a1, a2 = band_coeffs_normalized(
                        fc, 0.75, gain, t, 96000.0)
                    # 极点：z² + a1 z + a2 = 0
                    disc = a1 * a1 - 4.0 * a2
                    if disc >= 0:
                        r1 = (-a1 + math.sqrt(disc)) / 2.0
                        r2 = (-a1 - math.sqrt(disc)) / 2.0
                        radius = max(abs(r1), abs(r2))
                    else:
                        radius = math.sqrt(a2)
                    self.assertLess(radius, 1.0,
                                    f"类型{t} 增益{gain} fc={fc} 极点半径 {radius:.4f} >= 1")


class TestPeakGain(unittest.TestCase):
    """F4 增益补偿所依赖的峰值增益计算"""

    def test_flat_has_no_peak(self):
        d = EQData()
        d.gain_list = [0.0] * 8
        self.assertAlmostEqual(d.peak_gain_db(), 0.0, places=6)

    def test_all_cut_has_no_peak(self):
        d = EQData()
        d.gain_list = [-3.0] * 8
        self.assertAlmostEqual(d.peak_gain_db(), 0.0, places=6)

    def test_single_boost_detected(self):
        """单段 +6dB（Q=0.75）的峰值应略低于 6dB（相邻段有轻微叠加）"""
        d = EQData()
        d.gain_list = [0.0] * 8
        d.gain_list[4] = 6.0
        peak = d.peak_gain_db()
        self.assertGreater(peak, 5.5)
        self.assertLessEqual(peak, 6.05)

    def test_overlapping_boosts_accumulate(self):
        d = EQData()
        d.gain_list = [6.0] * 8
        self.assertGreater(d.peak_gain_db(), 6.0)

    def test_peak_within_device_range(self):
        """8 段全部拉满时峰值会因频段重叠而远超单段增益

        这正是 F4 需要给出「无法完全补偿」警告的场景：
        峰值（约 +27 dB）远超 offset 下限（-8 dB）。
        """
        d = EQData()
        d.gain_list = [float(TTGK_MAX_EQ_GAIN)] * 8
        peak = d.peak_gain_db()
        self.assertGreater(peak, float(TTGK_MAX_EQ_GAIN))
        self.assertLess(peak, 40.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
