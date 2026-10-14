# -*- coding: utf-8 -*-
"""旋润（XuanRun, VID 12230）设备协议

对照 Android 版 XuanRunActivity：
- 控制传输：写 (0x43,0xA0)，读 (0xC3,0xA1)，wIndex=0x09A0，7 字节包
- 命令包：[0xC1, 0xA6, cmd, a0, a1, a2, a3]
"""
from __future__ import annotations

from ..config import (
    XUANRUN_VOL_TABLE,
    XUANRUN_BALANCE_VALUE_L,
    XUANRUN_BALANCE_VALUE_R,
)
from ..usb.base import BaseTransport, TransportError

CMD_FILTER = 0x01
CMD_ELE_LEVEL = 0x02
CMD_VOLUME = 0x04
CMD_BALANCE = 0x05
CMD_LED = 0x06
CMD_DEPOP = 0x07

READ_FIRMWARE = 0xA0
READ_VOL_BALANCE = 0xA2
READ_STATUS = 0xA3


class XuanRunDevice:
    """旋润设备高级操作"""

    def __init__(self, transport: BaseTransport):
        self.t = transport

    # ---- 底层 ----
    def _write(self, cmd: int, a0: int = 0, a1: int = 0, a2: int = 0, a3: int = 0):
        pkt = bytes([0xC1, 0xA6, cmd & 0xFF, a0 & 0xFF, a1 & 0xFF, a2 & 0xFF, a3 & 0xFF])
        rc = self.t.control_out(pkt)
        if rc is not None and rc < 0:
            raise TransportError(f"发送失败 cmd={cmd:#x}")

    def _read(self, cmd: int, a0: int = 0, a1: int = 0) -> bytes:
        pkt = bytes([0xC1, 0xA6, cmd & 0xFF, a0 & 0xFF, a1 & 0xFF, 0, 0])
        resp = self.t.control_in(pkt)
        if not resp or len(resp) < 4:
            raise TransportError(f"读取失败 cmd={cmd:#x}")
        return resp

    # ---- 读取 ----
    def read_firmware(self) -> str:
        resp = self._read(READ_FIRMWARE)
        return str(resp[3])

    def read_vol_balance(self):
        """返回 (音量滑块0-60, L码, R码)"""
        resp = self._read(READ_VOL_BALANCE)
        code = resp[4] & 0xFF
        vol_idx = 0
        for i, v in enumerate(XUANRUN_VOL_TABLE):
            if v == code:
                vol_idx = i
        return vol_idx, resp[5] & 0xFF, resp[6] & 0xFF

    def read_status(self):
        """返回 (filter, ele_level, led, depop)"""
        resp = self._read(READ_STATUS)
        return resp[3], resp[4], resp[5], resp[6]

    # ---- 写入 ----
    def set_filter(self, mode: int) -> bool:
        self._write(CMD_FILTER, mode)
        return True

    def set_ele_level(self, level: int) -> bool:
        self._write(CMD_ELE_LEVEL, level)
        return True

    def set_volume_index(self, index: int) -> bool:
        index = max(0, min(60, int(index)))
        self._write(CMD_VOLUME, XUANRUN_VOL_TABLE[index])
        return True

    def set_balance_index(self, index: int) -> bool:
        index = max(0, min(36, int(index)))
        self._write(CMD_BALANCE,
                    XUANRUN_BALANCE_VALUE_L[index],
                    XUANRUN_BALANCE_VALUE_R[index])
        return True

    def set_led(self, on: bool) -> bool:
        self._write(CMD_LED, 0 if on else 2)
        return True

    def set_depop(self, on: bool) -> bool:
        self._write(CMD_DEPOP, 0 if on else 1)
        return True
