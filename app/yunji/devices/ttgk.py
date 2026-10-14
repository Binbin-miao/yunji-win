# -*- coding: utf-8 -*-
"""TTGK（VID 13058）设备协议

对照 Android 版 TTGKActivity / EZEQHelper / ProEQHelper：
- HID 中断端点：写 [4B 01 cmd len payload...]，读 [4B 80 cmd ...] → 64 字节响应
- 音量/麦克风写入后需延时 ~10ms 再发 [4B 01 04 00] 提交
"""
from __future__ import annotations

import time
from typing import Optional

from ..config import GET_INFO_MAX_RETRY_TIME
from ..protocol.eqdata import EQData
from ..usb.base import BaseTransport, TransportError

CMD_MIC_VOL = 0x02
CMD_VOLUME = 0x03
CMD_COMMIT = 0x04
CMD_EQ_BAND = 0x09
CMD_EQ_COMMIT = 0x0A
CMD_FIRMWARE = 0x0C
CMD_FILTER = 0x11
CMD_BALANCE = 0x16
CMD_LED = 0x18
CMD_GAIN = 0x19

IO_TIMEOUT = 1000  # ms


def _i16le(v: int) -> bytes:
    v &= 0xFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF])


def _le_i16(b: bytes) -> int:
    v = b[0] | (b[1] << 8)
    return v - 0x10000 if v & 0x8000 else v


class TtgkDevice:
    """TTGK 设备高级操作"""

    def __init__(self, transport: BaseTransport):
        self.t = transport

    # ---- 底层 ----
    def _read_raw(self, req: bytes, retries: int = GET_INFO_MAX_RETRY_TIME) -> Optional[bytes]:
        for _ in range(retries):
            self.t.hid_write(req)
            time.sleep(0.005)
            resp = self.t.hid_read(64, IO_TIMEOUT)
            if resp:
                return resp
        return None

    def _write(self, payload: bytes) -> int:
        n = self.t.hid_write(payload)
        if n is not None and n < 0:
            raise TransportError(f"发送失败: {payload[:4].hex(' ')}")
        return n

    # ---- 音量 / 麦克风 ----
    def read_vol(self) -> int:
        resp = self._read_raw(bytes([0x4B, 0x80, CMD_VOLUME]))
        if not resp:
            raise TransportError("获取音量信息失败")
        return _le_i16(resp[4:6]) // 256

    def set_vol(self, level: int) -> bool:
        self._write(bytes([0x4B, 0x01, CMD_VOLUME, 2]) + _i16le(level * 256))
        time.sleep(0.010)
        self._write(bytes([0x4B, 0x01, CMD_COMMIT, 0]))
        return True

    def read_mic(self) -> int:
        resp = self._read_raw(bytes([0x4B, 0x80, CMD_MIC_VOL]))
        if not resp:
            raise TransportError("获取麦克风信息失败")
        return _le_i16(resp[4:6]) // 256

    def set_mic(self, level: int) -> bool:
        self._write(bytes([0x4B, 0x01, CMD_MIC_VOL, 2]) + _i16le(level * 256))
        time.sleep(0.010)
        self._write(bytes([0x4B, 0x01, CMD_COMMIT, 0]))
        return True

    # ---- 固件 ----
    def read_firmware(self) -> str:
        resp = self._read_raw(bytes([0x4B, 0x80, CMD_FIRMWARE]))
        if not resp:
            raise TransportError("获取固件信息失败")
        out = []
        for b in resp[4:]:
            if b == 0 or not (b == 0x2E or 0x30 <= b <= 0x39):
                break
            out.append(chr(b))
        return "".join(out)

    # ---- 滤波器 ----
    def read_filter(self) -> int:
        resp = self._read_raw(bytes([0x4B, 0x80, CMD_FILTER]))
        if not resp:
            raise TransportError("接受滤波器信息失败")
        return resp[4]

    def set_filter(self, mode: int) -> bool:
        self._write(bytes([0x4B, 0x01, CMD_FILTER, 1, mode & 0xFF]))
        return True

    # ---- LED ----
    def read_led(self) -> int:
        resp = self._read_raw(bytes([0x4B, 0x80, CMD_LED, 1]))
        if not resp:
            raise TransportError("获取LED信息失败")
        return 0 if resp[4] == 0 else 1

    def set_led(self, on: bool) -> bool:
        self._write(bytes([0x4B, 0x01, CMD_LED, 1, 1 if on else 0]))
        return True

    # ---- 增益档位 ----
    def read_gain(self) -> int:
        resp = self._read_raw(bytes([0x4B, 0x80, CMD_GAIN]))
        if not resp:
            raise TransportError("获取增益数据失败")
        return 0 if resp[4] == 0 else 1

    def set_gain(self, level: int) -> bool:
        self._write(bytes([0x4B, 0x01, CMD_GAIN, 1, level & 0xFF]))
        return True

    # ---- 声道平衡（值域 -20..+20）----
    def read_balance(self) -> int:
        r0 = self._read_raw(bytes([0x4B, 0x80, CMD_BALANCE, 4, 0]))
        r1 = self._read_raw(bytes([0x4B, 0x80, CMD_BALANCE, 4, 1]))
        if not r0 or not r1:
            raise TransportError("获取声道平衡信息错误")
        v0 = _le_i16(r0[5:7]) // 256
        v1 = _le_i16(r1[5:7]) // 256
        return v1 - v0

    def set_balance(self, value: int) -> bool:
        value = max(-20, min(20, int(value)))
        pkt_l = bytearray([0x4B, 0x01, CMD_BALANCE, 4, 0, 0, 0, 0])
        pkt_r = bytearray([0x4B, 0x01, CMD_BALANCE, 4, 1, 0, 0, 0])
        if value != 0:
            att = _i16le(-abs(value) * 256)
            if value < 0:
                pkt_r[5], pkt_r[6] = att[0], att[1]
            else:
                pkt_l[5], pkt_l[6] = att[0], att[1]
        self._write(bytes(pkt_l))
        self._write(bytes(pkt_r))
        return True

    # ---- EQ ----
    def upload_eq(self, data: EQData):
        """上传 8 段 EQ（对照 uploadEQToDevice + confirmEQSettingOfDevice）"""
        for i in range(len(data.fc_list)):
            pkt = data.band_packet(i)
            n = self.t.hid_write(pkt)
            if n is not None and n < 0:
                raise TransportError("上传EQ失败")
            time.sleep(0.005)
        n = self.t.hid_write(bytes([0x4B, 0x01, CMD_EQ_COMMIT, 4, 0, 0, 0xFF, 0xFF]))
        if n is not None and n < 0:
            raise TransportError("上传EQ失败")
        # 生效确认：重设一次音量
        try:
            vol = self.read_vol()
            time.sleep(0.010)
            self.set_vol(vol)
        except TransportError:
            pass

    def read_eq_band(self, index: int) -> Optional[bytes]:
        """读取设备中的第 index 段 EQ 原始数据（64 字节响应）"""
        resp = self._read_raw(bytes([0x4B, 0x80, CMD_EQ_BAND, 0x18, index & 0xFF]))
        return resp
