# -*- coding: utf-8 -*-
"""设备扫描与打开：合并产品表配置与物理连接状态"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

from ..config import VENDER_ID_TTGK, VENDER_ID_XUAN_RUN
from ..storage import resolve_asset
from .base import BaseTransport, DeviceEntry, TransportError
from .hid_backend import HidBackend, enumerate_hid, hid_available
from .usb_backend import UsbBackend, enumerate_usb, usb_available


# ---------------- 产品表 ----------------
def load_product_list() -> List[dict]:
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


def find_product(vid: int, pid: int) -> Optional[dict]:
    for vendor in load_product_list():
        if vendor["id"] != vid:
            continue
        for p in vendor["products"]:
            if p["id"] == pid:
                return {**p, "vendor_id": vid, "vendor_name": vendor["name"]}
    return None


def brand_of(vid: int) -> str:
    if vid == VENDER_ID_XUAN_RUN:
        return "xuanrun"
    if vid == VENDER_ID_TTGK:
        return "ttgk"
    return "unknown"


# ---------------- 扫描 ----------------
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
    """扫描当前连接的云姬设备（含已知历史设备占位）"""
    vendors = load_product_list()
    result: Dict[str, DeviceEntry] = {}

    # 物理连接：HID 视角
    hid_pairs = set()
    for d in _hid_entries():
        hid_pairs.add((int(d.get("vendor_id", 0)), int(d.get("product_id", 0))))
    # 物理连接：libusb 视角
    usb_pairs = set(_usb_entries())

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
        from ..storage import AppState
        st = AppState()
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
    return list(result.values())


# ---------------- 打开设备 ----------------
def open_transport(entry: DeviceEntry) -> BaseTransport:
    """按品牌选择后端打开设备，返回可用的传输层"""
    brand = brand_of(entry.vid)
    errors: List[str] = []

    if brand == "ttgk":
        # 1) HID 优先（零安装）
        if hid_available():
            try:
                paths = enumerate_hid(entry.vid, entry.pid)
                # 优先 usage_page 0xFF00（厂商自定义），其次任意
                paths.sort(key=lambda d: 0 if d.get("usage_page") == 0xFF00 else 1)
                for d in paths:
                    try:
                        t = HidBackend(d["path"], d.get("serial_number") or "")
                        t.open()
                        return t
                    except TransportError as e:
                        errors.append(str(e))
            except Exception as e:  # noqa: BLE001
                errors.append(f"HID 枚举失败: {e}")
        # 2) WinUSB 兜底
        if usb_available():
            for dev in enumerate_usb():
                try:
                    if int(dev.idVendor) == entry.vid and int(dev.idProduct) == entry.pid:
                        return UsbBackend(dev).open(need_ttgk_endpoints=True)
                except TransportError as e:
                    errors.append(str(e))
                except Exception as e:  # noqa: BLE001
                    errors.append(str(e))
    else:  # 旋润：控制传输，必须 WinUSB/libusb
        if not usb_available():
            raise TransportError("USB(libusb) 组件不可用")
        for dev in enumerate_usb():
            try:
                if int(dev.idVendor) == entry.vid and int(dev.idProduct) == entry.pid:
                    return UsbBackend(dev).open(need_ttgk_endpoints=False)
            except TransportError as e:
                errors.append(str(e))
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))

    if not errors:
        raise TransportError("设备未连接或未找到可用的通信通道")
    raise TransportError(errors[0] if errors else "打开设备失败")


def probe_openability(entry: DeviceEntry) -> Tuple[bool, str]:
    """探测设备是否可打开（不保留连接）"""
    try:
        t = open_transport(entry)
        t.close()
        return True, ""
    except TransportError as e:
        return False, str(e)
