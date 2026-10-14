# -*- coding: utf-8 -*-
"""EZEQ 配置与随机模板加载（resources/ezeq-config, ezeq-template）

资源查找顺序：用户资源包（%APPDATA%\\YunjiSettings\\assets-override）→ 内置资源。
"""
from __future__ import annotations

import json
import random
from typing import Dict, List, Optional

from ..config import CHIP_CB1200
from ..storage import resolve_asset


class EzeqConfig:
    """EZEQ 断点配置（music / game）"""

    def __init__(self, d: dict):
        self.id = int(d.get("id", 0))
        self.name = d.get("name", "")
        self.points = []
        for pt in d.get("points", []):
            self.points.append({
                "index": int(pt.get("index", 0)),
                "name": pt.get("name", ""),
                "desc": pt.get("desc", ""),
                "freq": int(pt.get("freq", 1000)),
                "q": float(pt.get("q", 0.75)),
            })

    @property
    def freqs(self) -> List[int]:
        return [p["freq"] for p in self.points]

    @property
    def qs(self) -> List[float]:
        return [p["q"] for p in self.points]

    @property
    def names(self) -> List[str]:
        return [p["name"] for p in self.points]


class EzeqTemplates:
    """随机模板集合 {templates:[{gain:[8]}]}"""

    def __init__(self, d: dict):
        self.templates = []
        for t in d.get("templates", []):
            gains = [float(g) for g in t.get("gain", [])]
            if len(gains) == 8:
                self.templates.append(gains)

    def random_gains(self) -> Optional[List[float]]:
        if not self.templates:
            return None
        return list(random.choice(self.templates))


_cache: Dict[str, object] = {}


def _load_json(rel: str) -> dict:
    path = resolve_asset(rel)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_ezeq_config(mode: str) -> EzeqConfig:
    """mode: 'music' / 'game'"""
    key = f"cfg:{mode}"
    if key not in _cache:
        _cache[key] = EzeqConfig(_load_json(f"ezeq-config/{mode}.json"))
    return _cache[key]  # type: ignore[return-value]


def load_ezeq_templates(chip_type: str, mode: str) -> EzeqTemplates:
    """chip_type: 'cb1200' / 'cb5100'，mode: 'music' / 'game'"""
    prefix = "1200-" if chip_type == CHIP_CB1200 else "5100-"
    key = f"tpl:{prefix}{mode}"
    if key not in _cache:
        _cache[key] = EzeqTemplates(
            _load_json(f"ezeq-template/{prefix}{mode}.json")
        )
    return _cache[key]  # type: ignore[return-value]


def load_help_text(mode: str) -> dict:
    """帮助文本：{content, highlights:[{text,color}]}"""
    key = f"help:{mode}"
    if key not in _cache:
        _cache[key] = _load_json(f"ezeq-help/{mode}.json")
    return _cache[key]  # type: ignore[return-value]
