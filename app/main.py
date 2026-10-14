# -*- coding: utf-8 -*-
"""云姬（Windows 版）入口"""
import sys
import traceback


def main():
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QIcon
    except Exception as e:  # noqa: BLE001
        print("缺少依赖 PySide6，请先安装：pip install PySide6 hidapi pyusb libusb-package")
        print("错误：", e)
        return 1

    from yunji.storage import resolve_asset
    from yunji.ui.main_window import MainWindow
    from yunji.ui.theme import QSS

    app = QApplication(sys.argv)
    app.setApplicationName("云姬设置")
    app.setOrganizationName("Yunji")
    app.setStyleSheet(QSS)
    icon_path = resolve_asset("icons/ic_launcher.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    win = MainWindow()
    win.show()
    win.run_startup()
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        if not getattr(sys, "frozen", False):
            input("启动失败，按回车退出...")
