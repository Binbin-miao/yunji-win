# -*- coding: utf-8 -*-
"""旋润（XuanRun, VID 12230）设备控制传输诊断工具

用途：当设备「列表显示已连接，但点进去提示获取设备信息失败」时，
用本脚本逐层排查，定位到底是哪一步出问题。

排查层次：
    1. libusb 能否枚举到设备（能否看到 ≠ 能否通信）
    2. 设备描述符是否正常（速度 / 配置 / 接口）
    3. 写入命令是否成功
    4. 读取响应是否成功（写成功但读失败，说明设备收到命令后才断开）

用法：
    python tools/probe_xuanrun.py                 # 自动找所有 12230 设备
    python tools/probe_xuanrun.py --pid 61692     # 指定 PID
    python tools/probe_xuanrun.py --loop 10       # 连续读 10 次，测稳定性
    python tools/probe_xuanrun.py --config        # 额外调用 set_configuration（对照测试）
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


def _report_error(tag, e):
    kind, msg = classify_usb_error(e)
    print(f"    {tag} -> 失败 [{kind}] {e}")
    for line in msg.splitlines():
        print(f"         {line}")
    return kind


def probe_device(dev, loops: int, do_config: bool) -> bool:
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
        print(f"  速度          : {speed_name}")
    except Exception as e:  # noqa: BLE001
        print(f"  读取描述符失败: {e}")

    # ---- 配置 ----
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
        print(f"  读取活动配置失败: {e}")

    if do_config:
        print("\n  -- set_configuration（对照测试）--")
        try:
            dev.set_configuration()
            print("    OK")
        except Exception as e:  # noqa: BLE001
            _report_error("set_configuration", e)
    else:
        print("\n  （跳过 set_configuration；加 --config 可对照测试）")

    # ---- 控制传输：写 / 读 分开报告 ----
    print("\n  -- 厂商控制传输测试（写 / 读 分步）--")
    ok = 0
    for i in range(loops):
        cmd = CMD_READ_FIRMWARE if i == 0 else CMD_READ_STATUS
        pkt = bytes([0xC1, 0xA6, cmd, 0, 0, 0, 0])
        print(f"    #{i + 1} cmd={cmd:#04x}")

        # 写
        t0 = time.monotonic()
        try:
            n = dev.ctrl_transfer(0x43, 0xA0, 0, 0x09A0, pkt, timeout=1000)
            print(f"       写   : OK ({n} 字节, {(time.monotonic() - t0) * 1000:.0f} ms)")
        except Exception as e:  # noqa: BLE001
            kind = _report_error("写", e)
            if kind in ("stale", "unsupported"):
                print("         （该错误重试无意义，停止后续测试）")
            break

        # 读
        time.sleep(0.005)
        t0 = time.monotonic()
        try:
            resp = dev.ctrl_transfer(0xC3, 0xA1, 0, 0x09A0, 7, timeout=1000)
            print(f"       读   : OK {_hx(bytes(resp))} "
                  f"({(time.monotonic() - t0) * 1000:.0f} ms)")
            ok += 1
        except Exception as e:  # noqa: BLE001
            kind = _report_error("读", e)
            if kind == "stale":
                print("         注意：写成功但读失败 —— 设备收到命令后才断开，")
                print("         通常是设备固件在该命令下重置，或隔离器下游掉电。")
            if kind in ("stale", "unsupported"):
                break
        time.sleep(0.02)

    print(f"\n  结果: {ok}/{loops} 次完整成功")
    return ok == loops and loops > 0


def main() -> int:
    ap = argparse.ArgumentParser(description="旋润设备控制传输诊断")
    ap.add_argument("--vid", type=lambda s: int(s, 0), default=VENDER_ID_XUAN_RUN)
    ap.add_argument("--pid", type=lambda s: int(s, 0), default=None)
    ap.add_argument("--loop", type=int, default=3, help="控制传输重复次数（测稳定性）")
    ap.add_argument("--config", action="store_true",
                    help="额外调用 set_configuration 做对照测试")
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
        print("   · 设备走的是 HID 通道而非 libusb（可先运行 tools/list_usb_devices.py）")
        print("   · libusb 驱动未安装")
        return 1

    if len(devs) > 1:
        print(f"\n[注意] 枚举到 {len(devs)} 个同 VID 设备，将逐个测试。")
        print("       同一物理设备出现多个实例，说明枚举不稳定。")

    results = [probe_device(d, max(1, args.loop), args.config) for d in devs]

    print(f"\n{'=' * 62}")
    if all(results):
        print("结论：控制传输完全正常。")
        print("  若软件仍报错，说明问题出在软件的会话/扫描流程，请附上：")
        print("  %APPDATA%\\YunjiSettings\\logs\\yunji.log")
        return 0

    print("结论：控制传输失败。对照下面的类别判断：")
    print("  · 写阶段就 stale  -> 设备在收到命令前已消失：供电 / 链路问题")
    print("  · 写成功但读 stale -> 设备收到命令后断开：固件重置或隔离器下游掉电")
    print("  · unsupported     -> WinUSB 未绑定到该设备实例（用 Zadig 重新安装）")
    print("  · timeout         -> 设备无响应：隔离器不透传厂商请求，或供电不足")
    print("  · io              -> 链路不稳定：检查线材与隔离器")
    return 1


if __name__ == "__main__":
    sys.exit(main())
