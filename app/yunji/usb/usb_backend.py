# -*- coding: utf-8 -*-
"""pyusb (libusb / WinUSB) 后端：支持任意厂商控制传输与端点读写。

- 旋润（XuanRun）设备：控制传输协议，需要 WinUSB/libusb 类驱动绑定该设备
  （可用 Zadig 一键安装；详见 驱动安装说明.md）
- TTGK 设备：作为 HID 后端的备选，走同一套端点读写。

libusb DLL：优先使用 pip 包 `libusb-package` 自带的 1.0.27 DLL。
"""
from __future__ import annotations

import os
import time
from typing import List, Optional

from .base import BaseTransport, TransportError

try:
    import usb.core
    import usb.util
    import usb.backend.libusb1
    _USB_OK = True
except Exception:  # pragma: no cover
    usb = None
    _USB_OK = False

# ---- libusb DLL 定位 ----
_BACKEND = None


def _ensure_backend():
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    if not _USB_OK:
        return None
    try:
        import libusb_package  # type: ignore
        dll = libusb_package.get_library_path()
        _BACKEND = usb.backend.libusb1.get_backend(find_library=lambda x: dll)
    except Exception:
        _BACKEND = usb.backend.libusb1.get_backend()
    return _BACKEND


def usb_available() -> bool:
    return _USB_OK


def enumerate_usb() -> List:
    """枚举所有 USB 设备（libusb 视角）"""
    if not _USB_OK:
        return []
    try:
        return list(usb.core.find(find_all=True, backend=_ensure_backend()))
    except Exception:
        return []


class UsbBackend(BaseTransport):
    kind = "winusb"
    can_xuanrun = True
    can_ttgk = True

    def __init__(self, device, interface_class: int = 3):
        self._device = device
        self._iface_class = interface_class
        self._iface_num: Optional[int] = None
        self._ep_in = None
        self._ep_out = None

    # ---- 打开与关闭 ----
    def open(self, need_ttgk_endpoints: bool = True):
        if not _USB_OK:
            raise TransportError("pyusb/libusb 不可用")
        dev = self._device
        try:
            # 若设备被内核驱动占用（Windows 上一般不会），尝试解绑
            try:
                if dev.is_kernel_driver_active(0):
                    dev.detach_kernel_driver(0)
            except Exception:
                pass
            try:
                dev.set_configuration()
            except Exception:
                pass  # 已被系统配置亦可继续
            if need_ttgk_endpoints:
                self._find_endpoints()
        except usb.core.USBError as e:  # type: ignore
            raise TransportError(self._friendly_error(e)) from e
        return self

    @staticmethod
    def _friendly_error(e) -> str:
        msg = str(e)
        if "Access denied" in msg or "Errno 13" in msg or "not supported" in msg.lower():
            return ("无法打开设备：接口被系统驱动占用。\n"
                    "旋润协议需要为该设备安装 WinUSB 驱动（请使用 Zadig 工具，"
                    "选择该设备后安装 WinUSB），安装后再重新连接。")
        return f"USB 打开失败: {msg}"

    def _find_endpoints(self):
        dev = self._device
        cfg = None
        try:
            cfg = dev.get_active_configuration()
        except Exception:
            try:
                cfg = dev[0]
            except Exception as e:  # noqa: BLE001
                raise TransportError(f"读取设备配置失败: {e}") from e
        target_iface = None
        # 对应 Android 逻辑：找 class==3 (HID) 的接口
        for intf in cfg:
            if intf.bInterfaceClass == 3:
                target_iface = intf
                break
        if target_iface is None:
            # 备选：找带端点最多的接口
            best = None
            for intf in cfg:
                cnt = intf.bNumEndpoints or 0
                if cnt > 0 and (best is None or cnt > best.bNumEndpoints):
                    best = intf
            target_iface = best
        if target_iface is None:
            raise TransportError("未找到设备通信界面")
        self._iface_num = target_iface.bInterfaceNumber
        try:
            usb.util.claim_interface(dev, self._iface_num)
        except Exception:
            pass  # 某些平台已自动占用
        ep_in = ep_out = None
        for ep in target_iface:
            addr = ep.bEndpointAddress
            attr = ep.bmAttributes & 0x03
            if addr & 0x80:  # IN
                if attr == 3 or ep_in is None:  # 优先中断端点
                    ep_in = ep
            else:  # OUT
                if attr == 3 or ep_out is None:
                    ep_out = ep
        if ep_in is None or ep_out is None:
            raise TransportError("未找到设备端口")
        self._ep_in = ep_in
        self._ep_out = ep_out

    def close(self):
        try:
            if self._iface_num is not None:
                usb.util.release_interface(self._device, self._iface_num)
        except Exception:
            pass
        try:
            usb.util.dispose_resources(self._device)
        except Exception:
            pass

    # ---- 控制传输（旋润）----
    def control_out(self, data: bytes) -> int:
        try:
            return self._device.ctrl_transfer(
                0x43, 0xA0, 0, 0x09A0, bytes(data), timeout=1000
            )
        except usb.core.USBError as e:  # type: ignore
            raise TransportError(f"控制传输(写)失败: {e}") from e

    def control_in(self, data: bytes) -> bytes:
        try:
            self._device.ctrl_transfer(0x43, 0xA0, 0, 0x09A0, bytes(data), timeout=1000)
            time.sleep(0.005)
            resp = self._device.ctrl_transfer(0xC3, 0xA1, 0, 0x09A0, 7, timeout=1000)
            return bytes(resp)
        except usb.core.USBError as e:  # type: ignore
            raise TransportError(f"控制传输(读)失败: {e}") from e

    # ---- 端点读写（TTGK）----
    def hid_write(self, data: bytes) -> int:
        if self._ep_out is None:
            raise TransportError("端点未初始化")
        try:
            return int(self._device.write(self._ep_out, bytes(data), timeout=1000))
        except usb.core.USBError as e:  # type: ignore
            raise TransportError(f"端点写入失败: {e}") from e

    def hid_read(self, size: int = 64, timeout_ms: int = 1000) -> bytes:
        if self._ep_in is None:
            raise TransportError("端点未初始化")
        try:
            data = self._device.read(self._ep_in, size, timeout=timeout_ms)
            return bytes(data)
        except usb.core.USBTimeoutError:  # type: ignore
            return b""
        except usb.core.USBError as e:  # type: ignore
            raise TransportError(f"端点读取失败: {e}") from e

    def describe(self) -> str:
        return "USB (WinUSB/libusb)"
