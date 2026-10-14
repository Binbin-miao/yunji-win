# -*- coding: utf-8 -*-
"""模拟设备传输层：在没有真机时完整走通 UI 与协议流程（自测 / 功能预览）。

在传输层模拟设备行为：
- TTGK：解析写命令维护状态；对读命令返回符合协议格式的 64 字节响应
- 旋润：维护状态；对 0xA0/0xA2/0xA3 读命令返回 7 字节响应
"""
from __future__ import annotations

import time

from .base import BaseTransport


class SimulatedTransport(BaseTransport):
    kind = "simulator"
    can_xuanrun = True
    can_ttgk = True

    def __init__(self, brand: str, chip_type: str = "cb5100"):
        self.brand = brand            # "xuanrun" / "ttgk"
        self.chip_type = chip_type
        # 旋润状态
        self.xr_filter = 0
        self.xr_elevel = 1
        self.xr_vol_code = 0x50     # 对应滑块 ~20
        self.xr_bal_l = 0
        self.xr_bal_r = 0
        self.xr_led = 0
        self.xr_depop = 0
        self.xr_firmware = 3
        # TTGK 状态
        self.tk_vol = 0
        self.tk_mic = 0
        self.tk_filter = 0
        self.tk_led = 0
        self.tk_gain = 1
        self.tk_bal = [0, 0]
        self.tk_firmware = "1.75"
        self.tk_bands = {}          # index -> 37 字节包
        self._last_read_cmd = None
        self._last_read_args = ()
        self.opened = True
        self.log = []

    def open(self):
        return self

    def close(self):
        pass

    # ---------------- 旋润 ----------------
    def control_out(self, data: bytes) -> int:
        if len(data) < 7 or data[0] != 0xC1:
            return -1
        cmd, a0, a1 = data[2], data[3], data[4]
        self.log.append(f"XR OUT cmd={cmd:#x} a0={a0:#x} a1={a1:#x}")
        if cmd == 0x01:
            self.xr_filter = a0
        elif cmd == 0x02:
            self.xr_elevel = a0
        elif cmd == 0x04:
            self.xr_vol_code = a0
        elif cmd == 0x05:
            self.xr_bal_l, self.xr_bal_r = a0, a1
        elif cmd == 0x06:
            self.xr_led = a0
        elif cmd == 0x07:
            self.xr_depop = a0
        return 7

    def control_in(self, data: bytes) -> bytes:
        cmd = data[2]
        self.log.append(f"XR IN cmd={cmd:#x}")
        if cmd == 0xA0:  # 固件
            return bytes([0xC1, 0xA6, 0xA0, self.xr_firmware, 0, 0, 0])
        if cmd == 0xA2:  # 音量+平衡
            return bytes([0xC1, 0xA6, 0xA2, 0,
                          self.xr_vol_code, self.xr_bal_l, self.xr_bal_r])
        if cmd == 0xA3:  # 滤波器+增益+LED+depop
            return bytes([0xC1, 0xA6, 0xA3, self.xr_filter, self.xr_elevel,
                          self.xr_led, self.xr_depop])
        return bytes([0xC1, 0xA6, cmd, 0, 0, 0, 0])

    # ---------------- TTGK ----------------
    def hid_write(self, data: bytes) -> int:
        data = bytes(data)
        if len(data) < 3 or data[0] != 0x4B:
            return -1
        flag, cmd = data[1], data[2]
        if flag == 0x80:  # 读请求：记录，稍后 hid_read 返回应答
            self._last_read_cmd = cmd
            self._last_read_args = tuple(data[3:])
            self.log.append(f"TK READ cmd={cmd:#x} args={list(data[3:])}")
            return len(data)
        if flag == 0x01:  # 写
            payload = data[4:]
            self.log.append(f"TK WRITE cmd={cmd:#x} len={data[3] if len(data) > 3 else '?'}")
            if cmd == 0x02 and len(payload) >= 2:
                self.tk_mic = int.from_bytes(payload[:2], "little", signed=True) // 256
            elif cmd == 0x03 and len(payload) >= 2:
                self.tk_vol = int.from_bytes(payload[:2], "little", signed=True) // 256
            elif cmd == 0x11:
                self.tk_filter = payload[0]
            elif cmd == 0x16 and len(payload) >= 3:
                ch = payload[0]
                self.tk_bal[ch] = int.from_bytes(payload[1:3], "little", signed=True) // 256
            elif cmd == 0x18:
                self.tk_led = payload[0]
            elif cmd == 0x19:
                self.tk_gain = payload[0]
            elif cmd == 0x09 and len(payload) >= 30:
                idx = data[5]
                self.tk_bands[idx] = data
            elif cmd == 0x0A:
                pass  # 提交
            return len(data)
        return -1

    def hid_read(self, size: int = 64, timeout_ms: int = 1000) -> bytes:
        cmd = self._last_read_cmd
        if cmd is None:
            time.sleep(0.05)
            return b""
        resp = bytearray(64)
        resp[0], resp[1], resp[2] = 0x4B, 0x80, cmd
        if cmd == 0x02:
            resp[3] = 2
            resp[4:6] = (self.tk_mic * 256 & 0xFFFF).to_bytes(2, "little")
        elif cmd == 0x03:
            resp[3] = 2
            resp[4:6] = (self.tk_vol * 256 & 0xFFFF).to_bytes(2, "little")
        elif cmd == 0x0C:
            fb = self.tk_firmware.encode()
            resp[4:4 + len(fb)] = fb
        elif cmd == 0x11:
            resp[3] = 1
            resp[4] = self.tk_filter & 0xFF
        elif cmd == 0x16:
            ch = self._last_read_args[1] if len(self._last_read_args) > 1 else 0
            resp[3] = 4
            resp[4] = ch
            v = self.tk_bal[ch] * 256 & 0xFFFF
            resp[5] = v & 0xFF
            resp[6] = (v >> 8) & 0xFF
        elif cmd == 0x18:
            resp[3] = 1
            resp[4] = self.tk_led & 0xFF
        elif cmd == 0x19:
            resp[3] = 1
            resp[4] = self.tk_gain & 0xFF
        elif cmd == 0x09:
            idx = self._last_read_args[1] if len(self._last_read_args) > 1 else 0
            band = self.tk_bands.get(idx)
            if band:
                resp[4:4 + len(band)] = band[:60]
        self._last_read_cmd = None
        time.sleep(0.005)
        return bytes(resp)

    def describe(self) -> str:
        return f"模拟设备({self.brand}/{self.chip_type})"
