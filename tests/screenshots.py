# -*- coding: utf-8 -*-
"""渲染各页面截图，用于视觉检查与 README 配图

覆盖本轮新增功能：目标曲线叠加、悬停读数、分享图导出。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from yunji.storage import get_app_state  # noqa: E402
from yunji.ui.fonts import apply_app_font  # noqa: E402
from yunji.ui.main_window import MainWindow  # noqa: E402
from yunji.ui.theme import QSS  # noqa: E402

st = get_app_state()
st.notice.data.update({"agreed": True, "notice_version": 1})
st.notice.save()

app = QApplication([])
print("字体:", apply_app_font(app) or "(系统回退)")
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
    win.list_page.apply_entries(win.scan())
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
    entry = [e for e in win.simulated_entries()
             if e.vid == 13058 and e.chip_type == "cb5100"][0]
    win.open_device(entry)


def s7():
    shot("04_ttgk_main")


def s8():
    win.open_proeq_page(win.session)


def s9():
    """ProEQ：导入一条曲线 + 叠加目标曲线"""
    p = win.pages[-1]
    p.apply_import_text("""Preamp: -4.0 dB
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
""")
    p._set_target("harman_ie2019")


def s10():
    shot("05_proeq")


def s11():
    """悬停读数：把光标停在 1kHz 附近"""
    p = win.pages[-1]
    p.curve._hover_freq = 1000.0
    p.curve.update()


def s12():
    shot("06_proeq_hover")


def s13():
    """导出分享图"""
    from yunji.protocol import targets as tm
    from yunji.ui.share_card import render_share_card
    p = win.pages[-1]
    pm = render_share_card(p.data, p.entry.display_name, tm.load_target("harman_ie2019"))
    pm.save(os.path.join(OUT, "09_share_card.png"))
    print("saved 09_share_card")


def s14():
    p = win.pages[-1]
    p.curve._hover_freq = None
    win.go_back()
    win.open_ezeq_page(win.session)


def s15():
    shot("07_ezeq")


def s16():
    win.go_back()
    win.show_about()


def s17():
    shot("08_about")
    win._close_session()
    win.scan_service.shutdown()
    app.quit()


for ms, fn in [(300, s1), (600, s2), (1100, s3), (1400, s4), (1900, s5),
               (2200, s6), (2700, s7), (3000, s8), (3300, s9), (3900, s10),
               (4200, s11), (4700, s12), (5000, s13), (5300, s14), (5900, s15),
               (6200, s16), (6700, s17)]:
    QTimer.singleShot(ms, fn)

sys.exit(app.exec())
