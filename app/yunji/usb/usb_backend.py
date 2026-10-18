# -*- coding: utf-8 -*-
"""pyusb (libusb / WinUSB) 后端：支持任意厂商控制传输与端点读写。

- 旋润（XuanRun）设备：控制传输协议，需要 WinUSB/libusb 类驱动绑定该设备
  （可用 Zadig 一键安装；详见 驱动安装说明.md）
- TTGK 设备：作为 HID 后端的备选，走同一套端点读写。

libusb DLL：优先使用 pip 包 `libusb-package` 自带的 1.0.27 DLL。

控制传输的鲁棒性
----------------
USB 隔离器（ADuM3160/4160 等）会带来三类问题：
  1. 供电受限导致设备在首次操作时重新枚举 → 句柄失效（LIBUSB_ERROR_NO_DEVICE）
  2. 额外延迟导致「写入后立刻读取」拿不到响应 → 超时
  3. 驱动未正确绑定 → NOT_SUPPORTED / PIPE

因此控制传输改为有限重试 + 退避延时，并按 libusb 错误码给出可操作的提示。
"""
from __future__ import annotations

import logging
import os
import time
from typing import List, Optional

from .base import BaseTransport, TransportError

log = logging.getLogger(__name__)

try:
    import usb.core
    import usb.util
    import usb.backend.libusb1
    _USB_OK = True
except Exception:  # pragma: no cover
    usb = None
    _USB_OK = False

# ---- 控制传输参数 ----
CONTROL_TIMEOUT_MS = 1000      # 单次传输超时
CONTROL_RETRIES = 3            # 总尝试次数
WRITE_READ_GAP = 0.005         # 写入到读取之间的基准间隔（秒）
RETRY_BACKOFF = 0.05           # 重试退避基数（秒）

# libusb errno 常量（部分环境不暴露，直接写数值）
ERR_IO = -1
ERR_NO_DEVICE = -4
ERR_NOT_FOUND = -5
ERR_TIMEOUT = -7
ERR_PIPE = -9
ERR_NOT_SUPPORTED = -12

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
        log.warning("USB 枚举异常", exc_info=True)
        return []


# ---------------- 错误分类 ----------------
#: 重试无意义的错误类别（需要用户干预）
_FATAL_KINDS = ("stale", "unsupported")


def classify_usb_error(e) -> tuple:
    """把 libusb 异常归类为 (kind, 面向用户的说明)

    kind 取值：stale / unsupported / timeout / io / other
    """
    errno = getattr(e, "errno", None)
    text = str(e)
    low = text.lower()

    if errno == ERR_NO_DEVICE or "no such device" in low or "entity not found" in low:
        return ("stale",
                "设备句柄已失效（设备可能被重新枚举）。\n"
                "使用 USB 隔离器时常见：隔离器供电不足或链路抖动会导致设备重连。\n"
                "建议：换用带外部供电的隔离器、缩短线材，或拔插设备后重试。")

    if errno == ERR_NOT_SUPPORTED or "not supported" in low:
        return ("unsupported",
                "当前驱动不支持该操作。\n"
                "旋润设备需要为该接口安装 WinUSB 驱动（用 Zadig 选择设备后安装）。\n"
                "注意：经过隔离器后设备可能是新的设备实例，需重新确认绑定。")

    if errno == ERR_PIPE or "pipe error" in low:
        return ("unsupported",
                "设备拒绝了该请求（PIPE）。\n"
                "通常是驱动未正确绑定，或设备接口号与预期不符。\n"
                "建议用 Zadig 重新为设备安装 WinUSB 驱动。")

    if errno == ERR_TIMEOUT or "timeout" in low or "timed out" in low:
        return ("timeout",
                "设备未在超时时间内响应。\n"
                "USB 隔离器会增加链路延迟，或设备供电不足。")

    if errno == ERR_IO or "input/output error" in low:
        return ("io", "USB 传输出现 I/O 错误，链路可能不稳定。")

    return ("other", f"USB 通信失败：{text}")


def friendly_usb_error(e) -> str:
    return classify_usb_error(e)[1]



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
            except Exception as e:  # noqa: BLE001
                # 不能直接忽略：驱动未绑定时这里就会失败，而后续控制传输
                # 也会失败。记录下来便于诊断「列表已连接但读取失败」的问题。
                log.warning("set_configuration 失败（可能驱动未绑定，继续尝试）: %s", e)
            if need_ttgk_endpoints:
                self._find_endpoints()
        except usb.core.USBError as e:  # type: ignore
            raise TransportError(self._friendly_error(e)) from e
        return self

    @staticmethod
    def _friendly_error(e) -> str:
        kind, msg = classify_usb_error(e)
        if kind == "unsupported":
            return ("无法打开设备：接口被系统驱动占用或未绑定 WinUSB。\n"
                    "旋润协议需要为该设备安装 WinUSB 驱动（请使用 Zadig 工具，"
                    "选择该设备后安装 WinUSB），安装后再重新连接。")
        return msg

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

    def recover(self) -> bool:
        """重新枚举同 VID/PID 的设备并替换底层句柄

        用于 USB 隔离器导致设备重新枚举、原句柄失效的场景。
        返回 True 表示已拿到可用句柄（不代表协议层一定可用）。
        """
        if not _USB_OK:
            return False
        try:
            vid = int(self._device.idVendor)
            pid = int(self._device.idProduct)
        except Exception:
            return False

        try:
            self.close()
        except Exception:
            pass

        try:
            found = list(usb.core.find(find_all=True, idVendor=vid, idProduct=pid,
                                       backend=_ensure_backend()))
        except Exception:
            log.warning("恢复连接时枚举失败", exc_info=True)
            return False

        for dev in found:
            try:
                dev.set_configuration()
            except Exception:
                pass  # 已被系统配置亦可继续
            self._device = dev
            log.info("已重新获取设备句柄: %04X:%04X", vid, pid)
            return True

        log.warning("恢复连接失败：未找到 %04X:%04X", vid, pid)
        return False

    # ---- 控制传输（旋润）----
    def _control_loop(self, direction: str, data: bytes):
        """控制传输的公共重试逻辑

        - timeout / io：可重试，退避后继续
        - stale（设备重新枚举）：自动重新获取句柄后重试一次
        - unsupported：驱动问题，重试无意义，直接失败
        """
        last = None
        recovered = False
        attempt = 0

        while attempt < CONTROL_RETRIES:
            try:
                self._device.ctrl_transfer(
                    0x43, 0xA0, 0, 0x09A0, bytes(data), timeout=CONTROL_TIMEOUT_MS
                )
                if direction == "out":
                    return None
                # 隔离器会增加链路延迟，重试时逐步放宽等待
                time.sleep(WRITE_READ_GAP * (attempt + 1))
                resp = self._device.ctrl_transfer(
                    0xC3, 0xA1, 0, 0x09A0, 7, timeout=CONTROL_TIMEOUT_MS
                )
                return bytes(resp)
            except usb.core.USBError as e:  # type: ignore
                last = e
                kind, _msg = classify_usb_error(e)

                if kind == "stale" and not recovered:
                    recovered = True
                    log.warning("设备句柄失效（可能被重新枚举），尝试自动恢复…")
                    if self.recover():
                        continue          # 恢复成功：不消耗重试次数
                    break

                if kind in _FATAL_KINDS:
                    break

                attempt += 1
                log.warning("控制传输(%s)失败 第 %d/%d 次 [%s]: %s",
                            direction, attempt, CONTROL_RETRIES, kind, e)
                if attempt < CONTROL_RETRIES:
                    time.sleep(RETRY_BACKOFF * attempt)

        kind, msg = classify_usb_error(last) if last is not None else ("other", "未知错误")
        log.error("控制传输(%s)最终失败 [%s]: %s", direction, kind, last)
        raise TransportError(f"控制传输({direction})失败：{msg}") from last

    def control_out(self, data: bytes) -> int:
        self._control_loop("out", data)
        return len(data)

    def control_in(self, data: bytes) -> bytes:
        return self._control_loop("in", data)

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
