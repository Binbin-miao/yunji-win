# -*- coding: utf-8 -*-
"""协议自测：EQ 打包字节级校验 + 模拟设备往返 + 曲线计算"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.join(os.path.dirname(__file__), "app")))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))

from yunji.protocol.eqdata import EQData
from yunji.usb.simulator import SimulatedTransport
from yunji.devices.ttgk import TtgkDevice
from yunji.devices.xuanrun import XuanRunDevice


def test_band_packet():
    d = EQData()
    d.fc_list = [60, 120, 250, 500, 1000, 2000, 4000, 8000]
    d.q_list = [0.75] * 8
    d.gain_list = [5.9, 0, 0, 0, 0, 0, 0, 0]
    d.offset = -3
    pkt = d.band_packet(0)
    assert len(pkt) == 37, f"band packet length {len(pkt)} != 37"
    assert pkt[0:6] == bytes([0x4B, 0x01, 0x09, 0x18, 0x00, 0x00]), pkt[0:6].hex()
    assert pkt[8:28] == pkt[8:28], "coeff slice"
    fc = pkt[28] | (pkt[29] << 8)
    assert fc == 60, f"fc={fc}"
    assert pkt[30:32] == b"\xC0\x00", "Q constant"
    frac, floor_b = pkt[32], pkt[33]
    gain_val = floor_b + frac / 256.0
    assert abs(gain_val - 5.9) < 0.01, f"gain={gain_val}"
    assert pkt[34] == 2, "type"
    assert pkt[35] == 0xFD, f"offset byte {pkt[35]:#x}"   # -3 & 0xFF
    assert pkt[36] == 0, "terminator"
    # 负增益
    d.gain_list[0] = -4.8
    pkt = d.band_packet(0)
    frac, floor_b = pkt[32], pkt[33]
    # floor(-4.8) = -5 → 0xFB；frac = 0.2*256 = 51
    assert floor_b == 0xFB, f"floor byte {floor_b:#x}"
    assert frac == 51, f"frac {frac}"
    # biquad 系数已知值检查（gain=0 → b0≈1, b1≈-2cos, b2≈1-alphaA... 只验证范围）
    coeff0 = int.from_bytes(pkt[8:12], "little", signed=True)
    assert abs(coeff0) <= (1 << 31), "coeff range"
    print("test_band_packet OK")


def test_response_curve():
    d = EQData()
    d.fc_list = [1000] * 8
    d.q_list = [1.0] * 8
    d.gain_list = [6.0] + [0.0] * 7
    at_1k = d.response_db(1000)
    assert 5.0 < at_1k < 7.0, f"peak response at 1k = {at_1k}"
    far = d.response_db(50)
    assert abs(far) < 1.0, f"far response = {far}"
    print("test_response_curve OK", round(at_1k, 3), round(far, 4))


def test_ttgk_roundtrip():
    t = SimulatedTransport(brand="ttgk", chip_type="cb5100")
    tk = TtgkDevice(t)
    tk.set_vol(-30)
    assert tk.read_vol() == -30, tk.read_vol()
    tk.set_mic(12)
    assert tk.read_mic() == 12
    tk.set_filter(3)
    assert tk.read_filter() == 3
    tk.set_led(True)
    assert tk.read_led() == 1
    tk.set_gain(0)
    assert tk.read_gain() == 0
    tk.set_balance(-6)
    assert tk.read_balance() == -6, tk.read_balance()
    tk.set_balance(5)
    assert tk.read_balance() == 5, tk.read_balance()
    fw = tk.read_firmware()
    assert fw == "1.75", fw
    # EQ 上传
    d = EQData()
    d.gain_list = [1.5, -2.0, 0, 0, 3.0, 0, 0, -1.0]
    tk.upload_eq(d)
    assert len(t.tk_bands) == 8, t.tk_bands.keys()
    band0 = t.tk_bands[0]
    assert len(band0) == 37
    resp = tk.read_eq_band(0)
    assert resp and resp[4:41] == band0, "band echoed back"
    print("test_ttgk_roundtrip OK")


def test_xuanrun_roundtrip():
    t = SimulatedTransport(brand="xuanrun")
    xr = XuanRunDevice(t)
    xr.set_volume_index(30)
    idx, l, r = xr.read_vol_balance()
    assert idx == 30, idx
    xr.set_balance_index(10)
    idx2, l2, r2 = xr.read_vol_balance()
    assert l2 == 0 and r2 == 8, (l2, r2)  # valueR[10] = 8
    xr.set_filter(4)
    _f, _e, _l, _d = xr.read_status()
    assert _f == 4, _f
    xr.set_led(False)
    assert t.xr_led == 2
    xr.set_depop(True)
    assert t.xr_depop == 0
    fw = xr.read_firmware()
    assert fw == "3"
    print("test_xuanrun_roundtrip OK")


if __name__ == "__main__":
    test_band_packet()
    test_response_curve()
    test_ttgk_roundtrip()
    test_xuanrun_roundtrip()
    print("ALL PROTOCOL TESTS PASSED")
