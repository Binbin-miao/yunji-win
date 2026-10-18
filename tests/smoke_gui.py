# -*- coding: utf-8 -*-
"""GUI 冒烟测试（offscreen）

覆盖：
- 启动 → 模拟设备 → 各页面导航 → 退出
- 列表页增量刷新（不重建控件）
- 后台扫描服务缓存
- ProEQ 新功能：旁通 / 增益补偿 / 多格式导入 / 目标曲线 / 滤波器类型 / 分享图
"""
import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))

errors = []


def hook(exc_type, exc, tb):
    errors.append("".join(traceback.format_exception(exc_type, exc, tb)))
    traceback.print_exception(exc_type, exc, tb)


sys.excepthook = hook

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from yunji.storage import get_app_state  # noqa: E402
from yunji.ui.fonts import apply_app_font  # noqa: E402
from yunji.ui.main_window import MainWindow  # noqa: E402
from yunji.ui.theme import QSS  # noqa: E402

# 预先同意协议（跳过启动弹窗）
st = get_app_state()
st.notice.data.update({"agreed": True, "notice_version": 1})
st.notice.save()

app = QApplication([])
print(">> 中文字体:", apply_app_font(app) or "(未找到，交给系统回退)")
app.setStyleSheet(QSS)
win = MainWindow()
win.show()
win.run_startup()

state = {"phase": 0}

APO_10BAND = """Preamp: -5.0 dB
Filter 1: ON LSC Fc 105 Hz Gain 5.5 dB Q 0.70
Filter 2: ON PK Fc 220 Hz Gain -2.1 dB Q 1.20
Filter 3: ON PK Fc 560 Hz Gain 1.4 dB Q 1.80
Filter 4: ON PK Fc 1200 Hz Gain -1.8 dB Q 2.00
Filter 5: ON PK Fc 2100 Hz Gain 2.6 dB Q 1.50
Filter 6: ON PK Fc 3000 Hz Gain 4.2 dB Q 2.20
Filter 7: ON PK Fc 4500 Hz Gain -3.0 dB Q 3.00
Filter 8: ON PK Fc 6500 Hz Gain 1.9 dB Q 2.50
Filter 9: ON PK Fc 9000 Hz Gain -2.4 dB Q 2.00
Filter 10: ON HSC Fc 10000 Hz Gain 3.2 dB Q 0.70
"""

GRAPHIC_EQ = ("GraphicEQ: " + "; ".join(
    f"{f} {v}" for f, v in [(20, -4), (50, -3), (100, -1), (200, 0.5),
                            (500, 1.5), (1000, 0), (2000, 3), (3000, 5),
                            (5000, 2), (8000, -1), (10000, -2)]))


def open_sim_xr():
    print(">> open xuanrun sim")
    win.use_simulator = True
    entry = [e for e in win.simulated_entries() if e.vid == 12230][0]
    win.open_device(entry)
    assert type(win.pages[-1]).__name__ == "XuanRunPage", type(win.pages[-1]).__name__


def test_xr_load_error():
    """模拟读取失败：应显示真实原因并出现「重试连接」按钮"""
    print(">> xuanrun load error UI")
    pg = win.pages[-1]
    assert type(pg).__name__ == "XuanRunPage"
    # 先确认正常状态下错误区是隐藏的
    assert not pg.err_label.isVisible(), "正常状态不应显示错误区"
    assert not pg.retry_btn.isVisible(), "正常状态不应显示重试按钮"

    fake = "控制传输(读)失败：设备句柄已失效（设备可能被重新枚举）。"
    pg._load_err(fake)

    assert pg.err_label.isVisible(), "失败后应显示错误详情"
    assert fake in pg.err_label.text(), f"未显示真实原因: {pg.err_label.text()!r}"
    assert pg.retry_btn.isVisible(), "失败后应出现重试按钮"
    assert pg.conn_label.text() == "未连接", pg.conn_label.text()

    # 恢复成功后应清除错误状态
    pg._apply({"firm": "8", "vol": 20, "l": 0, "r": 0,
               "filter": 0, "elevel": 0, "led": 0, "depop": 0})
    assert not pg.err_label.isVisible(), "恢复后错误区应隐藏"
    assert not pg.retry_btn.isVisible(), "恢复后重试按钮应隐藏"
    print("   错误提示 / 重试按钮 显隐正确")


def open_xr_filter():
    print(">> filter page")
    win.open_filter_page(win.session)
    assert type(win.pages[-1]).__name__ == "FilterPage"


def back2():
    print(">> back")
    win.go_back()
    win.go_back()
    assert type(win.pages[-1]).__name__ == "DeviceListPage"


def check_list_incremental():
    print(">> list incremental refresh")
    lp = win.list_page
    entries = win.scan() + win.simulated_entries()
    lp.apply_entries(entries)
    first = dict(lp._rows)
    lp.apply_entries(entries)          # 同样数据再刷一次
    second = dict(lp._rows)
    assert set(first) == set(second), "行集合不一致"
    for k in first:
        assert first[k] is second[k], f"行 {k} 被重建了（应原地更新）"
    print(f"   行数={len(second)}，控件复用正常")


def open_sim_tk():
    print(">> open ttgk sim (cb5100)")
    entry = [e for e in win.simulated_entries()
             if e.vid == 13058 and e.chip_type == "cb5100"][0]
    win.open_device(entry)
    assert type(win.pages[-1]).__name__ == "TtgkPage", type(win.pages[-1]).__name__


def test_tk_load_error():
    """TTGK 页面同样应显示真实原因与重试按钮"""
    print(">> ttgk load error UI")
    pg = win.pages[-1]
    assert type(pg).__name__ == "TtgkPage"
    assert not pg.err_label.isVisible(), "正常状态不应显示错误区"

    pg._load_err("读取失败：设备未在超时时间内响应。")
    assert pg.err_label.isVisible(), "失败后应显示错误详情"
    assert "超时" in pg.err_label.text(), pg.err_label.text()
    assert pg.retry_btn.isVisible(), "失败后应出现重试按钮"

    pg._apply({"firm": "0.8", "vol": 40, "mic": 0, "bal": 0, "gain": 0, "led": 0})
    assert not pg.err_label.isVisible(), "恢复后错误区应隐藏"
    assert not pg.retry_btn.isVisible(), "恢复后重试按钮应隐藏"
    print("   TTGK 错误提示显隐正确")


def open_tk_filter():
    print(">> ttgk filter")
    win.open_filter_page(win.session)
    win.go_back()


def open_proeq():
    print(">> proeq page")
    win.open_proeq_page(win.session)
    p = win.pages[-1]
    assert type(p).__name__ == "ProEqPage"
    state["proeq"] = p


def test_bypass():
    print(">> bypass toggle")
    p = state["proeq"]
    p._toggle_bypass()
    assert p._bypass_snapshot is not None, "未进入旁通状态"
    assert p.data.gain_list == [0.0] * 8, "旁通后增益未归零"
    p._toggle_bypass()
    assert p._bypass_snapshot is None, "未退出旁通状态"
    print("   旁通进入/退出正常")


def test_preamp():
    print(">> auto preamp")
    p = state["proeq"]
    p.data.gain_list = [6.0] * 8
    p.refresh_display()
    peak = p.data.peak_gain_db()
    assert peak > 0, f"峰值增益异常: {peak}"
    p._auto_preamp()
    assert p.data.offset < 0, f"未设置负偏移: {p.data.offset}"
    print(f"   峰值 {peak:+.1f} dB → offset {p.data.offset} dB")


def test_import_apo():
    print(">> import equalizer apo (10 bands -> 8)")
    p = state["proeq"]
    assert p.apply_import_text(APO_10BAND), "APO 导入失败"
    assert len(p.data.gain_list) == 8
    _assert_monotonic(p, "APO")
    nonzero = [g for g in p.data.gain_list if abs(g) > 0.01]
    assert nonzero, "导入后增益全为 0"
    print(f"   增益: {[round(g,1) for g in p.data.gain_list]}")


def _assert_monotonic(p, tag):
    fc = p.data.fc_list
    assert all(fc[i] < fc[i + 1] for i in range(len(fc) - 1)), \
        f"{tag}: 频点未严格递增 -> {fc}"
    assert fc[0] >= 20 and fc[-1] <= 20000, f"{tag}: 频点越界 -> {fc}"
    for g in p.data.gain_list:
        assert -12.0 <= g <= 12.0, f"{tag}: 增益越界 {g}"


def test_import_graphic():
    print(">> import graphiceq")
    p = state["proeq"]
    assert p.apply_import_text(GRAPHIC_EQ), "GraphicEQ 导入失败"
    _assert_monotonic(p, "GraphicEQ")
    print(f"   增益: {[round(g,1) for g in p.data.gain_list]}")


def test_import_wavelet():
    print(">> import wavelet")
    p = state["proeq"]
    txt = '{"graphicEQ": [[20,-4],[100,-1],[1000,0],[3000,5],[10000,-2]]}'
    assert p.apply_import_text(txt), "Wavelet 导入失败"


def test_import_native():
    print(">> import native json")
    p = state["proeq"]
    txt = '{"bands":[{"freq":80,"q":1.0,"gain":3.0},{"freq":900,"q":2.0,"gain":-2.0}]}'
    assert p.apply_import_text(txt), "原生格式导入失败"
    _assert_monotonic(p, "原生格式")
    # 80Hz 与 900Hz 应与默认频点合并后按频率排序
    assert 80 in p.data.fc_list, p.data.fc_list
    assert 900 in p.data.fc_list, p.data.fc_list
    i80 = p.data.fc_list.index(80)
    assert abs(p.data.gain_list[i80] - 3.0) < 1e-6, "增益未随频率一起搬移"
    print(f"   频点: {p.data.fc_list}")


def test_import_garbage():
    print(">> import garbage (应被拒绝)")
    p = state["proeq"]
    assert not p.apply_import_text("这不是 EQ 数据"), "垃圾输入未被拒绝"
    assert not p.apply_import_text(""), "空输入未被拒绝"


def test_target():
    print(">> target curve overlay")
    p = state["proeq"]
    from yunji.protocol import targets as tm
    avail = tm.list_targets()
    assert len(avail) >= 3, f"内置目标曲线不足: {len(avail)}"
    p._set_target(avail[0].id)
    assert p.curve._target is not None, "目标曲线未挂载"
    assert p.curve._target_dbs, "目标曲线未采样"
    p._set_target("__none__")
    assert p.curve._target is None
    print(f"   可用曲线: {[c.label for c in avail]}")


def test_shelf():
    print(">> filter type (experimental)")
    p = state["proeq"]
    from yunji.config import EQ_TYPE_LOW_SHELF, EQ_TYPE_PEAKING
    assert p._shelf_enabled is False, "shelf 应默认关闭"
    p._shelf_enabled = True            # 跳过确认弹窗，直接验证逻辑
    for lab in p.t_labels:
        lab.setVisible(True)
    p.refresh_display()
    p._cycle_type(0)
    assert p.data.type_list[0] == EQ_TYPE_LOW_SHELF, p.data.type_list[0]
    p._cycle_type(0)
    p._cycle_type(0)
    assert p.data.type_list[0] == EQ_TYPE_PEAKING, p.data.type_list[0]
    # 包内 type 字节应随类型变化
    p.data.type_list[0] = EQ_TYPE_LOW_SHELF
    assert p.data.band_packet(0)[34] == EQ_TYPE_LOW_SHELF
    p.data.type_list[0] = EQ_TYPE_PEAKING
    assert p.data.band_packet(0)[34] == EQ_TYPE_PEAKING
    print("   类型循环与包字节正常")


def test_share_card():
    print(">> share card render")
    from yunji.ui.share_card import render_share_card
    from yunji.protocol import targets as tm
    p = state["proeq"]
    pm = render_share_card(p.data, p.entry.display_name, tm.list_targets()[0])
    assert not pm.isNull(), "渲染结果为空"
    assert pm.width() == 960 and pm.height() == 720, (pm.width(), pm.height())
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "share.png")
        assert pm.save(out, "PNG"), "PNG 保存失败"
        assert os.path.getsize(out) > 5000, "导出的 PNG 过小"
    print("   PNG 渲染与保存正常（临时目录）")


def test_curve_hover():
    print(">> curve hover readout")
    p = state["proeq"]
    c = p.curve
    assert c._dbs, "曲线未缓存"
    assert len(c._freqs) == len(c._dbs)
    v = c._interp_cached(1000.0)
    assert isinstance(v, float)
    c._hover_freq = 1000.0
    c.update()                       # 触发重绘（含悬停绘制分支）
    c._hover_freq = None
    print(f"   1kHz 读数 {v:+.2f} dB")


def open_ezeq():
    print(">> ezeq page")
    win.open_ezeq_page(win.session)
    p = win.pages[-1]
    assert type(p).__name__ == "EzeqPage"
    p._switch_config("game")
    p._random()
    p.data.gain_list[0] = 2.5
    p._after_change()


def open_about():
    print(">> about page")
    win.show_about()
    assert type(win.pages[-1]).__name__ == "AboutPage"


def test_scan_service():
    print(">> scan service")
    svc = win.scan_service
    assert svc is not None
    e1 = svc.entries()
    e2 = win.scan()
    assert e1 == e2, "缓存读取不一致"
    print(f"   缓存条目 {len(e1)} 个")


def finish():
    print(">> finish")
    win._close_session()
    win.scan_service.shutdown()
    app.quit()
    if errors:
        print("SMOKE TEST FAILED")
        for e in errors:
            print(e)
        sys.exit(1)
    print("SMOKE TEST PASSED")


steps = [
    (400, open_sim_xr),
    (700, test_xr_load_error),
    (900, open_xr_filter),
    (1300, back2),
    (1600, check_list_incremental),
    (2000, test_scan_service),
    (2300, open_sim_tk),
    (2600, test_tk_load_error),
    (2700, open_tk_filter),
    (3000, open_proeq),
    (3300, test_bypass),
    (3600, test_preamp),
    (3900, test_import_apo),
    (4200, test_import_graphic),
    (4500, test_import_wavelet),
    (4800, test_import_native),
    (5100, test_import_garbage),
    (5400, test_target),
    (5700, test_shelf),
    (6000, test_curve_hover),
    (6300, test_share_card),
    (6700, open_ezeq),
    (7200, open_about),
    (7700, finish),
]
for ms, fn in steps:
    QTimer.singleShot(ms, fn)

sys.exit(app.exec())
