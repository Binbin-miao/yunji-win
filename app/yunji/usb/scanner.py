# -*- coding: utf-8 -*-
"""设备扫描与打开：合并产品表配置与物理连接状态"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional, Tuple

from ..config import VENDER_ID_TTGK, VENDER_ID_XUAN_RUN
from ..storage import get_app_state, resolve_asset
from .base import BaseTransport, DeviceEntry, TransportError
from .hid_backend import HidBackend, enumerate_hid, hid_available
from .usb_backend import UsbBackend, enumerate_usb, usb_available

log = logging.getLogger(__name__)


# ---------------- 产品表（进程内缓存）----------------
_product_cache: Optional[List[dict]] = None
_index_cache: Optional[Dict[Tuple[int, int], dict]] = None


def _read_product_list() -> List[dict]:
    path = resolve_asset("product-list/product-list.json")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    vendors = []
    for v in raw.get("vendors", []):
        products = []
        for p in v.get("products", []):
            products.append({
                "id": int(p.get("id", 0)),
                "name": p.get("name", ""),
                "icon": p.get("icon", "ic_dev_null"),
                "valid": bool(p.get("isValid", False)),
                "additional_info": list(p.get("additionalInfo", []) or []),
            })
        vendors.append({"id": int(v.get("id", 0)), "name": v.get("name", ""), "products": products})
    return vendors


def load_product_list() -> List[dict]:
    """产品表（只读缓存）。调用方不得修改返回值。"""
    global _product_cache
    if _product_cache is None:
        _product_cache = _read_product_list()
        log.debug("产品表已载入，共 %d 个厂商", len(_product_cache))
    return _product_cache


def _product_index() -> Dict[Tuple[int, int], dict]:
    """(vid, pid) -> 产品信息，避免逐设备线性查找"""
    global _index_cache
    if _index_cache is None:
        idx: Dict[Tuple[int, int], dict] = {}
        for v in load_product_list():
            for p in v["products"]:
                idx[(v["id"], p["id"])] = {
                    **p, "vendor_id": v["id"], "vendor_name": v["name"]
                }
        _index_cache = idx
    return _index_cache


def find_product(vid: int, pid: int) -> Optional[dict]:
    return _product_index().get((vid, pid))


def invalidate_product_cache() -> None:
    """用户覆盖资源变更后调用（测试与开发期使用）"""
    global _product_cache, _index_cache
    _product_cache = None
    _index_cache = None


def brand_of(vid: int) -> str:
    if vid == VENDER_ID_XUAN_RUN:
        return "xuanrun"
    if vid == VENDER_ID_TTGK:
        return "ttgk"
    return "unknown"


# ---------------- 扫描 ----------------
class ScanError(RuntimeError):
    """扫描失败（区分「没有设备」与「枚举本身出错」）"""


def _hid_entries() -> List[dict]:
    return enumerate_hid()


def _usb_entries() -> List[Tuple[int, int]]:
    out = []
    for dev in enumerate_usb():
        try:
            out.append((int(dev.idVendor), int(dev.idProduct)))
        except Exception:
            continue
    return out


def scan_devices(include_known: bool = True) -> List[DeviceEntry]:
    """扫描当前连接的云姬设备（含已知历史设备占位）

    与旧实现不同：不再吞掉异常。若枚举本身失败会抛出 ScanError，
    由调用方决定如何提示用户（驱动未装 / 设备被占用 等）。
    """
    vendors = load_product_list()
    result: Dict[str, DeviceEntry] = {}

    errors: List[str] = []

    # 物理连接：HID 视角
    hid_pairs = set()
    try:
        for d in _hid_entries():
            hid_pairs.add((int(d.get("vendor_id", 0)), int(d.get("product_id", 0))))
    except Exception as e:  # noqa: BLE001
        errors.append(f"HID 枚举失败: {e}")
        log.warning("HID 枚举失败", exc_info=True)

    # 物理连接：libusb 视角
    usb_pairs = set()
    try:
        usb_pairs = set(_usb_entries())
    except Exception as e:  # noqa: BLE001
        errors.append(f"USB 枚举失败: {e}")
        log.warning("USB 枚举失败", exc_info=True)

    for vendor in vendors:
        for p in vendor["products"]:
            vid, pid = vendor["id"], p["id"]
            key = f"{vid}:{pid}"
            present = (vid, pid) in hid_pairs or (vid, pid) in usb_pairs
            if not present:
                continue
            brand = brand_of(vid)
            hint = "hid" if brand == "ttgk" else "winusb"
            result[key] = DeviceEntry(
                vid=vid, pid=pid, name=p["name"], icon=p["icon"],
                valid=p["valid"], additional_info=p["additional_info"],
                connected=True, transport_hint=hint,
            )

    # 已知历史设备（未插入时显示为未连接）
    if include_known:
        st = get_app_state()
        for item in st.list_known_devices():
            try:
                vid = int(item.get("vid", 0))
                pid = int(item.get("id", 0))
            except Exception:
                continue
            key = f"{vid}:{pid}"
            if key in result:
                continue
            p = find_product(vid, pid)
            if p is None:
                continue
            result[key] = DeviceEntry(
                vid=vid, pid=pid, name=p["name"], icon=p["icon"],
                valid=p["valid"], additional_info=p["additional_info"],
                connected=False,
                transport_hint="hid" if brand_of(vid) == "ttgk" else "winusb",
            )

    # 两个枚举通道全挂 → 说明环境有问题，而不是「没插设备」
    if errors and not hid_pairs and not usb_pairs:
        raise ScanError("；".join(errors))

    return list(result.values())



# ---------------- 打开设备 ----------------
def open_transport(entry: DeviceEntry) -> BaseTransport:
    """按品牌选择后端打开设备，返回可用的传输层"""
    brand = brand_of(entry.vid)
    errors: List[str] = []
    log.info("打开设备 %s (vid=%d pid=%d brand=%s)", entry.name, entry.vid, entry.pid, brand)

    if brand == "ttgk":
        # 1) HID 优先（零安装）
        if hid_available():
            try:
                paths = enumerate_hid(entry.vid, entry.pid)
                # 优先 usage_page 0xFF00（厂商自定义），其次任意
                paths.sort(key=lambda d: 0 if d.get("usage_page") == 0xFF00 else 1)
                log.info("发现 %d 个 HID 接口", len(paths))
                for d in paths:
                    try:
                        t = HidBackend(d["path"], d.get("serial_number") or "")
                        t.open()
                        log.info("已通过 HID 打开: usage_page=0x%04X",
                                 int(d.get("usage_page") or 0))
                        return t
                    except TransportError as e:
                        log.warning("HID 接口打开失败: %s", e)
                        errors.append(str(e))
            except Exception as e:  # noqa: BLE001
                log.exception("HID 枚举异常")
                errors.append(f"HID 枚举失败: {e}")
        else:
            log.warning("hidapi 不可用，跳过 HID 通道")

        # 2) WinUSB 兜底
        if usb_available():
            for dev in enumerate_usb():
                try:
                    if int(dev.idVendor) == entry.vid and int(dev.idProduct) == entry.pid:
                        log.info("尝试 WinUSB 兜底通道")
                        return UsbBackend(dev).open(need_ttgk_endpoints=True)
                except TransportError as e:
                    log.warning("WinUSB 打开失败: %s", e)
                    errors.append(str(e))
                except Exception as e:  # noqa: BLE001
                    log.exception("WinUSB 打开异常")
                    errors.append(str(e))
    else:  # 旋润：控制传输，必须 WinUSB/libusb
        if not usb_available():
            log.error("USB(libusb) 组件不可用")
            raise TransportError("USB(libusb) 组件不可用")
        for dev in enumerate_usb():
            try:
                if int(dev.idVendor) == entry.vid and int(dev.idProduct) == entry.pid:
                    return UsbBackend(dev).open(need_ttgk_endpoints=False)
            except TransportError as e:
                log.warning("旋润设备打开失败: %s", e)
                errors.append(str(e))
            except Exception as e:  # noqa: BLE001
                log.exception("旋润设备打开异常")
                errors.append(str(e))

    if not errors:
        log.error("设备未找到可用通道")
        raise TransportError("设备未连接或未找到可用的通信通道")
    log.error("打开设备失败，尝试过的通道错误: %s", errors)
    raise TransportError(errors[0] if errors else "打开设备失败")



def probe_openability(entry: DeviceEntry) -> Tuple[bool, str]:
    """探测设备是否可打开（不保留连接）"""
    try:
        t = open_transport(entry)
        t.close()
        return True, ""
    except TransportError as e:
        return False, str(e)
