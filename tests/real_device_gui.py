# -*- coding: utf-8 -*-
"""真机 GUI 测试：用真实设备打开 TTGK 页面并截图"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402


def _load_fonts():
    import glob
    for pat in (r"C://Windows//Fonts//msyh.ttc", r"C://Windows//Fonts//msyh.ttf",
                r"C://Windows//Fonts//msyhbd.ttc", r"C://Windows//Fonts//simhei.ttf",
                r"C://Windows//Fonts//simsun.ttc"):
        for p in glob.glob(pat):
            try:
                QFontDatabase.addApplicationFont(p)
            except Exception:
                pass

from PySide6.QtWidgets import QApplication  # noqa: E402

from yunji.storage import AppState  # noqa: E402
from yunji.ui.main_window import MainWindow  # noqa: E402
from yunji.ui.theme import QSS  # noqa: E402
from yunji.usb import scanner  # noqa: E402

st = AppState()
st.notice.data.update({"agreed": True, "notice_version": 1})
st.notice.save()

app = QApplication([])
_load_fonts()
app.setStyleSheet(QSS)
win = MainWindow()
win.resize(500, 840)
win.show()

OUT = os.path.join(ROOT, "shots")
os.makedirs(OUT, exist_ok=True)

real_entry = None
for e in scanner.scan_devices(False):
    if e.vid == 13058:
        real_entry = e
print("real device:", real_entry)


def s1():
    win._close_session()
    win._pop()
    win.list_page.refresh()
    print("list refreshed")


def s2():
    if real_entry:
        win.open_device(real_entry)


def s3():
    win.grab().save(os.path.join(OUT, "08_real_ttgk_main.png"))
    p = win.pages[-1]
    print("page:", type(p).__name__)
    if hasattr(p, "firm_value"):
        print("firmware shown:", p.firm_value.text())
    if hasattr(p, "vol_row"):
        print("vol slider:", p.vol_row.value(), "->", p.vol_row.value_label.text())
    if hasattr(p, "mic_row"):
        print("mic slider:", p.mic_row.value(), "->", p.mic_row.value_label.text())
    print("saved 08")


def s4():
    win.open_proeq_page(win.session)
    print("proeq opened")


def s5():
    win.grab().save(os.path.join(OUT, "09_real_proeq.png"))
    print("saved 09")
    win.go_back()
    win.open_ezeq_page(win.session)


def s6():
    win.grab().save(os.path.join(OUT, "10_real_ezeq.png"))
    print("saved 10 (ezeq with real device)")
    win._close_session()
    app.quit()


for ms, fn in [(300, s1), (700, s2), (1800, s3), (2200, s4), (2900, s5), (3600, s6)]:
    QTimer.singleShot(ms, fn)

sys.exit(app.exec())
