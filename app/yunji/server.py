# -*- coding: utf-8 -*-
"""更新检查：查询本项目 GitHub Releases（替代原版的厂商更新接口）

本软件为第三方非官方项目，不调用任何厂商服务器。
"""
from __future__ import annotations

import json
import threading
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

from .config import APP_VERSION, GITHUB_REPO

API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
TIMEOUT = 8


@dataclass
class ReleaseInfo:
    tag: str = ""
    name: str = ""
    notes: str = ""
    html_url: str = ""


def fetch_latest_release() -> Optional[ReleaseInfo]:
    try:
        req = urllib.request.Request(
            API_LATEST,
            headers={"User-Agent": "YunjiDeskTool", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return ReleaseInfo(
            tag=str(data.get("tag_name", "")),
            name=str(data.get("name", "")),
            notes=str(data.get("body", "") or ""),
            html_url=str(data.get("html_url", "")),
        )
    except Exception:
        return None


def version_newer(latest: str, current: str) -> bool:
    """版本比较：a.b.c 数字段比较（忽略 v 前缀）"""
    def seg(v: str):
        out = []
        for part in str(v).lstrip("vV").replace("-", ".").split("."):
            try:
                out.append(int(part))
            except ValueError:
                out.append(0)
        return out

    a, b = seg(latest), seg(current)
    n = max(len(a), len(b))
    a += [0] * (n - len(a))
    b += [0] * (n - len(b))
    return a > b


def check_update_async(callback: Callable[[Optional[ReleaseInfo], Optional[str]], None]):
    """异步检查更新，callback(info, error)"""
    def worker():
        try:
            info = fetch_latest_release()
            if info is None:
                callback(None, "获取最新版本信息失败")
            else:
                callback(info, None)
        except Exception as e:  # noqa: BLE001
            callback(None, str(e))

    threading.Thread(target=worker, daemon=True).start()
