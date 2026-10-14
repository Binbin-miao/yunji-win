# -*- coding: utf-8 -*-
"""关于页 与 开源合规声明（替代原版 AboutActivity 与 LaunchActivity 的协议弹窗）"""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import server
from ..config import (
    APP_VERSION,
    DISCLAIMER_TEXT,
    GITHUB_DOCS_URL,
    GITHUB_ISSUES_URL,
    GITHUB_RELEASES_URL,
    GITHUB_URL,
    LICENSE_SUMMARY,
    ORIGINAL_APP_NOTE,
    PROJECT_NAME,
    S,
)
from ..storage import resolve_asset
from .common import Toolbar, load_pixmap
from .dialogs import ContentDialog
from .widgets import card_frame


class AboutPage(QWidget):
    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.toolbar = Toolbar(S["title_about"], self.ctrl.go_back)
        root.addWidget(self.toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        host.setObjectName("listHost")
        v = QVBoxLayout(host)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        # 头部：Logo + 标题 + 版本 + GitHub 检查更新
        card = card_frame()
        c = QVBoxLayout(card)
        c.setContentsMargins(16, 20, 16, 20)
        c.setSpacing(8)

        logo = QLabel()
        pm = load_pixmap("icons/logo_project.png")
        if pm.isNull():
            pm = load_pixmap("icons/app.ico")
        if not pm.isNull():
            logo.setPixmap(pm.scaledToWidth(120, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        c.addWidget(logo)

        title_lab = QLabel(PROJECT_NAME)
        title_lab.setAlignment(Qt.AlignCenter)
        title_lab.setStyleSheet("font-size: 16px; font-weight: bold;")
        c.addWidget(title_lab)

        ver_text = f"{S['about_item_version']}{APP_VERSION} ({ORIGINAL_APP_NOTE})"
        self.ver = QLabel(ver_text)
        self.ver.setAlignment(Qt.AlignCenter)
        self.ver.setStyleSheet("color: #718096; font-size: 12px;")
        c.addWidget(self.ver)

        self.update_btn = QPushButton("检查 GitHub 新版本")
        self.update_btn.clicked.connect(self._check_update)
        c.addWidget(self.update_btn)
        v.addWidget(card)

        # 开源仓库与社区链接
        card_repo = card_frame()
        c_repo = QVBoxLayout(card_repo)
        c_repo.setContentsMargins(12, 8, 12, 8)
        self._link_row(c_repo, "GitHub 开源仓库", GITHUB_URL, "查看源码、提交 PR")
        self._link_row(c_repo, "Releases 发布页", GITHUB_RELEASES_URL, "下载最新打包程序")
        self._link_row(c_repo, "问题反馈 (Issues)", GITHUB_ISSUES_URL, "反馈 Bug、新设备适配")
        self._link_row(c_repo, "硬件协议文档", GITHUB_DOCS_URL, "USB / HID 协议逆向文档")
        v.addWidget(card_repo)

        # 许可与声明
        card_lic = card_frame()
        c_lic = QVBoxLayout(card_lic)
        c_lic.setContentsMargins(12, 8, 12, 8)

        row_lic = QHBoxLayout()
        b_lic = QPushButton("开源许可证 (MIT)")
        b_lic.clicked.connect(self._show_license)
        b_notice = QPushButton("免责与版权声明")
        b_notice.clicked.connect(self._show_notice)
        row_lic.addWidget(b_lic)
        row_lic.addWidget(b_notice)
        c_lic.addLayout(row_lic)
        v.addWidget(card_lic)

        # 底部免责声明条
        tip = QLabel("本项目为独立开源移植工具，与各音频硬件品牌官方无商业关联。")
        tip.setAlignment(Qt.AlignCenter)
        tip.setObjectName("hint")
        tip.setStyleSheet("color: #a0aec0; font-size: 11px;")
        v.addWidget(tip)
        v.addStretch(1)

    def _link_row(self, lay, title: str, url: str, desc: str = ""):
        row = QHBoxLayout()
        text_layout = QVBoxLayout()
        lab = QLabel(title)
        lab.setObjectName("rowLabel")
        lab.setStyleSheet("font-weight: 500;")
        text_layout.addWidget(lab)
        if desc:
            d_lab = QLabel(desc)
            d_lab.setStyleSheet("color: #718096; font-size: 11px;")
            text_layout.addWidget(d_lab)
        row.addLayout(text_layout, 1)

        go = QPushButton("打开")
        go.setFixedWidth(64)
        go.clicked.connect(lambda: webbrowser.open(url))
        row.addWidget(go)
        lay.addLayout(row)

    def _show_license(self):
        html = f"""
        <h3>MIT License</h3>
        <p>Copyright (c) 2026 宾宾</p>
        <p>Permission is hereby granted, free of charge, to any person obtaining a copy
        of this software and associated documentation files (the "Software"), to deal
        in the Software without restriction, including without limitation the rights
        to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
        copies of the Software, and to permit persons to whom the Software is
        furnished to do so, subject to the following conditions:</p>
        <p>The above copyright notice and this permission notice shall be included in all
        copies or substantial portions of the Software.</p>
        <p>THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
        IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
        FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
        AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
        LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
        OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
        SOFTWARE.</p>
        """
        ContentDialog(self, "开源许可证 (MIT)", html).exec()

    def _show_notice(self):
        html = f"""
        <h3>免责与非官方项目声明</h3>
        <div style='line-height:1.7; font-size:13px; color:#2d3748;'>
            <p><b>1. 非官方声明：</b>本项目（YunjiSettings Windows Port）是由爱好者出于学习、逆向工程与跨平台使用便利性而独立开发的第三方工具，<b>与任何音频硬件品牌官方均不存在商业合作、授权或隶属关系</b>。</p>
            <p><b>2. 商标声明：</b>文中及界面提及的品牌名称、型号名称仅用于客观指示硬件兼容性，其商标权与知识产权归其各自权利人所有。</p>
            <p><b>3. 风险声明：</b>本项目基于对原始通信协议的逆向分析与自研协议实现，虽然经过真机测试，但不承担任何因固件版本不匹配、误操作或异常写入导致的设备异常责任。</p>
            <p><b>4. 资源规范：</b>本开源仓库不包含任何原厂专有资源。用户可在 <code>%APPDATA%\\YunjiSettings\\assets-override\\</code> 目录放置个人合法拥有的资源进行本地加载。</p>
        </div>
        """
        ContentDialog(self, "免责与版权声明", html).exec()

    def _check_update(self):
        self.update_btn.setEnabled(False)
        self.update_btn.setText("正在查询 GitHub Releases...")

        def done(info, err):
            self.update_btn.setEnabled(True)
            self.update_btn.setText("检查 GitHub 新版本")
            if err or info is None:
                ContentDialog(self, "检查更新",
                              f"<p>未能获取 GitHub Releases 信息：</p><p style='color:#e53e3e'>{err or '网络超时'}</p>"
                              f"<p>您可直接访问：<a href='{GITHUB_RELEASES_URL}'>{GITHUB_RELEASES_URL}</a></p>").exec()
                return

            latest = (info.tag or "").lstrip("vV") or "-"
            if not latest or not server.version_newer(latest, APP_VERSION):
                ContentDialog(self, "检查更新",
                              f"<p>当前已是最新版本！</p>"
                              f"<p>当前运行版本：v{APP_VERSION}</p>").exec()
                return

            note = (info.notes or "暂无更新日志").replace("\n", "<br/>")
            url = info.html_url or GITHUB_RELEASES_URL
            html = (f"<p>发现新版本：<b>v{latest}</b></p>"
                    f"<p>更新说明：</p><p style='color:#4a5568; background:#edf2f7; padding:8px; border-radius:4px;'>{note}</p>"
                    f"<p><a href='{url}'>点击前往 GitHub 下载最新安装包</a></p>")
            ContentDialog(self, "发现新版本", html).exec()

        server.check_update_async(done)


class PolicyDialog(QDialog):
    """首启声明确认弹窗（非官方开源项目合规告知）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"欢迎使用 {PROJECT_NAME}")
        self.setModal(True)
        self.resize(580, 420)
        self.agreed = False

        lay = QVBoxLayout(self)
        text = QTextBrowser()
        text.setOpenExternalLinks(True)

        msg = f"""
        <div style='font-size:13px; line-height:1.8; color:#2d3748;'>
            <h3 style='margin-top:0;'>欢迎使用 {PROJECT_NAME} (Windows 桌面端)</h3>
            <p>感谢使用本项目。在您开始配置您的音频解码设备前，请阅读以下须知：</p>
            <ul>
                <li><b>独立开源移植：</b>本项目为个人开源项目，代码完全独立重写，旨在方便广大 Windows 用户在 PC 端直接调试小尾巴/耳放的硬件参数与 EQ。</li>
                <li><b>非官方声明：</b>本项目与硬件厂商官方不存在任何商业合作、赞助或技术授权，相关品牌商标归原权利人所有。</li>
                <li><b>免责条款：</b>软件按 MIT 许可证开源，作者已尽力确保协议读写的安全与稳健，但无法对第三方设备固件差异或不可预见的异常承担连带责任。</li>
                <li><b>开源协作：</b>如遇到新硬件未识别、调音参数问题，欢迎前往 <a href='{GITHUB_URL}'>GitHub 仓库</a> 提交 Issue 与 PR。</li>
            </ul>
            <p style='color:#718096;'>点击“同意并继续”即表示您已阅读并理解上述声明，该提示仅在首次启动时出现。</p>
        </div>
        """
        text.setHtml(msg)
        lay.addWidget(text, 1)

        box = QDialogButtonBox()
        agree = box.addButton("同意并继续", QDialogButtonBox.AcceptRole)
        disagree = box.addButton("退出程序", QDialogButtonBox.RejectRole)
        box.accepted.connect(self._on_agree)
        box.rejected.connect(self._on_disagree)
        lay.addWidget(box)

    def _on_agree(self):
        self.agreed = True
        self.accept()

    def _on_disagree(self):
        self.agreed = False
        self.next_action = "quit"
        self.reject()
