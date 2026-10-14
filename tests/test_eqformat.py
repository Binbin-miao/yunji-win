# -*- coding: utf-8 -*-
"""EQ 导入格式解析测试（F2）

覆盖社区实际流通的四种格式，以及格式嗅探与错误输入处理。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

from yunji.config import (  # noqa: E402
    EQ_TYPE_HIGH_SHELF,
    EQ_TYPE_LOW_SHELF,
    EQ_TYPE_PEAKING,
)
from yunji.protocol.eqformat import (  # noqa: E402
    parse_eq_text,
    to_apo_text,
    to_native_json,
)

APO_SAMPLE = """\
Preamp: -6.0 dB
Filter 1: ON PK Fc 105 Hz Gain -3.2 dB Q 0.70
Filter 2: ON LSC Fc 105 Hz Gain 5.5 dB Q 0.70
Filter 3: ON HSC Fc 10000 Hz Gain -2.0 dB Q 0.70
Filter 4: OFF PK Fc 500 Hz Gain 4.0 dB Q 1.00
Filter 5: ON PK Fc 1000 Hz Gain 1.5 dB Q 2.00
"""

GRAPHIC_SAMPLE = (
    "GraphicEQ: 20 -3.5; 25 -3.2; 31 -2.9; 40 -2.5; 50 -2.1; 63 -1.6; "
    "80 -1.0; 100 -0.5; 125 0.0; 160 0.6; 200 1.2; 250 1.8; 315 2.4; "
    "400 3.0; 500 3.4; 630 3.8; 800 4.1; 1000 4.3; 1250 4.2; 1600 3.9"
)

WAVELET_SAMPLE = """\
{"graphicEQ": [[20,-3.5],[25,-3.2],[31,-2.9],[40,-2.5],[50,-2.1],
[63,-1.6],[80,-1.0],[100,-0.5],[125,0.0],[160,0.6],[200,1.2],
[250,1.8],[315,2.4],[400,3.0],[500,3.4],[630,3.8],[800,4.1],[1000,4.3]]}
"""

NATIVE_SAMPLE = """\
{"bands": [
  {"freq": 60,  "q": 0.75, "gain": 4.0, "type": 2},
  {"freq": 150, "q": 1.20, "gain": -2.5, "type": 2},
  {"freq": 1000,"q": 2.00, "gain": 1.0, "type": 2}
], "preamp": -3.0}
"""


class TestApoParsing(unittest.TestCase):
    def test_basic(self):
        r = parse_eq_text(APO_SAMPLE)
        self.assertEqual(r.fmt, "Equalizer APO")
        self.assertAlmostEqual(r.preamp, -6.0)
        # OFF 的那条应被跳过 → 4 条有效
        self.assertEqual(len(r.bands), 4)

    def test_types_mapped(self):
        r = parse_eq_text(APO_SAMPLE)
        types = [b.type for b in r.bands]
        self.assertIn(EQ_TYPE_PEAKING, types)
        self.assertIn(EQ_TYPE_LOW_SHELF, types)
        self.assertIn(EQ_TYPE_HIGH_SHELF, types)

    def test_values(self):
        r = parse_eq_text(APO_SAMPLE)
        first = r.bands[0]
        self.assertAlmostEqual(first.freq, 105.0)
        self.assertAlmostEqual(first.gain, -3.2)
        self.assertAlmostEqual(first.q, 0.70)

    def test_off_filter_skipped(self):
        r = parse_eq_text(APO_SAMPLE)
        self.assertNotIn(500.0, [b.freq for b in r.bands])

    def test_bandwidth_becomes_q(self):
        r = parse_eq_text("Filter 1: ON PK Fc 1000 Hz Gain 3 dB BW 1.0")
        self.assertEqual(len(r.bands), 1)
        self.assertGreater(r.bands[0].q, 0.5)
        self.assertLess(r.bands[0].q, 2.0)

    def test_comments_and_blanks_ignored(self):
        r = parse_eq_text("# 注释\n\nFilter 1: ON PK Fc 200 Hz Gain 1 dB Q 1.0\n")
        self.assertEqual(len(r.bands), 1)

    def test_missing_freq_skipped(self):
        r = parse_eq_text("Filter 1: ON PK Gain 3 dB Q 1.0")
        self.assertEqual(len(r.bands), 0)


class TestGraphicEqParsing(unittest.TestCase):
    def test_basic(self):
        r = parse_eq_text(GRAPHIC_SAMPLE)
        self.assertEqual(r.fmt, "GraphicEQ")
        self.assertGreater(len(r.graphic), 15)
        self.assertEqual(r.graphic[0][0], 20.0)

    def test_sorted(self):
        pts = r = parse_eq_text(GRAPHIC_SAMPLE).graphic
        self.assertEqual(pts, sorted(pts, key=lambda p: p[0]))

    def test_newline_separated(self):
        text = "GraphicEQ: 20 -3.5\n25 -3.2\n31 -2.9\n"
        r = parse_eq_text(text)
        self.assertEqual(len(r.graphic), 3)

    def test_semicolon_only(self):
        r = parse_eq_text("GraphicEQ: 20 -3.5; 25 -3.2")
        self.assertEqual(len(r.graphic), 2)


class TestWaveletParsing(unittest.TestCase):
    def test_basic(self):
        r = parse_eq_text(WAVELET_SAMPLE)
        self.assertEqual(r.fmt, "Wavelet")
        self.assertEqual(len(r.graphic), 18)
        self.assertEqual(r.graphic[0], (20.0, -3.5))

    def test_bad_json_returns_empty(self):
        r = parse_eq_text('{"graphicEQ": not-json}')
        self.assertTrue(r.is_empty)

    def test_non_list_points_ignored(self):
        r = parse_eq_text('{"graphicEQ": [[20,-3.5], "bad", [25,-3.2]]}')
        self.assertEqual(len(r.graphic), 2)


class TestNativeParsing(unittest.TestCase):
    def test_basic(self):
        r = parse_eq_text(NATIVE_SAMPLE)
        self.assertEqual(r.fmt, "本工具格式")
        self.assertEqual(len(r.bands), 3)
        self.assertAlmostEqual(r.preamp, -3.0)

    def test_values(self):
        r = parse_eq_text(NATIVE_SAMPLE)
        self.assertEqual(r.bands[0].freq, 60.0)
        self.assertEqual(r.bands[1].gain, -2.5)

    def test_native_takes_priority_over_wavelet(self):
        """两者都是 JSON，应优先识别为原生格式"""
        text = '{"bands":[{"freq":100,"q":1,"gain":2}],"graphicEQ":[[20,-1]]}'
        r = parse_eq_text(text)
        self.assertEqual(r.fmt, "本工具格式")
        self.assertEqual(len(r.bands), 1)

    def test_missing_fields_use_defaults(self):
        r = parse_eq_text('{"bands":[{"freq":100}]}')
        self.assertEqual(len(r.bands), 1)
        self.assertEqual(r.bands[0].gain, 0.0)
        self.assertGreater(r.bands[0].q, 0)


class TestEdgeCases(unittest.TestCase):
    def test_empty(self):
        self.assertTrue(parse_eq_text("").is_empty)
        self.assertTrue(parse_eq_text("   \n  ").is_empty)

    def test_garbage(self):
        self.assertTrue(parse_eq_text("hello world, this is not eq data").is_empty)

    def test_broken_json(self):
        self.assertTrue(parse_eq_text("{broken json").is_empty)

    def test_unknown_filter_type_skipped(self):
        r = parse_eq_text("Filter 1: ON LPQ Fc 1000 Hz Gain 3 dB Q 1.0")
        self.assertEqual(len(r.bands), 0)


class TestExportRoundTrip(unittest.TestCase):
    def test_apo_roundtrip(self):
        src = parse_eq_text(APO_SAMPLE)
        text = to_apo_text(src.bands, src.preamp)
        again = parse_eq_text(text)
        self.assertEqual(len(again.bands), len(src.bands))
        for a, b in zip(src.bands, again.bands):
            self.assertAlmostEqual(a.freq, b.freq, places=3)
            self.assertAlmostEqual(a.gain, b.gain, places=1)
            self.assertAlmostEqual(a.q, b.q, places=2)
            self.assertEqual(a.type, b.type)

    def test_native_roundtrip(self):
        src = parse_eq_text(NATIVE_SAMPLE)
        text = to_native_json(src.bands, src.preamp)
        again = parse_eq_text(text)
        self.assertEqual(len(again.bands), len(src.bands))
        for a, b in zip(src.bands, again.bands):
            self.assertAlmostEqual(a.gain, b.gain, places=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
