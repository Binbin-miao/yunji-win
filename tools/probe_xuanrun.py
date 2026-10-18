# -*- coding: utf-8 -*-
"""旋润（XuanRun, VID 12230）设备控制传输诊断工具

用途：当设备「列表显示已连接，但点进去提示获取设备信息失败」时，
用本脚本逐层排查，定位到底是哪一步出问题。

排查层次：
    1. libusb 能否枚举到设备（能否看到 ≠ 能否通信）
    2. 设备描述符是否正常（速度 / 配置 / 接口）
    3. 能否 set_configuration（驱动是否绑定）
    4. 厂商控制传输能否得到响应（隔离器是否透传、供电是否充足）

用法：
    python tools/probe_xuanrun.py                 # 自动找所有 12230 设备
    python tools/probe_xuanrun.py --pid 61692     # 指定 PID
    python tools/probe_xuanrun.py --loop 10       # 连续读 10 次，测稳定性
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

from yunji.config import VENDER_ID_XUAN_RUN  # noqa: E402
from yunji.usb.usb_backend import (  # noqa: E402
    classify_usb_error,
    enumerate_usb,
    usb_available,
)

CMD_READ_FIRMWARE = 0xA0
CMD_READ_STATUS = 0xA3


def _hx(b):
    return b.hex(" ") if b else "(空)"


def probe_device(dev, loops: int) -> bool:
    """对单个设备做完整探测，返回是否成功"""
    print(f"\n{'=' * 62}")
    print(f"设备: VID={dev.idVendor:04X} PID={dev.idProduct:04X}")
    print(f"{'=' * 62}")

    # ---- 描述符 ----
    try:
        print(f"  bcdUSB        : {dev.bcdUSB:#06x}")
        print(f"  bDeviceClass  : {dev.bDeviceClass:#04x}")
        print(f"  bNumConfigs   : {dev.bNumConfigurations}")
        speed = getattr(dev, "speed", None)
        speed_name = {1: "低速 1.5M", 2: "全速 12M", 3: "高速 480M",
                      4: "超速 5G", 5: "超速+ 10G"}.get(speed, "未知")
        print(f"  速度          : {speed_name}  (隔离器通常只有全速 12M)")
    except Exception as e:  # noqa: BLE001
        print(f"  读取描述符失败: {e}")

    # ---- 配置 ----
    try:
        dev.set_configuration()
        print("  set_configuration : OK")
    except Exception as e:  # noqa: BLE001
        kind, msg = classify_usb_error(e)
        print(f"  set_configuration : 失败 [{kind}] {e}")
        print(f"    -> {msg.splitlines()[0]}")

    try:
        cfg = dev.get_active_configuration()
        print(f"  活动配置      : Config {cfg.bConfigurationValue}, "
              f"{cfg.bNumInterfaces} 个接口")
        for intf in cfg:
            print(f"    接口 {intf.bInterfaceNumber}: "
                  f"class={intf.bInterfaceClass:#04x} "
                  f"sub={intf.bInterfaceSubClass:#04x} "
                  f"端点={intf.bNumEndpoints}")
    except Exception as e:  # noqa: BLE001
        print(f"  读取配置失败  : {e}")

    # ---- 控制传输 ----
    print("\n  -- 厂商控制传输测试 --")
    ok_count = 0
    for i in range(loops):
        cmd = CMD_READ_FIRMWARE if i == 0 else CMD_READ_STATUS
        pkt = bytes([0xC1, 0xA6, cmd, 0, 0, 0, 0])
        t0 = time.monotonic()
        try:
            dev.ctrl_transfer(0x43, 0xA0, 0, 0x09A0, pkt, timeout=1000)
            time.sleep(0.005)
            resp = dev.ctrl_transfer(0xC3, 0xA1, 0, 0x09A0, 7, timeout=1000)
            ms = (time.monotonic() - t0) * 1000
            print(f"    #{i + 1} cmd={cmd:#04x} -> {_hx(bytes(resp))}  ({ms:.0f} ms)")
            ok_count += 1
        except Exception as e:  # noqa: BLE001
            kind, msg = classify_usb_error(e)
            print(f"    #{i + 1} cmd={cmd:#04x} -> 失败 [{kind}] {e}")
            print(f"         {msg.replace(chr(10), chr(10) + '         ')}")
            if kind in ("stale", "unsupported"):
                print("         （该错误重试无意义，停止后续测试）")
                break
        time.sleep(0.02)

    print(f"\n  结果: {ok_count}/{loops} 次成功")
    return ok_count > 0 and ok_count == loops


def main() -> int:
    ap = argparse.ArgumentParser(description="旋润设备控制传输诊断")
    ap.add_argument("--vid", type=lambda s: int(s, 0), default=VENDER_ID_XUAN_RUN)
    ap.add_argument("--pid", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--loop", type=int, default=3, help="控制传输重复次数（测稳定性）")
    args = ap.parse_args()

    print("旋润设备诊断工具")
    print(f"  VID = {args.vid} ({args.vid:#06x})"
          + (f"  PID = {args.pid} ({args.pid:#06x})" if args.pid else "  全部 PID"))

    if not usb_available():
        print("\n[失败] pyusb / libusb 不可用。请先安装：pip install pyusb libusb-package")
        return 2

    devs = []
    for d in enumerate_usb():
        try:
            if int(d.idVendor) != args.vid:
                continue
            if args.pid is not None and int(d.idProduct) != args.pid:
                continue
            devs.append(d)
        except Exception:
            continue

    if not devs:
        print(f"\n[失败] 未枚举到 VID={args.vid:#06x} 的设备。")
        print("  可能原因：")
        print("   · 设备未插入 / 隔离器未供电")
        print("   · 设备走的是 HID 通道而非 libusb（可先运行 tools/list_usb_devices.py 确认）")
        print("   · libusb 驱动未安装")
        return 1

    if len(devs) > 1:
        print(f"\n[注意] 枚举到 {len(devs)} 个同 VID 设备，将逐个测试。")
        print("       若同一个物理设备出现多个实例，说明枚举不稳定（隔离器供电常见）。")

    results = [probe_device(d, max(1, args.loop)) for d in devs]

    print(f"\n{'=' * 62}")
    if all(results):
        print("结论：控制传输正常。若软件仍报错，请附上 %APPDATA%\\YunjiSettings\\logs\\yunji.log")
        return 0
    print("结论：控制传输失败。请对照上面的错误类别：")
    print("  · stale       -> 设备被重新枚举，多为隔离器供电不足 / 链路不稳")
    print("  · unsupported -> WinUSB 未绑定到该设备实例，用 Zadig 重新安装")
    print("  · timeout     -> 设备无响应，可能供电不足或隔离器不透传厂商请求")
    print("  · io          -> 链路不稳定，检查线材与隔离器质量")
    return 1


if __name__ == "__main__":
    sys.exit(main())
