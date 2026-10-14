# -*- coding: utf-8 -*-
"""GUI 冒烟测试（offscreen）：启动 -> 模拟设备 -> 各页面导航 -> 退出"""
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

from yunji.storage import AppState  # noqa: E402
from yunji.ui.main_window import MainWindow  # noqa: E402
from yunji.ui.theme import QSS  # noqa: E402

# 预先同意协议（跳过启动弹窗）
st = AppState()
st.notice.data.update({"agreed": True, "notice_version": 1})
st.notice.save()

app = QApplication([])
app.setStyleSheet(QSS)
win = MainWindow()
win.show()
win.run_startup()

state = {"phase": 0}


def open_sim_xr():
    print(">> open xuanrun sim")
    win.use_simulator = True
    entry = [e for e in win.simulated_entries() if e.vid == 12230][0]
    win.open_device(entry)
    assert type(win.pages[-1]).__name__ == "XuanRunPage", type(win.pages[-1]).__name__


def open_xr_filter():
    print(">> filter page")
    win.open_filter_page(win.session)
    assert type(win.pages[-1]).__name__ == "FilterPage"


def back2():
    print(">> back")
    win.go_back()
    win.go_back()
    assert type(win.pages[-1]).__name__ == "DeviceListPage"


def open_sim_tk():
    print(">> open ttgk sim (cb5100)")
    entry = [e for e in win.simulated_entries() if e.vid == 13058 and e.chip_type == "cb5100"][0]
    win.open_device(entry)
    assert type(win.pages[-1]).__name__ == "TtgkPage", type(win.pages[-1]).__name__


def open_tk_filter():
    print(">> ttgk filter")
    win.open_filter_page(win.session)
    win.go_back()


def open_proeq():
    print(">> proeq page")
    win.open_proeq_page(win.session)
    p = win.pages[-1]
    assert type(p).__name__ == "ProEqPage"
    p._edit_gain  # touch


def open_ezeq():
    print(">> ezeq page")
    win.open_ezeq_page(win.session)
    p = win.pages[-1]
    assert type(p).__name__ == "EzeqPage"
    # 模拟若干操作
    p._switch_config("game")
    p._random()
    p.data.gain_list[0] = 2.5
    p._after_change()


def open_about():
    print(">> about page")
    win.show_about()
    assert type(win.pages[-1]).__name__ == "AboutPage"


def finish():
    print(">> finish")
    win._close_session()
    app.quit()
    if errors:
        print("SMOKE TEST FAILED")
        for e in errors:
            print(e)
        sys.exit(1)
    print("SMOKE TEST PASSED")


steps = [
    (400, open_sim_xr),
    (1100, open_xr_filter),
    (1600, back2),
    (2100, open_sim_tk),
    (2700, open_tk_filter),
    (3200, open_proeq),
    (3900, open_ezeq),
    (4600, open_about),
    (5100, finish),
]
for ms, fn in steps:
    QTimer.singleShot(ms, fn)

sys.exit(app.exec())
