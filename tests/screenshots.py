# -*- coding: utf-8 -*-
"""渲染各页面截图用于视觉检查"""
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

st = AppState()
st.notice.data.update({"agreed": True, "notice_version": 1})
st.notice.save()

app = QApplication([])
_load_fonts()
app.setStyleSheet(QSS)
win = MainWindow()
win.resize(500, 840)
win.show()
win.use_simulator = True

OUT = os.path.join(ROOT, "screenshots")
os.makedirs(OUT, exist_ok=True)


def shot(name):
    win.grab().save(os.path.join(OUT, f"{name}.png"))
    print("saved", name)


def s1():
    win.list_page.refresh()
    shot("01_device_list")


def s2():
    entry = [e for e in win.simulated_entries() if e.vid == 12230][0]
    win.open_device(entry)


def s3():
    shot("02_xuanrun_main")


def s4():
    win.open_filter_page(win.session)


def s5():
    shot("03_filter")


def s6():
    win.go_back()
    win.go_back()
    entry = [e for e in win.simulated_entries() if e.vid == 13058 and e.chip_type == "cb5100"][0]
    win.open_device(entry)


def s7():
    shot("04_ttgk_main")


def s8():
    win.open_proeq_page(win.session)


def s9():
    shot("05_proeq")


def s10():
    win.go_back()
    win.open_ezeq_page(win.session)


def s11():
    shot("06_ezeq")


def s12():
    win.go_back()
    win.show_about()


def s13():
    shot("07_about")
    win._close_session()
    app.quit()


for ms, fn in [(300, s1), (600, s2), (1200, s3), (1500, s4), (2100, s5),
               (2400, s6), (3000, s7), (3300, s8), (3900, s9), (4200, s10),
               (4800, s11), (5100, s12), (5600, s13)]:
    QTimer.singleShot(ms, fn)

sys.exit(app.exec())
