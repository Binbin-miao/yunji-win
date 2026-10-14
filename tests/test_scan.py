# -*- coding: utf-8 -*-
"""扫描、协议校验、存储层测试（覆盖本轮 bug 修复）

对应改动：
- A4 产品表进程内缓存
- A6/B2 响应头与长度校验
- B4 HID 报告描述符解析
- 存储层原子写入与线程安全
- 资源覆盖优先级
"""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

from yunji.devices.ttgk import CMD_BALANCE, CMD_FILTER, CMD_VOLUME, TtgkDevice  # noqa: E402
from yunji.storage import JsonStore  # noqa: E402
from yunji.usb import scanner  # noqa: E402
from yunji.usb.base import DeviceEntry, TransportError  # noqa: E402
from yunji.usb.hid_report import find_output_report, parse_output_reports  # noqa: E402


# ============================================================ 产品表缓存
class TestProductCache(unittest.TestCase):
    def setUp(self):
        scanner.invalidate_product_cache()

    def tearDown(self):
        scanner.invalidate_product_cache()

    def test_reads_file_only_once(self):
        with mock.patch.object(scanner, "_read_product_list",
                               wraps=scanner._read_product_list) as m:
            for _ in range(20):
                scanner.load_product_list()
            self.assertEqual(m.call_count, 1, "产品表被重复读盘")

    def test_find_product_uses_index(self):
        with mock.patch.object(scanner, "_read_product_list",
                               wraps=scanner._read_product_list) as m:
            for _ in range(50):
                scanner.find_product(13058, 17388)
            self.assertEqual(m.call_count, 1)

    def test_find_product_result(self):
        p = scanner.find_product(13058, 17388)
        self.assertIsNotNone(p)
        self.assertEqual(p["vendor_name"], "TTGK")
        self.assertEqual(p["name"], "凌云剑")

    def test_find_unknown_returns_none(self):
        self.assertIsNone(scanner.find_product(1, 2))

    def test_invalidate_forces_reread(self):
        with mock.patch.object(scanner, "_read_product_list",
                               wraps=scanner._read_product_list) as m:
            scanner.load_product_list()
            scanner.invalidate_product_cache()
            scanner.load_product_list()
            self.assertEqual(m.call_count, 2)


# ============================================================ 扫描合并
class _UsbStub:
    """模拟 pyusb 的 device 对象（只暴露用到的两个属性）"""

    def __init__(self, vid, pid):
        self.idVendor = vid
        self.idProduct = pid


class TestScanDevices(unittest.TestCase):
    def setUp(self):
        scanner.invalidate_product_cache()

    def _entry(self, vid, pid):
        return {"vendor_id": vid, "product_id": pid, "path": b"x",
                "usage_page": 0xFF00, "serial_number": ""}

    def test_connected_device_detected(self):
        with mock.patch.object(scanner, "enumerate_hid",
                               return_value=[self._entry(13058, 17388)]), \
             mock.patch.object(scanner, "enumerate_usb", return_value=[]):
            entries = scanner.scan_devices(include_known=False)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].connected)
        self.assertEqual(entries[0].name, "凌云剑")

    def test_unplugged_device_absent(self):
        with mock.patch.object(scanner, "enumerate_hid", return_value=[]), \
             mock.patch.object(scanner, "enumerate_usb", return_value=[]):
            entries = scanner.scan_devices(include_known=False)
        self.assertEqual(entries, [])

    def test_both_enumerations_failing_raises(self):
        """两个枚举通道都挂掉时应报错，而不是静默返回空列表"""
        with mock.patch.object(scanner, "enumerate_hid",
                               side_effect=RuntimeError("hid boom")), \
             mock.patch.object(scanner, "enumerate_usb",
                               side_effect=RuntimeError("usb boom")):
            with self.assertRaises(scanner.ScanError) as ctx:
                scanner.scan_devices(include_known=False)
        msg = str(ctx.exception)
        self.assertIn("hid boom", msg)
        self.assertIn("usb boom", msg)

    def test_one_channel_ok_does_not_raise(self):
        """只有一个通道出错（另一个正常）时不应报错"""
        with mock.patch.object(scanner, "enumerate_hid",
                               side_effect=RuntimeError("hid boom")), \
             mock.patch.object(scanner, "enumerate_usb",
                               return_value=[_UsbStub(13058, 17388)]):
            entries = scanner.scan_devices(include_known=False)
        self.assertEqual(len(entries), 1)

    def test_known_devices_merged(self):
        from yunji.storage import get_app_state
        st = get_app_state()
        st.remember_device("凌云剑", 17388, 13058)
        with mock.patch.object(scanner, "enumerate_hid", return_value=[]), \
             mock.patch.object(scanner, "enumerate_usb", return_value=[]):
            entries = scanner.scan_devices(include_known=True)
        hit = [e for e in entries if e.pid == 17388]
        self.assertEqual(len(hit), 1)
        self.assertFalse(hit[0].connected)

    def test_uses_cached_app_state(self):
        """scan_devices 不应重复构造 AppState"""
        from yunji import storage
        with mock.patch.object(storage, "AppState",
                               side_effect=AssertionError("不应新建 AppState")), \
             mock.patch.object(scanner, "enumerate_hid", return_value=[]), \
             mock.patch.object(scanner, "enumerate_usb", return_value=[]):
            scanner.scan_devices(include_known=True)


# ============================================================ 响应校验
class FakeTransport:
    """按脚本依次返回预设响应；记录所有写入"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.writes = []

    def hid_write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def hid_read(self, size=64, timeout_ms=1000):
        if self.responses:
            return self.responses.pop(0)
        return b""


def _resp(cmd, payload=b"", length=64):
    """构造设备响应： [0x4B, 0x80, cmd, 0x00, <payload...>] 补零到 length

    与协议一致：有效数据从下标 4 开始（read_vol 取 resp[4:6]，
    read_filter 取 resp[4]，read_balance 取 resp[4]=arg 与 resp[5:7]）。
    """
    body = bytes([0x4B, 0x80, cmd, 0x00]) + payload
    return body + bytes(max(0, length - len(body)))


def _vol_payload(level):
    """音量/麦克风按 level*256 小端编码"""
    v = (level * 256) & 0xFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF])



class TestResponseValidation(unittest.TestCase):
    """B2：丢弃头部/CMD/长度不匹配的响应"""

    def _dev(self, responses):
        return TtgkDevice(FakeTransport(responses))

    def test_correct_response_accepted(self):
        dev = self._dev([_resp(CMD_VOLUME, _vol_payload(12))])
        self.assertEqual(dev.read_vol(), 12)

    def test_wrong_cmd_discarded(self):
        """先来一条其他命令的延迟回包，应被丢弃后继续等待正确响应"""
        dev = self._dev([
            _resp(CMD_FILTER, bytes([3])),      # 陈旧回包
            _resp(CMD_VOLUME, _vol_payload(10)),
        ])
        self.assertEqual(dev.read_vol(), 10)

    def test_bad_header_discarded(self):
        dev = self._dev([
            b"\x00\x00\x00" + bytes(61),
            _resp(CMD_VOLUME, _vol_payload(8)),
        ])
        self.assertEqual(dev.read_vol(), 8)

    def test_short_response_discarded(self):
        dev = self._dev([
            bytes([0x4B, 0x80, CMD_VOLUME, 0x00]),   # 长度不足
            _resp(CMD_VOLUME, _vol_payload(7)),
        ])
        self.assertEqual(dev.read_vol(), 7)

    def test_all_bad_raises(self):
        dev = self._dev([_resp(CMD_FILTER, bytes([1]))] * 8)
        with self.assertRaises(TransportError):
            dev.read_vol()

    def test_no_response_raises(self):
        dev = self._dev([])
        with self.assertRaises(TransportError):
            dev.read_vol()

    def test_balance_arg_mismatch_discarded(self):
        """平衡读取依赖 arg 回显区分左右，错位响应必须丢弃"""
        dev = self._dev([
            _resp(CMD_BALANCE, bytes([1]) + _vol_payload(5)),   # arg=1，但请求 arg=0
            _resp(CMD_BALANCE, bytes([0]) + _vol_payload(2)),
        ])
        r = dev._read_raw(CMD_BALANCE,
                          bytes([0x4B, 0x80, CMD_BALANCE, 4, 0]),
                          expect_len=7, expect_arg=0)
        self.assertIsNotNone(r)
        self.assertEqual(r[4], 0)

    def test_filter_read(self):
        dev = self._dev([_resp(CMD_FILTER, bytes([2]))])
        self.assertEqual(dev.read_filter(), 2)

    def test_write_propagates_error(self):
        class Boom(FakeTransport):
            def hid_write(self, data):
                raise TransportError("device gone")

        dev = TtgkDevice(Boom([]))
        with self.assertRaises(TransportError):
            dev.set_led(True)


class TestUploadEqConfirmation(unittest.TestCase):
    """upload_eq 必须区分「已写入但确认失败」与成功"""

    def test_returns_false_when_confirm_fails(self):
        dev = TtgkDevice(FakeTransport([]))     # 读音量必然失败
        self.assertFalse(dev.upload_eq(__import__(
            "yunji.protocol.eqdata", fromlist=["EQData"]).EQData()))

    def test_returns_true_when_confirmed(self):
        # 音量读取成功 → 后续 set_vol 写入成功
        responses = [_resp(CMD_VOLUME, _vol_payload(5))]
        dev = TtgkDevice(FakeTransport(responses))
        from yunji.protocol.eqdata import EQData
        self.assertTrue(dev.upload_eq(EQData()))

    def test_write_sequence(self):
        """写入顺序：8 段包 → EQ 生效提交 → 读音量 → 音量复位 → 提交"""
        t = FakeTransport([_resp(CMD_VOLUME, _vol_payload(5))])
        dev = TtgkDevice(t)
        from yunji.protocol.eqdata import EQData
        dev.upload_eq(EQData())
        self.assertEqual(len(t.writes), 12)
        for i in range(8):
            self.assertEqual(t.writes[i][:3], bytes([0x4B, 0x01, 0x09]))
            self.assertEqual(t.writes[i][5], i)          # 段号
        self.assertEqual(t.writes[8][:4], bytes([0x4B, 0x01, 0x0A, 4]))
        self.assertEqual(t.writes[9][:3], bytes([0x4B, 0x80, CMD_VOLUME]))


# ============================================================ HID 报告描述符
class TestHidReportParser(unittest.TestCase):
    # 与真机同构的最小描述符：两个输出报告 0x4B / 0x54，负载各 63 字节
    DESC = bytes([
        0x06, 0x00, 0xFF,          # Usage Page (Vendor)
        0x09, 0x01,                # Usage
        0xA1, 0x01,                # Collection (Application)
        0x85, 0x4B,                #   Report ID (0x4B)
        0x75, 0x08,                #   Report Size (8)
        0x95, 0x3F,                #   Report Count (63)
        0x91, 0x02,                #   Output
        0x85, 0x54,                #   Report ID (0x54)
        0x75, 0x08,                #   Report Size (8)
        0x95, 0x3F,                #   Report Count (63)
        0x91, 0x02,                #   Output
        0xC0,                      # End Collection
    ])

    def test_parses_two_output_reports(self):
        reports = parse_output_reports(self.DESC)
        self.assertEqual(reports, [(0x4B, 63), (0x54, 63)])

    def test_find_by_id(self):
        self.assertEqual(find_output_report(self.DESC, 0x4B), 63)
        self.assertEqual(find_output_report(self.DESC, 0x54), 63)

    def test_missing_id_returns_none(self):
        self.assertIsNone(find_output_report(self.DESC, 0x99))

    def test_input_reports_ignored(self):
        desc = bytes([0x85, 0x01, 0x75, 0x08, 0x95, 0x08, 0x81, 0x02])
        self.assertEqual(parse_output_reports(desc), [])

    def test_feature_reports_ignored(self):
        desc = bytes([0x85, 0x01, 0x75, 0x08, 0x95, 0x08, 0xB1, 0x02])
        self.assertEqual(parse_output_reports(desc), [])

    def test_empty_descriptor(self):
        self.assertEqual(parse_output_reports(b""), [])

    def test_truncated_descriptor_does_not_crash(self):
        self.assertEqual(parse_output_reports(self.DESC[:6]), [])

    def test_long_item_skipped(self):
        desc = bytes([0xFE, 0x03, 0x00]) + bytes([1, 2, 3]) + self.DESC
        self.assertEqual(parse_output_reports(desc), [(0x4B, 63), (0x54, 63)])

    def test_report_without_id(self):
        desc = bytes([0x75, 0x08, 0x95, 0x10, 0x91, 0x02])
        self.assertEqual(parse_output_reports(desc), [(0, 16)])


# ============================================================ 存储
class TestJsonStore(unittest.TestCase):
    def test_atomic_write_and_reload(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.json"
            s = JsonStore(p, {"a": 1})
            self.assertEqual(s.data, {"a": 1})
            s.data["a"] = 2
            s.save()
            self.assertTrue(p.exists())
            self.assertFalse((Path(td) / "t.json.tmp").exists(), "临时文件未清理")
            self.assertEqual(JsonStore(p, {}).data, {"a": 2})

    def test_corrupt_file_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "t.json"
            p.write_text("{not json", encoding="utf-8")
            self.assertEqual(JsonStore(p, {"x": 0}).data, {"x": 0})

    def test_default_not_shared_between_instances(self):
        with tempfile.TemporaryDirectory() as td:
            d = {"data": []}
            a = JsonStore(Path(td) / "a.json", d)
            a.data["data"].append(1)
            b = JsonStore(Path(td) / "b.json", d)
            self.assertEqual(b.data["data"], [], "默认值被共享修改")

    def test_concurrent_read_write(self):
        """后台扫描线程与主线程会并发访问，不能抛异常"""
        with tempfile.TemporaryDirectory() as td:
            s = JsonStore(Path(td) / "t.json", {"n": 0})
            errors = []

            def worker():
                try:
                    for _ in range(60):
                        s.data["n"] = s.data.get("n", 0) + 1
                        s.save()
                except Exception as e:  # noqa: BLE001
                    errors.append(e)

            ts = [threading.Thread(target=worker) for _ in range(4)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            self.assertEqual(errors, [])


class TestResolveAsset(unittest.TestCase):
    def test_override_takes_priority(self):
        from yunji import storage
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {"APPDATA": td}):
                ov = Path(td) / "YunjiSettings" / "assets-override" / "icons"
                ov.mkdir(parents=True)
                (ov / "x.png").write_bytes(b"OVERRIDE")
                got = storage.resolve_asset("icons/x.png")
                self.assertEqual(got.read_bytes(), b"OVERRIDE")

    def test_fallback_to_builtin(self):
        from yunji import storage
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {"APPDATA": td}):
                got = storage.resolve_asset("product-list/product-list.json")
                self.assertTrue(got.exists())
                self.assertIn("assets", str(got))


if __name__ == "__main__":
    unittest.main(verbosity=2)
