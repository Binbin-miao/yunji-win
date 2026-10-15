# -*- coding: utf-8 -*-
"""列出当前连接的所有 USB / HID 设备，并标注是否已被本工具支持

用途：当你手上有设备但软件里不显示时，用这个脚本查出它的 VID/PID，
再按 docs/设备适配.md 的说明加进产品表即可。

用法：
    python tools/list_usb_devices.py

输出示例：
    [已知] TTGK   vid=13058 pid=17388  HID    凌云剑
    [未知] -      vid=13058 pid=17399  HID    （未收录，可考虑加入产品表）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

from yunji.config import VENDER_ID_TTGK, VENDER_ID_XUAN_RUN  # noqa: E402
from yunji.usb import scanner  # noqa: E402
from yunji.usb.hid_backend import enumerate_hid, hid_available  # noqa: E402
from yunji.usb.usb_backend import enumerate_usb, usb_available  # noqa: E402


def _known(vid: int, pid: int):
    p = scanner.find_product(vid, pid)
    return p["name"] if p else None


def _brand(vid: int) -> str:
    return {"ttgk": "TTGK", "xuanrun": "旋润"}.get(scanner.brand_of(vid), "-")


def main() -> int:
    seen = {}

    if hid_available():
        for d in enumerate_hid():
            vid = int(d.get("vendor_id") or 0)
            pid = int(d.get("product_id") or 0)
            seen.setdefault((vid, pid), {"hid": True, "usb": False,
                                         "usage_page": d.get("usage_page")})
    else:
        print("提示：hidapi 不可用，跳过 HID 枚举")

    if usb_available():
        for dev in enumerate_usb():
            try:
                vid, pid = int(dev.idVendor), int(dev.idProduct)
            except Exception:
                continue
            e = seen.setdefault((vid, pid), {"hid": False, "usb": False,
                                             "usage_page": None})
            e["usb"] = True
    else:
        print("提示：pyusb/libusb 不可用，跳过 USB 枚举")

    if not seen:
        print("未枚举到任何设备。请确认设备已插入，且 hidapi / pyusb 已安装。")
        return 1

    interesting = []
    others = []
    for (vid, pid), info in seen.items():
        name = _known(vid, pid)
        row = (vid, pid, info, name)
        # 云姬设备或未被收录的厂商自定义设备（usage_page 0xFF00）优先展示
        if name or vid in (VENDER_ID_TTGK, VENDER_ID_XUAN_RUN):
            interesting.append(row)
        else:
            others.append(row)

    def dump(rows, title):
        if not rows:
            return
        print(f"\n=== {title} ===")
        print(f"{'状态':<6} {'品牌':<6} {'VID':<7} {'PID':<7} {'通道':<8} 名称")
        for vid, pid, info, name in sorted(rows):
            tag = "已知" if name else "未知"
            chans = ("HID" if info["hid"] else "") + ("/USB" if info["usb"] else "")
            print(f"{tag:<6} {_brand(vid):<6} {vid:<7} {pid:<7} {chans or '-':<8} "
                  f"{name or '（未收录）'}")

    dump(interesting, "云姬相关设备")
    dump(others, "其他 USB/HID 设备")

    print("\n说明：")
    print("  · 「已知」= 已收录在产品表中，软件里会正常显示")
    print("  · 「未知」+ VID=13058(TTGK) = 协议通用，加入产品表后大概率可用")
    print("  · 「未知」+ 其他 VID = 需要先确认通信协议，见 docs/设备适配.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
