# -*- coding: utf-8 -*-
"""最小化 HID 报告描述符解析

只做一件事：从描述符字节流里提取 **Output(0x91)** 项的 (report_id, 字节长度)。

为什么要做：协议里的报告 ID（0x4B）与缓冲长度（64）此前是硬编码，新固件或
新设备若改变报告结构就必须重新手工逆向。改为从描述符动态解析后，适配可以
自动完成；解析失败则回退到硬编码默认值。

HID 短项（short item）编码：
    byte0 = 1010 tt nn
        nn = 后续数据字节数（0/1/2/4；值 3 表示 4 字节）
        tt = 类型 0=Main 1=Global 2=Local 3=Reserved
        高 4 位 = tag

注意：Input/Output/Feature 属于 **Main** 项（tt=0），
       Report ID / Size / Count 属于 **Global** 项（tt=1）。
"""
from __future__ import annotations

import logging
from typing import List, Tuple

log = logging.getLogger(__name__)

# Global 项 tag
_TAG_USAGE_PAGE = 0x0
_TAG_REPORT_SIZE = 0x7
_TAG_REPORT_ID = 0x8
_TAG_REPORT_COUNT = 0x9

# Main 项 tag
_TAG_INPUT = 0x8
_TAG_OUTPUT = 0x9
_TAG_FEATURE = 0xB


def _iter_items(desc: bytes):
    """遍历描述符短项，产出 (type, tag, value)"""
    i = 0
    n = len(desc)
    while i < n:
        b = desc[i]
        if b == 0xFE:                      # long item：跳过
            if i + 2 >= n:
                return
            size = desc[i + 1]
            i += 3 + size
            continue
        size = b & 0x03
        if size == 3:
            size = 4
        typ = (b >> 2) & 0x03
        tag = (b >> 4) & 0x0F
        if i + 1 + size > n:
            return
        value = int.from_bytes(desc[i + 1:i + 1 + size], "little") if size else 0
        i += 1 + size
        yield typ, tag, value


def parse_output_reports(desc: bytes) -> List[Tuple[int, int]]:
    """返回 [(report_id, size_bytes), ...]

    report_id 为 0 表示该报告没有 ID 前缀。
    同时会把该报告占用的字节数按 ReportSize × ReportCount 换算。
    """
    out: List[Tuple[int, int]] = []
    report_id = 0
    report_size_bits = 8
    report_count = 0

    for typ, tag, value in _iter_items(desc):
        if typ == 1:                                   # Global
            if tag == _TAG_REPORT_ID:
                report_id = value
            elif tag == _TAG_REPORT_SIZE:
                report_size_bits = value
            elif tag == _TAG_REPORT_COUNT:
                report_count = value
        elif typ == 0 and tag == _TAG_OUTPUT:          # Main / Output
            bits = report_size_bits * report_count
            size_bytes = (bits + 7) // 8
            if size_bytes > 0:
                out.append((report_id, size_bytes))
    return out


def find_output_report(desc: bytes, report_id: int):
    """按报告 ID 查长度，找不到返回 None"""
    for rid, size in parse_output_reports(desc):
        if rid == report_id:
            return size
    return None
