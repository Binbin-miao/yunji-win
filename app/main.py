# -*- coding: utf-8 -*-
"""云姬（Windows 版）入口"""
import sys
import traceback


def main():
    # 日志最早初始化，确保后续任何失败都留痕
    from yunji.logging_setup import install_excepthook, install_qt_message_handler, setup_logging
    setup_logging()
    install_excepthook()

    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QIcon
    except Exception as e:  # noqa: BLE001
        print("缺少依赖 PySide6，请先安装：pip install PySide6 hidapi pyusb libusb-package")
        print("错误：", e)
        return 1

    from yunji.storage import resolve_asset
    from yunji.ui.fonts import apply_app_font
    from yunji.ui.main_window import MainWindow
    from yunji.ui.theme import QSS

    app = QApplication(sys.argv)
    install_qt_message_handler()
    apply_app_font(app)              # 确保中文字体可用（无头/精简环境亦生效）
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
