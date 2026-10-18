# -*- coding: utf-8 -*-
"""USB 传输抽象层

设计：把设备通信抽象为 4 个原语，覆盖两个品牌协议：
- control_out / control_in  →  旋润（XuanRun）：USB 控制传输（厂商请求 0xA0/0xA1）
- hid_write / hid_read      →  TTGK：HID 中断端点读写

后端实现：
- HidBackend   （hidapi，Windows 标准 HID 驱动即可，零安装）
- UsbBackend   （pyusb + libusb/WinUSB 驱动，支持任意控制传输）
- SimulatedTransport （无设备时的模拟实现，用于功能预览与自测）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class TransportError(Exception):
    pass


class BaseTransport:
    """传输层基类"""

    kind = "base"
    can_xuanrun = False     # 是否支持控制传输（旋润协议）
    can_ttgk = False        # 是否支持 HID 中断端点（TTGK 协议）

    def open(self):
        raise NotImplementedError

    def close(self):
        pass

    # ---- 旋润：控制传输（7 字节包）----
    def control_out(self, data: bytes) -> int:
        raise TransportError("当前传输后端不支持控制传输")

    def control_in(self, data: bytes) -> bytes:
        raise TransportError("当前传输后端不支持控制传输")

    # ---- TTGK：中断端点读写 ----
    def hid_write(self, data: bytes) -> int:
        raise TransportError("当前传输后端不支持中断端点写")

    def hid_read(self, size: int = 64, timeout_ms: int = 1000) -> bytes:
        raise TransportError("当前传输后端不支持中断端点读")

    def recover(self) -> bool:
        """尝试恢复失效的连接（重新枚举 / 重新打开）

        典型场景：USB 隔离器供电波动导致设备重新枚举，原句柄失效。
        默认不支持恢复；具体后端可按自身能力实现。
        """
        return False

    def describe(self) -> str:
        return self.kind


@dataclass
class DeviceEntry:
    """扫描到的设备条目（合并产品表信息与物理连接信息）"""
    vid: int
    pid: int
    name: str
    icon: str
    valid: bool
    additional_info: list = field(default_factory=list)
    connected: bool = False            # 当前是否插入且已获得访问权限
    transport_hint: str = "hid"        # hid / winusb
    backend_desc: str = ""
    openable: bool = False             # 是否已确认可打开（驱动是否就绪）
    open_error: str = ""
    is_sim: bool = False               # 模拟设备标记

    @property
    def chip_type(self) -> Optional[str]:
        for info in self.additional_info:
            if info in ("cb1200", "cb5100"):
                return info
        return None

    @property
    def key(self):
        return f"{self.vid}:{self.pid}"

    @property
    def display_name(self) -> str:
        return self.name
