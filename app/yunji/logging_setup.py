# -*- coding: utf-8 -*-
"""日志系统：写入 %APPDATA%\\YunjiSettings\\logs\\yunji.log

设计目标：用户报「连不上设备」「读数不对」时，能有一份可诊断的日志。
日志文件超过 512KB 自动轮转，保留 3 份备份。
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .storage import app_data_dir

_configured = False

_FMT = logging.Formatter(
    "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def log_dir() -> Path:
    """日志目录（不存在则创建）"""
    d = app_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    return log_dir() / "yunji.log"


def setup_logging(level: int = logging.INFO) -> None:
    """初始化根日志器。重复调用无副作用。"""
    global _configured
    if _configured:
        return

    root = logging.getLogger()
    root.setLevel(level)

    try:
        fh = RotatingFileHandler(log_file(), maxBytes=512 * 1024,
                                 backupCount=3, encoding="utf-8")
        fh.setFormatter(_FMT)
        root.addHandler(fh)
    except Exception:  # noqa: BLE001
        pass  # 日志不可用不应影响程序启动

    # 源码运行时同时输出到控制台，便于开发排查
    if not getattr(sys, "frozen", False):
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(_FMT)
        root.addHandler(sh)

    _configured = True
    logging.getLogger(__name__).info("日志系统就绪 -> %s", log_file())


def install_excepthook() -> None:
    """接管未捕获异常，确保崩溃前留下栈信息"""
    log = logging.getLogger("yunji.crash")

    def _hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("未捕获异常", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook


def install_qt_message_handler() -> None:
    """把 Qt 自身输出重定向到日志（忽略常见的无害告警）"""
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except Exception:  # noqa: BLE001
        return

    log = logging.getLogger("Qt")
    level_map = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def _handler(mode, context, message):
        lvl = level_map.get(mode, logging.INFO)
        if lvl < logging.INFO:
            return
        log.log(lvl, "%s", message)

    qInstallMessageHandler(_handler)
