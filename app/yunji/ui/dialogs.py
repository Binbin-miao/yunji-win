# -*- coding: utf-8 -*-
"""对话框集合：数值输入 / 预设选择 / 文本输入 / 帮助 / 公告 / 协议 / 确认"""
from __future__ import annotations

import html
from typing import Callable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..config import S
from .theme import C_SECONDARY_TEXT


class NumberInputDialog(QDialog):
    """数值输入（对照 DialogNumberInput，DOUBLE_LIMITED）"""

    def __init__(self, parent, title: str, minimum: float, maximum: float,
                 initial: float = 0.0, step: float = 0.1, decimals: int = 1):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(320)
        self._result: Optional[float] = None

        lay = QVBoxLayout(self)
        lab = QLabel(f"请输入{title}（{minimum:g} ~ {maximum:g}）")
        lay.addWidget(lab)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setValue(max(minimum, min(maximum, initial)))
        lay.addWidget(self.spin)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText(S["text_confirm"])
        box.button(QDialogButtonBox.Cancel).setText(S["text_cancel"])
        box.accepted.connect(self._ok)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _ok(self):
        self._result = self.spin.value()
        self.accept()

    @staticmethod
    def ask(parent, title: str, minimum: float, maximum: float,
            initial: float = 0.0, decimals: int = 1) -> Optional[float]:
        d = NumberInputDialog(parent, title, minimum, maximum, initial, decimals=decimals)
        if d.exec() == QDialog.Accepted:
            return d._result
        return None


class TextInputDialog(QDialog):
    """文本输入（预设命名）"""

    def __init__(self, parent, title: str, initial: str = "", allow_empty=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(320)
        self._allow_empty = allow_empty
        self._result: Optional[str] = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(title))
        self.edit = QLineEdit(initial)
        self.edit.selectAll()
        lay.addWidget(self.edit)
        self.err = QLabel("")
        self.err.setStyleSheet("color:#c62828;")
        lay.addWidget(self.err)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText(S["text_confirm"])
        box.button(QDialogButtonBox.Cancel).setText(S["text_cancel"])
        box.accepted.connect(self._ok)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _ok(self):
        text = self.edit.text().strip()
        if not text and not self._allow_empty:
            self.err.setText(S["eq_name_cannot_empty"])
            return
        self._result = text
        self.accept()

    @staticmethod
    def ask(parent, title: str, initial: str = "") -> Optional[str]:
        d = TextInputDialog(parent, title, initial)
        if d.exec() == QDialog.Accepted:
            return d._result
        return None


class PresetDialog(QDialog):
    """预设选择对话框（对照 DialogEZEQPresetSelect / DialogProEQPresetSelect）

    mode: "load" / "save"
    槽位最多 eq_max_preset_count 个；左键=加载/保存，右键=删除
    """

    def __init__(self, parent, mode: str, presets: List[dict],
                 max_count: int = 64):
        super().__init__(parent)
        self.setWindowTitle(S["eq_select_title_load"] if mode == "load" else S["eq_select_title_save"])
        self.setModal(True)
        self.resize(560, 480)
        self.mode = mode
        self.presets = presets
        self.action: Optional[tuple] = None  # ("load", idx) / ("save", idx) / ("delete", idx)

        root = QVBoxLayout(self)
        head = QLabel(S["eq_select_title_load"] if mode == "load" else S["eq_select_title_save"])
        head.setObjectName("title")
        root.addWidget(head)

        grid_host = QWidget()
        self.grid = QGridLayout(grid_host)
        self.grid.setSpacing(8)
        root.addWidget(grid_host, 1)
        btns = QHBoxLayout()
        btns.addStretch(1)
        close = QPushButton(S["text_close"])
        close.clicked.connect(self.reject)
        btns.addWidget(close)
        root.addLayout(btns)
        self._rebuild()

    def _rebuild(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for i in range(64):
            name = ""
            if i < len(self.presets):
                name = self.presets[i].get("presetName") or self.presets[i].get("name") or ""
            btn = QPushButton(f"{i + 1}. {name}" if name else f"{i + 1}. {S['text_please_select']}")
            btn.setMinimumHeight(40)
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.clicked.connect(lambda _=False, idx=i: self._on_click(idx))
            btn.customContextMenuRequested.connect(lambda _pos, idx=i: self._on_delete(idx))
            self.grid.addWidget(btn, i // 4, i % 4)

    def _on_click(self, idx: int):
        if self.mode == "load":
            if idx >= len(self.presets):
                return
            self.action = ("load", idx)
            self.accept()
        else:
            self.action = ("save", idx)
            self.accept()

    def _on_delete(self, idx: int):
        if idx >= len(self.presets):
            return
        name = self.presets[idx].get("presetName") or self.presets[idx].get("name") or ""
        ok = QMessageBox.question(
            self, S["text_delete"],
            S["eq_config_delete_confirm"] % (idx + 1, name),
            QMessageBox.Yes | QMessageBox.No)
        if ok == QMessageBox.Yes:
            self.action = ("delete", idx)
            self.accept()

    @staticmethod
    def open_dialog(parent, mode: str, presets: List[dict]):
        d = PresetDialog(parent, mode, presets)
        if d.exec() == QDialog.Accepted:
            return d.action
        return None


class HelpDialog(QDialog):
    """帮助弹窗（对照 EZEQHelper.showHelpDialog：正文 + 红色高亮段落）"""

    def __init__(self, parent, title: str, help_data: dict):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(620, 560)
        lay = QVBoxLayout(self)
        browser = QTextBrowser()
        content = html.escape(str(help_data.get("content", ""))).replace("\n", "<br/>")
        html_doc = f"<div style='font-size:13px;line-height:1.7;'>{content}</div>"
        for h in help_data.get("highlights", []) or []:
            text = html.escape(str(h.get("text", ""))).replace("\n", "<br/>")
            color = h.get("color", "#FF0000")
            html_doc += (f"<div style='margin-top:14px;color:{color};"
                         f"font-size:13px;line-height:1.7;'>{text}</div>")
        browser.setHtml(f"<body style='background:#ffffff;'>{html_doc}</body>")
        lay.addWidget(browser, 1)
        btns = QHBoxLayout()
        btns.addStretch(1)
        b = QPushButton(S["text_close"])
        b.clicked.connect(self.accept)
        btns.addWidget(b)
        lay.addLayout(btns)


class ContentDialog(QDialog):
    """通用内容弹窗（公告 / 协议 / 版本说明），支持 HTML"""

    def __init__(self, parent, title: str, html_content: str, width=620, height=560):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(width, height)
        lay = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(html_content)
        lay.addWidget(browser, 1)
        btns = QHBoxLayout()
        btns.addStretch(1)
        b = QPushButton(S["text_close"])
        b.clicked.connect(self.accept)
        btns.addWidget(b)
        lay.addLayout(btns)


class ConfirmDialog(QDialog):
    """确认对话框（返回 True/False）"""

    def __init__(self, parent, title: str, message: str,
                 ok_text: str = "", cancel_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        lab = QLabel(message)
        lab.setWordWrap(True)
        lay.addWidget(lab)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText(ok_text or S["text_confirm"])
        box.button(QDialogButtonBox.Cancel).setText(cancel_text or S["text_cancel"])
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    @staticmethod
    def ask(parent, title: str, message: str) -> bool:
        d = ConfirmDialog(parent, title, message)
        return d.exec() == QDialog.Accepted


class ImportExportDialog(QDialog):
    """导入/导出 JSON 编辑框（剪贴板方式，对照 Android 剪贴板导入导出）"""

    def __init__(self, parent, title: str, text: str = "", edit_mode: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 380)
        lay = QVBoxLayout(self)
        self.edit = QLineEdit()
        if edit_mode:
            self.browser = None
            lay.addWidget(QLabel(f"{title}（JSON 文本）"))
            import json
            pretty = text
            try:
                pretty = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except Exception:
                pass
            self.text = QTextBrowser()
            self.text.setPlainText(pretty)
            lay.addWidget(self.text, 1)
            btns = QHBoxLayout()
            btns.addStretch(1)
            copy_btn = QPushButton("复制到剪贴板")
            copy_btn.clicked.connect(self._copy)
            btns.addWidget(copy_btn)
            close_btn = QPushButton(S["text_close"])
            close_btn.clicked.connect(self.accept)
            btns.addWidget(close_btn)
            lay.addLayout(btns)
        else:
            lay.addWidget(QLabel("粘贴 JSON 文本后点击导入"))
            self.text = QTextBrowser()
            self.text.setPlaceholderText("{ ... }")
            lay.addWidget(self.text, 1)
            self.err = QLabel("")
            self.err.setStyleSheet("color:#c62828;")
            lay.addWidget(self.err)
            btns = QHBoxLayout()
            btns.addStretch(1)
            paste = QPushButton("从剪贴板粘贴")
            paste.clicked.connect(self._paste)
            btns.addWidget(paste)
            ok = QPushButton(S["text_confirm"])
            ok.clicked.connect(self._ok)
            btns.addWidget(ok)
            cancel = QPushButton(S["text_cancel"])
            cancel.clicked.connect(self.reject)
            btns.addWidget(cancel)
            lay.addLayout(btns)
        self.result_text = ""

    def _copy(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.text.toPlainText())

    def _paste(self):
        from PySide6.QtWidgets import QApplication
        self.text.setPlainText(QApplication.clipboard().text())

    def _ok(self):
        text = self.text.toPlainText().strip()
        if not text:
            self.err.setText(S["toast_invalid_clipboard"])
            return
        self.result_text = text
        self.accept()

    @staticmethod
    def get_text(parent, title: str, text: str) -> None:
        d = ImportExportDialog(parent, title, text, edit_mode=True)
        d.exec()

    @staticmethod
    def ask_import(parent) -> Optional[str]:
        d = ImportExportDialog(parent, "导入 EQ", "", edit_mode=False)
        if d.exec() == QDialog.Accepted:
            return d.result_text
        return None
