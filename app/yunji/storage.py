# -*- coding: utf-8 -*-
"""本地存储：配置目录、设备列表、每设备设置、EQ 预设文件（JSON 格式）

同时提供「用户资源包」覆盖机制：
- 内置资源位于程序自带的 assets 目录；
- 若 %APPDATA%\\YunjiSettings\\assets-override 下存在同名文件，则优先使用（可选，高级用法）。
"""
import json
import logging
import os
import sys
import threading
from pathlib import Path

log = logging.getLogger(__name__)

APP_DIR_NAME = "YunjiSettings"
OVERRIDE_DIR_NAME = "assets-override"


def app_data_dir() -> Path:
    """用户数据目录（Windows: %APPDATA%\\YunjiSettings）"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    p = Path(base) / APP_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def assets_dir() -> Path:
    """内置资源目录（打包后兼容 PyInstaller --add-data）"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


def override_dir() -> Path:
    """用户资源包目录（默认不存在，可由用户自行创建）"""
    return app_data_dir() / OVERRIDE_DIR_NAME


def resolve_asset(rel: str) -> Path:
    """解析资源路径：用户资源包优先，其次内置资源"""
    o = override_dir() / rel
    try:
        if o.exists():
            return o
    except OSError:
        pass
    return assets_dir() / rel


class JsonStore:
    """简单 JSON 文件存储（线程安全）"""

    def __init__(self, path: Path, default):
        self.path = Path(path)
        self.default = default
        self._data = None
        self._lock = threading.RLock()

    @property
    def data(self):
        with self._lock:
            if self._data is None:
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        self._data = json.load(f)
                except Exception:
                    self._data = json.loads(json.dumps(self.default))
            return self._data

    def save(self):
        with self._lock:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
            except Exception:
                logging.getLogger(__name__).exception("写入失败: %s", self.path)
                raise


class AppState:
    """全局状态：设备列表 / 非官方声明确认 / 每设备设置

    注意：设备扫描在后台线程执行，会调用 list_known_devices()，
    因此本类实例需通过 get_app_state() 复用，避免重复建目录与读盘。
    """

    def __init__(self):
        d = app_data_dir()
        self.known_devices = JsonStore(d / "device_list.json", {"data": []})
        self.notice = JsonStore(d / "notice.json", {"agreed": False})
        # 每设备设置: { "<name>_<pid>": {...} }
        self.device_settings = JsonStore(d / "device_settings.json", {})

    # ---- 设备列表 ----
    def list_known_devices(self):
        return list(self.known_devices.data.get("data", []))

    def remember_device(self, name: str, pid: int, vid: int):
        arr = self.known_devices.data.setdefault("data", [])
        for item in arr:
            if item.get("name") == name and int(item.get("id", -1)) == int(pid):
                return
        arr.append({"id": str(pid), "vid": str(vid), "name": name})
        self.known_devices.save()

    def forget_device(self, name: str, pid: int):
        arr = self.known_devices.data.setdefault("data", [])
        self.known_devices.data["data"] = [
            it for it in arr
            if not (it.get("name") == name and str(it.get("id")) == str(pid))
        ]
        self.known_devices.save()

    # ---- 每设备设置 ----
    @staticmethod
    def settings_key(name: str, pid) -> str:
        return f"{name}_{pid}"

    def get_device_settings(self, name: str, pid) -> dict:
        return dict(self.device_settings.data.get(self.settings_key(name, pid), {}))

    def set_device_settings(self, name: str, pid, values: dict):
        self.device_settings.data[self.settings_key(name, pid)] = values
        self.device_settings.save()


_state: "AppState | None" = None
_state_lock = threading.Lock()


def get_app_state() -> AppState:
    """进程内单例：设备扫描线程与主线程共用，避免重复读盘"""
    global _state
    with _state_lock:
        if _state is None:
            _state = AppState()
        return _state
