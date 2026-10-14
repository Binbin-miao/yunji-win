# -*- coding: utf-8 -*-
"""中文字体引导

背景：`QFontDatabase.families()` 在无头（offscreen）环境下可能返回空列表，
此时 Qt 无法解析任何字体，中文会渲染成豆腐块（□□□）。
真实桌面环境一般不会遇到，但导出分享图、截图、CI 冒烟测试都会受影响。

本模块提供 ensure_cjk_font()：
1. 先在系统字体族里找常见中文字体；
2. 找不到则直接从字体文件加载（Windows 的 msyh.ttc / simhei.ttf 等）；
3. 都没有则返回空串，交给 Qt 默认字体与系统回退处理。
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional

log = logging.getLogger(__name__)

#: 常见中文字体族名（按优先级）
CANDIDATES = [
    "Microsoft YaHei UI", "Microsoft YaHei",
    "PingFang SC", "Hiragino Sans GB",
    "Noto Sans CJK SC", "Source Han Sans SC", "Source Han Sans CN",
    "SimHei", "SimSun", "Microsoft JhengHei",
]

#: 字体文件兜底路径（按平台）
_FONT_FILES = {
    "win32": [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ],
    "darwin": [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ],
    "linux": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ],
}

_resolved: Optional[str] = None


def _font_files() -> list:
    return _FONT_FILES.get(sys.platform, [])


def ensure_cjk_font() -> str:
    """返回可渲染中文的字体族名；无可用字体时返回空串"""
    global _resolved
    if _resolved is not None:
        return _resolved

    try:
        from PySide6.QtGui import QFontDatabase
    except Exception:  # noqa: BLE001
        _resolved = ""
        return _resolved

    families = set(QFontDatabase.families())
    for name in CANDIDATES:
        if name in families:
            _resolved = name
            log.debug("使用系统字体: %s", name)
            return _resolved

    for path in _font_files():
        if not os.path.exists(path):
            continue
        try:
            fid = QFontDatabase.addApplicationFont(path)
            if fid < 0:
                continue
            names = QFontDatabase.applicationFontFamilies(fid)
            if names:
                _resolved = names[0]
                log.info("已从字体文件加载: %s -> %s", path, _resolved)
                return _resolved
        except Exception:  # noqa: BLE001
            log.debug("字体加载失败: %s", path, exc_info=True)

    log.warning("未找到可用的中文字体，中文可能显示为方块")
    _resolved = ""
    return _resolved


def reset_cache() -> None:
    """测试用：清空缓存"""
    global _resolved
    _resolved = None


def apply_app_font(app) -> str:
    """把解析出的字体设为应用默认字体（整个 UI 受益）"""
    from PySide6.QtGui import QFont

    family = ensure_cjk_font()
    if family:
        f = QFont(app.font())
        f.setFamily(family)
        app.setFont(f)
    return family
