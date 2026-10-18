# -*- coding: utf-8 -*-
"""hidapi 后端：使用 Windows 标准 HID 驱动（hidusb/hidclass），零安装。

适用于 TTGK 品牌设备（HID 中断端点协议）。

写入格式策略
------------
真机验证：设备把协议首字节 0x4B 同时用作 HID 报告 ID，Windows HID 驱动要求
写入缓冲 = 报告 ID + 完整负载，故需补零到 64 字节。

旧实现在**每次写入**时依次尝试三种格式，这很危险：`0x00 + data` 是另一种
协议封装，设备可能解析成完全不同的命令；对 0x04(提交保存) / 0x0A(EQ 生效)
这类有副作用的命令，重复+变形发送可能让设备进入非预期状态。

现改为：打开设备时用只读的「读固件版本」命令探测一次，锁定唯一可用格式；
之后写入失败直接报错，不再静默变形重试。
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

from .base import BaseTransport, TransportError

try:
    import hid  # hidapi
    _HID_OK = True
except Exception:  # pragma: no cover
    hid = None
    _HID_OK = False

log = logging.getLogger(__name__)

CMD_FIRMWARE = 0x0C

#: Windows HID 路径形如 \\?\hid#vid_32d2&pid_43dc#...，用于恢复时重新定位
_VIDPID_RE = re.compile(r"vid_([0-9a-f]{4}).*?pid_([0-9a-f]{4})", re.IGNORECASE)


def _parse_vid_pid(path):
    """从 HID 设备路径解析 VID/PID（解析失败返回 (None, None)）"""
    if not path:
        return None, None
    try:
        text = path.decode("utf-8", "ignore") if isinstance(path, bytes) else str(path)
    except Exception:
        return None, None
    m = _VIDPID_RE.search(text)
    if not m:
        return None, None
    return int(m.group(1), 16), int(m.group(2), 16)


def hid_available() -> bool:
    return _HID_OK


def enumerate_hid(vid: Optional[int] = None, pid: Optional[int] = None) -> List[dict]:
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
        log.warning("HID 枚举异常", exc_info=True)
        return []
    return out


class HidBackend(BaseTransport):
    kind = "hidapi"
    can_ttgk = True

    #: 默认报告缓冲长度（实测描述符：输出报告 ID 0x4B / 0x54，负载 63 字节）
    REPORT_BUF = 64

    STRATEGY_NAMES = ("补零至64字节", "0x00 前缀", "原始数据")

    def __init__(self, path, serial: str = ""):
        self._path = path
        self._serial = serial
        self._dev = None
        self._strategy: Optional[int] = None

    # ---------------- 生命周期 ----------------
    def open(self):
        if not _HID_OK:
            raise TransportError("hidapi 未安装")
        try:
            self._dev = hid.device()
            self._dev.open_path(self._path)
        except Exception as e:  # noqa: BLE001
            raise TransportError(f"打开 HID 设备失败: {e}") from e
        self._probe_report_layout()
        self._strategy = self._probe_strategy()
        return self

    def close(self):
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None

    def recover(self) -> bool:
        """重新打开设备；路径失效时按 VID/PID 重新枚举"""
        if not _HID_OK or self._dev is None and self._path is None:
            return False
        self.close()
        try:
            self.open()
            log.info("HID 句柄已重新打开")
            return True
        except Exception:
            log.warning("按原路径重开失败，尝试重新枚举", exc_info=True)

        vid, pid = _parse_vid_pid(self._path)
        if vid is None:
            return False
        for d in enumerate_hid(vid, pid):
            try:
                self._path = d["path"]
                self.open()
                log.info("HID 句柄已通过重新枚举恢复: %04X:%04X", vid, pid)
                return True
            except Exception:
                continue
        log.warning("HID 恢复失败: %04X:%04X", vid, pid)
        return False

    # ---------------- 报告布局探测 ----------------
    def _probe_report_layout(self):
        """从 HID 报告描述符读取输出报告长度，失败则沿用默认值"""
        try:
            desc = self._dev.get_report_descriptor()
        except Exception:
            log.debug("无法获取报告描述符，沿用默认 %d 字节", self.REPORT_BUF)
            return
        try:
            from .hid_report import parse_output_reports
            reports = parse_output_reports(bytes(desc))
            log.info("HID 输出报告布局: %s", reports)
            for rid, size in reports:
                if rid == 0x4B:
                    self.REPORT_BUF = size + 1     # +1 为报告 ID 本身
                    log.info("按描述符采用报告长度 %d 字节", self.REPORT_BUF)
                    break
        except Exception:
            log.warning("报告描述符解析失败，沿用默认 %d 字节（描述符 %d 字节）",
                        self.REPORT_BUF, len(desc), exc_info=True)

    # ---------------- 写入策略 ----------------
    def _candidates(self, data: bytes) -> List[bytes]:
        return [self._pad(data), b"\x00" + data, bytes(data)]

    def _probe_strategy(self) -> int:
        """用只读的「读固件版本」命令探测唯一可用的写入格式。

        探测失败不阻断打开（回退策略 0 并记警告），保证向后兼容；
        但此后写入失败会直接报错，不再尝试其他格式。
        """
        probe = bytes([0x4B, 0x80, CMD_FIRMWARE])
        for idx, buf in enumerate(self._candidates(probe)):
            try:
                n = self._dev.write(bytes(buf))
            except Exception:
                log.debug("探测策略 %d(%s) 写入抛异常",
                          idx, self.STRATEGY_NAMES[idx], exc_info=True)
                continue
            if not n or n <= 0:
                log.debug("探测策略 %d(%s) 写入返回 %s", idx, self.STRATEGY_NAMES[idx], n)
                continue
            try:
                resp = self._dev.read(64, 300)
            except Exception:
                resp = None
            if resp and bytes(resp)[:1] == b"\x4B":
                log.info("HID 写入策略锁定为 %d（%s）", idx, self.STRATEGY_NAMES[idx])
                return idx
        log.warning("HID 写入探测未获确认响应，回退策略 0（%s）", self.STRATEGY_NAMES[0])
        return 0

    def _pad(self, data: bytes) -> bytes:
        if len(data) >= self.REPORT_BUF:
            return data[:self.REPORT_BUF]
        return data + bytes(self.REPORT_BUF - len(data))

    # ---------------- 读写 ----------------
    def hid_write(self, data: bytes) -> int:
        """按锁定策略单次写入；失败直接抛错"""
        if self._dev is None:
            raise TransportError("HID 设备未打开")
        if self._strategy is None:
            self._strategy = self._probe_strategy()
        buf = self._candidates(bytes(data))[self._strategy]
        try:
            n = self._dev.write(buf)
        except Exception as e:  # noqa: BLE001
            log.error("HID 写入失败: %s | 数据 %s", e, bytes(data)[:8].hex(" "))
            raise TransportError(f"HID 写入失败: {e}") from e
        if n is None or n <= 0:
            log.error("HID 写入被驱动拒绝 (返回 %s) | 数据 %s", n, bytes(data)[:8].hex(" "))
            raise TransportError("HID 写入失败：驱动未接受数据")
        return n

    def hid_read(self, size: int = 64, timeout_ms: int = 1000) -> bytes:
        if self._dev is None:
            raise TransportError("HID 设备未打开")
        try:
            data = self._dev.read(size, timeout_ms)
            return bytes(data) if data else b""
        except Exception as e:  # noqa: BLE001
            log.error("HID 读取失败: %s", e)
            raise TransportError(f"HID 读取失败: {e}") from e

    def describe(self) -> str:
        return "HID (hidapi)"
