# -*- coding: utf-8 -*-
"""TTGK（VID 13058）设备协议

对照 Android 版 TTGKActivity / EZEQHelper / ProEQHelper：
- HID 中断端点：写 [4B 01 cmd len payload...]，读 [4B 80 cmd ...] → 64 字节响应
- 音量/麦克风写入后需延时 ~10ms 再发 [4B 01 04 00] 提交

响应校验（重要）
----------------
旧实现收到任何非空响应就直接当成当前命令的结果，不校验头部与 CMD。设备上一条
命令的延迟回包会被误认为当前响应 → 偶发读到错误的音量/滤波器值，且极难复现。
现改为丢弃「头部异常 / CMD 不匹配 / arg 不匹配 / 长度不足」的响应。
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from ..config import GET_INFO_MAX_RETRY_TIME
from ..protocol.eqdata import EQData
from ..usb.base import BaseTransport, TransportError

log = logging.getLogger(__name__)

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

IO_TIMEOUT = 1000        # ms，单次读取的最长等待
WRITE_GAP = 0.005        # 连续写入之间的间隔
READ_POLL = 200          # ms，轮询响应的单片超时


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
    def _read_raw(self, cmd: int, req: bytes, *, expect_len: int = 0,
                  expect_arg: Optional[int] = None,
                  retries: int = GET_INFO_MAX_RETRY_TIME) -> Optional[bytes]:
        """发送请求并等待「匹配」的响应。

        丢弃以下响应（可能是上一条命令的延迟回包或脏数据）：
          - 长度 < 3
          - 头部不是 0x4B 0x80
          - CMD 字段不等于本次请求
          - expect_arg 不为 None 且第 5 字节不等于它
          - expect_len 不为 0 且长度不足
        """
        for attempt in range(retries):
            self.t.hid_write(req)
            deadline = time.monotonic() + IO_TIMEOUT / 1000.0
            while time.monotonic() < deadline:
                resp = self.t.hid_read(64, READ_POLL)
                if not resp:
                    break
                if len(resp) < 3 or resp[0] != 0x4B or resp[1] != 0x80:
                    log.debug("丢弃头部异常响应: %s", resp[:8].hex(" "))
                    continue
                if resp[2] != cmd:
                    log.debug("丢弃 CMD 不匹配响应: 期望 %02X 实收 %02X (%s)",
                              cmd, resp[2], resp[:8].hex(" "))
                    continue
                if expect_arg is not None and (len(resp) < 5 or resp[4] != expect_arg):
                    log.debug("丢弃 arg 不匹配响应: 期望 %s", expect_arg)
                    continue
                if expect_len and len(resp) < expect_len:
                    log.warning("响应长度不足: %d < %d (%s)",
                                len(resp), expect_len, resp[:8].hex(" "))
                    continue
                return resp
            log.debug("第 %d/%d 次读取未获有效响应 (CMD %02X)",
                      attempt + 1, retries, cmd)
        return None

    def _write(self, payload: bytes) -> int:
        return self.t.hid_write(payload)

    # ---- 音量 / 麦克风 ----
    def read_vol(self) -> int:
        resp = self._read_raw(CMD_VOLUME, bytes([0x4B, 0x80, CMD_VOLUME]), expect_len=6)
        if not resp:
            raise TransportError("获取音量信息失败")
        return _le_i16(resp[4:6]) // 256

    def set_vol(self, level: int) -> bool:
        self._write(bytes([0x4B, 0x01, CMD_VOLUME, 2]) + _i16le(level * 256))
        time.sleep(0.010)
        self._write(bytes([0x4B, 0x01, CMD_COMMIT, 0]))
        return True

    def read_mic(self) -> int:
        resp = self._read_raw(CMD_MIC_VOL, bytes([0x4B, 0x80, CMD_MIC_VOL]), expect_len=6)
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
        resp = self._read_raw(CMD_FIRMWARE, bytes([0x4B, 0x80, CMD_FIRMWARE]), expect_len=5)
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
        resp = self._read_raw(CMD_FILTER, bytes([0x4B, 0x80, CMD_FILTER]), expect_len=5)
        if not resp:
            raise TransportError("接受滤波器信息失败")
        return resp[4]

    def set_filter(self, mode: int) -> bool:
        self._write(bytes([0x4B, 0x01, CMD_FILTER, 1, mode & 0xFF]))
        return True

    # ---- LED ----
    def read_led(self) -> int:
        resp = self._read_raw(CMD_LED, bytes([0x4B, 0x80, CMD_LED, 1]), expect_len=5)
        if not resp:
            raise TransportError("获取LED信息失败")
        return 0 if resp[4] == 0 else 1

    def set_led(self, on: bool) -> bool:
        self._write(bytes([0x4B, 0x01, CMD_LED, 1, 1 if on else 0]))
        return True

    # ---- 增益档位 ----
    def read_gain(self) -> int:
        resp = self._read_raw(CMD_GAIN, bytes([0x4B, 0x80, CMD_GAIN]), expect_len=5)
        if not resp:
            raise TransportError("获取增益数据失败")
        return 0 if resp[4] == 0 else 1

    def set_gain(self, level: int) -> bool:
        self._write(bytes([0x4B, 0x01, CMD_GAIN, 1, level & 0xFF]))
        return True

    # ---- 声道平衡（值域 -20..+20）----
    def read_balance(self) -> int:
        r0 = self._read_raw(CMD_BALANCE, bytes([0x4B, 0x80, CMD_BALANCE, 4, 0]),
                            expect_len=7, expect_arg=0)
        r1 = self._read_raw(CMD_BALANCE, bytes([0x4B, 0x80, CMD_BALANCE, 4, 1]),
                            expect_len=7, expect_arg=1)
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
    def upload_eq(self, data: EQData) -> bool:
        """上传 8 段 EQ（对照 uploadEQToDevice + confirmEQSettingOfDevice）

        返回 True 表示已提交并完成生效确认；False 表示参数已写入但确认步骤失败
        （调用方应据此给出不同提示，而不是一律报「成功」）。
        """
        for i in range(len(data.fc_list)):
            self._write(data.band_packet(i))
            time.sleep(WRITE_GAP)
        self._write(bytes([0x4B, 0x01, CMD_EQ_COMMIT, 4, 0, 0, 0xFF, 0xFF]))

        # 生效确认：重设一次当前音量（原版行为）
        try:
            vol = self.read_vol()
            time.sleep(0.010)
            self.set_vol(vol)
            return True
        except TransportError as e:
            log.warning("EQ 已写入但生效确认失败: %s", e)
            return False

    def read_eq_band(self, index: int) -> Optional[bytes]:
        """读取设备中的第 index 段 EQ 原始数据（64 字节响应）"""
        return self._read_raw(CMD_EQ_BAND,
                              bytes([0x4B, 0x80, CMD_EQ_BAND, 0x18, index & 0xFF]),
                              expect_len=0x18 + 4)
