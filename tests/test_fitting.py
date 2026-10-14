# -*- coding: utf-8 -*-
"""曲线拟合测试（F3）

核心验收：把任意段数的目标曲线拟合为 8 段后，
拟合结果与目标的偏差应足够小（RMS < 1 dB 量级）。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

from yunji.config import (  # noqa: E402
    EQ_DISPLAY_SAMPLE_RATE,
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
from yunji.protocol.eqformat import parse_eq_text  # noqa: E402
from yunji.protocol.fitting import (  # noqa: E402
    build_target_curve,
    fit_parsed,
)

# AutoEQ 风格的 10 段配置（耳塞常见）
APO_10BAND = """\
Preamp: -5.0 dB
Filter 1: ON LSC Fc 105 Hz Gain 5.5 dB Q 0.70
Filter 2: ON PK Fc 220 Hz Gain -2.1 dB Q 1.20
Filter 3: ON PK Fc 560 Hz Gain 1.4 dB Q 1.80
Filter 4: ON PK Fc 1200 Hz Gain -1.8 dB Q 2.00
Filter 5: ON PK Fc 2100 Hz Gain 2.6 dB Q 1.50
Filter 6: ON PK Fc 3000 Hz Gain 4.2 dB Q 2.20
Filter 7: ON PK Fc 4500 Hz Gain -3.0 dB Q 3.00
Filter 8: ON PK Fc 6500 Hz Gain 1.9 dB Q 2.50
Filter 9: ON PK Fc 9000 Hz Gain -2.4 dB Q 2.00
Filter 10: ON HSC Fc 10000 Hz Gain 3.2 dB Q 0.70
"""


def response_of_bands(bands, freqs):
    total = [0.0] * len(freqs)
    for b in bands:
        c = band_coeffs_normalized(b.freq, b.q, b.gain, b.type,
                                   EQ_DISPLAY_SAMPLE_RATE)
        for i, f in enumerate(freqs):
            total[i] += response_db_from_coeffs(f, c, EQ_DISPLAY_SAMPLE_RATE)
    return total


class TestFittingQuality(unittest.TestCase):
    def test_ten_band_apo_fits_within_1db(self):
        """10 段配置拟合到 8 段后，RMS 偏差应小于 1 dB"""
        parsed = parse_eq_text(APO_10BAND)
        self.assertEqual(len(parsed.bands), 10)
        result = fit_parsed(parsed)
        self.assertEqual(len(result.gains), 8)
        self.assertTrue(result.needs_fit)
        self.assertLess(result.rms_error, 1.0,
                        f"RMS 偏差过大: {result.rms_error:.3f} dB")
        self.assertLess(result.max_error, 3.0,
                        f"最大偏差过大: {result.max_error:.3f} dB")

    def test_graphic_eq_fits(self):
        """GraphicEQ 频响折线也能拟合"""
        text = ("GraphicEQ: " + "; ".join(
            f"{f} {v}" for f, v in [
                (20, -4.0), (50, -3.0), (100, -1.0), (200, 0.5),
                (500, 1.5), (1000, 0.0), (2000, 3.0), (3000, 5.0),
                (5000, 2.0), (8000, -1.0), (10000, -2.0)]))
        parsed = parse_eq_text(text)
        self.assertTrue(parsed.graphic)
        result = fit_parsed(parsed)
        self.assertLess(result.rms_error, 1.5,
                        f"RMS 偏差过大: {result.rms_error:.3f} dB")

    def test_fitted_gains_within_device_range(self):
        """拟合结果必须落在设备可写入的增益范围内"""
        parsed = parse_eq_text(APO_10BAND)
        result = fit_parsed(parsed)
        for g in result.gains:
            self.assertGreaterEqual(g, float(TTGK_MIN_EQ_GAIN))
            self.assertLessEqual(g, float(TTGK_MAX_EQ_GAIN))

    def test_gains_quantized_to_0p1db(self):
        parsed = parse_eq_text(APO_10BAND)
        result = fit_parsed(parsed)
        for g in result.gains:
            self.assertAlmostEqual(round(g, 1), g, places=9)


class TestCenterSelection(unittest.TestCase):
    def test_few_bands_keep_source_frequencies(self):
        """源段数 <= 8 时沿用源频率（保真最高）"""
        parsed = parse_eq_text(
            '{"bands":[{"freq":80,"q":1,"gain":3},{"freq":900,"q":2,"gain":-2}]}')
        result = fit_parsed(parsed)
        self.assertEqual(len(result.centers), 2)
        self.assertAlmostEqual(result.centers[0], 80.0)
        self.assertAlmostEqual(result.centers[1], 900.0)

    def test_many_bands_use_log_grid(self):
        parsed = parse_eq_text(APO_10BAND)
        result = fit_parsed(parsed)
        self.assertEqual(len(result.centers), 8)
        # 对数轴均匀 → 相邻比值应基本恒定
        ratios = [result.centers[i + 1] / result.centers[i] for i in range(7)]
        self.assertLess(max(ratios) - min(ratios), 0.01)


class TestTargetCurve(unittest.TestCase):
    def test_graphic_target_interpolated(self):
        parsed = parse_eq_text("GraphicEQ: 20 -6; 20000 6")
        freqs = [20.0, 1000.0, 20000.0]
        vals = build_target_curve(parsed, freqs)
        self.assertAlmostEqual(vals[0], -6.0)
        self.assertAlmostEqual(vals[2], 6.0)
        self.assertGreater(vals[1], -6.0)
        self.assertLess(vals[1], 6.0)

    def test_band_target_summed(self):
        parsed = parse_eq_text('{"bands":[{"freq":1000,"q":1,"gain":6}]}')
        freqs = log_freqs(20.0, 20000.0, 50)
        vals = build_target_curve(parsed, freqs)
        peak = max(vals)
        self.assertAlmostEqual(peak, 6.0, delta=0.05)

    def test_empty_parsed_gives_flat(self):
        from yunji.protocol.eqformat import ParsedEQ
        vals = build_target_curve(ParsedEQ(), [20.0, 1000.0, 20000.0])
        self.assertEqual(vals, [0.0, 0.0, 0.0])


class TestFittingEdgeCases(unittest.TestCase):
    def test_single_band(self):
        parsed = parse_eq_text('{"bands":[{"freq":500,"q":1.5,"gain":-4}]}')
        result = fit_parsed(parsed)
        self.assertEqual(len(result.gains), 1)
        self.assertAlmostEqual(result.gains[0], -4.0, delta=0.2)

    def test_flat_target_gives_zero_gains(self):
        parsed = parse_eq_text("GraphicEQ: 20 0; 200 0; 2000 0; 20000 0")
        result = fit_parsed(parsed)
        for g in result.gains:
            self.assertAlmostEqual(g, 0.0, delta=0.05)

    def test_extreme_target_is_clamped(self):
        """远超设备能力的极端目标不应产生越界增益"""
        parsed = parse_eq_text("GraphicEQ: 20 24; 200 24; 2000 24; 20000 24")
        result = fit_parsed(parsed)
        for g in result.gains:
            self.assertLessEqual(g, float(TTGK_MAX_EQ_GAIN))

    def test_target_curve_returned_for_display(self):
        parsed = parse_eq_text(APO_10BAND)
        result = fit_parsed(parsed)
        self.assertIsNotNone(result.target_curve)
        freqs, vals = result.target_curve
        self.assertEqual(len(freqs), len(vals))
        self.assertGreater(len(freqs), 100)

    def test_fit_reproduces_target_reasonably(self):
        """直接验证：拟合出的 8 段响应应贴近目标"""
        parsed = parse_eq_text(APO_10BAND)
        result = fit_parsed(parsed)
        freqs, target = result.target_curve

        fitted = EQData()
        fitted.fc_list = [int(round(c)) for c in result.centers]
        fitted.q_list = list(result.qs)
        fitted.gain_list = list(result.gains)
        fitted.type_list = list(result.types)
        got = fitted.response_curve(freqs)

        worst = max(abs(a - b) for a, b in zip(target, got))
        self.assertLess(worst, 3.0, f"拟合后最大偏差 {worst:.2f} dB")


if __name__ == "__main__":
    unittest.main(verbosity=2)
