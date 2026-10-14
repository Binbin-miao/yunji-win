# -*- coding: utf-8 -*-
"""hidapi 后端：使用 Windows 标准 HID 驱动（hidusb/hidclass），零安装。

适用于 TTGK 品牌设备（HID 中断端点协议）。
写策略：优先 [0x00]+data（report ID 0 前缀，hidapi 约定），失败则尝试原文数据。
"""
from __future__ import annotations

import time
from typing import List

from .base import BaseTransport, TransportError

try:
    import hid  # hidapi
    _HID_OK = True
except Exception:  # pragma: no cover
    hid = None
    _HID_OK = False


def hid_available() -> bool:
    return _HID_OK


def enumerate_hid(vid: int | None = None, pid: int | None = None) -> List[dict]:
    """枚举 HID 设备，可按 VID/PID 过滤"""
    if not _HID_OK:
        return []
    out = []
    try:
        for d in hid.enumerate():
            if vid is not None and d.get("vendor_id") != vid:
                continue
            if pid is not None and d.get("product_id") != pid:
                continue
            out.append(d)
    except Exception:
        return []
    return out


class HidBackend(BaseTransport):
    kind = "hidapi"
    can_ttgk = True

    #: 云姬设备 HID 输出/输入报告长度（实测报告描述符：
    #: 输出报告 ID 0x4B / 0x54，负载各 63 字节 → 缓冲 64 字节）
    REPORT_BUF = 64

    def __init__(self, path: bytes | str, serial: str = ""):
        self._path = path
        self._serial = serial
        self._dev = None
        self._strategy = 0   # 0: 原文+补零 64 字节（真机验证） 1: 0x00 前缀 2: 原文不补零

    def open(self):
        if not _HID_OK:
            raise TransportError("hidapi 未安装")
        try:
            self._dev = hid.device()
            self._dev.open_path(self._path)
        except Exception as e:  # noqa: BLE001
            raise TransportError(f"打开 HID 设备失败: {e}") from e
        return self

    def close(self):
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    def hid_write(self, data: bytes) -> int:
        """发送报文。

        真机验证的对齐方式：设备将协议首字节 0x4B 同时用作 HID 报告 ID，
        Windows HID 驱动要求写入缓冲 = 报告 ID + 完整负载，故直接补零到 64 字节。
        """
        if self._dev is None:
            raise TransportError("HID 设备未打开")
        data = bytes(data)
        attempts = []
        if self._strategy == 0:
            attempts = [self._pad(data), b"\x00" + data, data]
        elif self._strategy == 1:
            attempts = [b"\x00" + data, self._pad(data), data]
        else:
            attempts = [data, self._pad(data), b"\x00" + data]
        last_err = None
        for i, buf in enumerate(attempts):
            try:
                n = self._dev.write(bytes(buf))
                if n is not None and n > 0:
                    return n
            except Exception as e:  # noqa: BLE001
                last_err = e
        if last_err is not None:
            raise TransportError(f"HID 写入失败: {last_err}")
        return -1

    def _pad(self, data: bytes) -> bytes:
        if len(data) >= self.REPORT_BUF:
            return data
        return data + bytes(self.REPORT_BUF - len(data))

    def hid_read(self, size: int = 64, timeout_ms: int = 1000) -> bytes:
        if self._dev is None:
            raise TransportError("HID 设备未打开")
        try:
            data = self._dev.read(size, timeout_ms)
            return bytes(data) if data else b""
        except Exception as e:  # noqa: BLE001
            raise TransportError(f"HID 读取失败: {e}") from e

    def describe(self) -> str:
        return "HID (hidapi)"
