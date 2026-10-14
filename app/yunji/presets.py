# -*- coding: utf-8 -*-
"""EQ 预设与 UI 状态持久化（文件格式与 Android 版一致，可实现手机/电脑互导）

- EZEQ 预设文件：v{vid}_p{pid}_eq_ez.json
  {"vid":..,"pid":..,"customPresets":[{"presetName","configName","values":[8]}]}
- ProEQ 预设文件：v{vid}_p{pid}_eq.json
  {"vender":..,"product":..,"eqDataList":[{EQData...}]}
- UI 状态文件：v{vid}_p{pid}_ez_ui.json / v{vid}_p{pid}_pro_ui.json
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from .protocol.eqdata import EQData
from .storage import app_data_dir


def _read_json(path) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path, data: dict):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------------- EZEQ ----------------
class EzeqPresetStore:
    def __init__(self, vid: int, pid: int, chip_type: str = "cb5100"):
        self.vid, self.pid = vid, pid
        self.chip_type = chip_type
        d = app_data_dir()
        self.path = d / f"v{vid}_p{pid}_eq_ez.json"
        self.ui_path = d / f"v{vid}_p{pid}_ez_ui.json"
        raw = _read_json(self.path) or {}
        self.presets: List[dict] = list(raw.get("customPresets", []) or [])
        self.ui = _read_json(self.ui_path) or {}

    def save_file(self):
        _write_json(self.path, {
            "vid": self.vid, "pid": self.pid, "customPresets": self.presets,
        })

    def save_ui(self):
        _write_json(self.ui_path, self.ui)

    def add_preset(self, slot: int, preset_name: str, config_name: str, values: List[float]):
        unit = {"presetName": preset_name, "configName": config_name,
                "values": [round(float(v), 1) for v in values]}
        while len(self.presets) < slot:
            self.presets.append({})
        if slot < len(self.presets):
            self.presets[slot] = unit
        else:
            self.presets.append(unit)
        self.save_file()

    def delete(self, slot: int):
        if 0 <= slot < len(self.presets):
            self.presets.pop(slot)
            self.save_file()


# ---------------- ProEQ ----------------
class ProEqPresetStore:
    def __init__(self, vid: int, pid: int):
        self.vid, self.pid = vid, pid
        d = app_data_dir()
        self.path = d / f"v{vid}_p{pid}_eq.json"
        self.ui_path = d / f"v{vid}_p{pid}_pro_ui.json"
        raw = _read_json(self.path) or {}
        self.eq_list: List[dict] = list(raw.get("eqDataList", []) or [])
        self.ui = _read_json(self.ui_path) or {}

    def save_file(self):
        _write_json(self.path, {
            "vender": self.vid, "product": self.pid, "eqDataList": self.eq_list,
        })

    def save_ui(self):
        _write_json(self.ui_path, self.ui)

    def add_preset(self, slot: int, data: EQData):
        d = data.to_json_dict()
        while len(self.eq_list) < slot:
            self.eq_list.append({})
        if slot < len(self.eq_list):
            self.eq_list[slot] = d
        else:
            self.eq_list.append(d)
        self.save_file()

    def delete(self, slot: int):
        if 0 <= slot < len(self.eq_list):
            self.eq_list.pop(slot)
            self.save_file()
