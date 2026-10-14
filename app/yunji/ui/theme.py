# -*- coding: utf-8 -*-
"""主题：颜色与全局样式（对照 Android res/values/colors.xml）"""

C_MAIN_BG = "#f5f5f5"
C_SECONDARY_BG = "#eeeeee"
C_CARD = "#ffffff"
C_MAIN_TEXT = "#222222"
C_MAIN_ICON = "#202020"
C_SECONDARY_TEXT = "#777777"
C_HIGHLIGHT_TEXT = "#111111"
C_STATUS_LINKED = "#018786"
C_STATUS_UNLINK = "#333333"
C_ELSE = "#404040"
C_ACCENT = "#008577"
C_MENU_BG = "#f0f0f0"
C_DIVIDER = "#dcdcdc"
C_TOAST_BG = "#cc000000"

FONT_FAMILY = "Microsoft YaHei UI"

QSS = f"""
* {{
    font-family: "{FONT_FAMILY}", "Microsoft YaHei", sans-serif;
    font-size: 14px;
    color: {C_MAIN_TEXT};
}}
QMainWindow, QDialog {{
    background: {C_MAIN_BG};
}}
QWidget#pageRoot {{ background: {C_SECONDARY_BG}; }}
QWidget#toolbar {{
    background: {C_MAIN_BG};
    min-height: 52px; max-height: 52px;
}}
QLabel#toolbarTitle {{
    font-size: 18px; color: {C_MAIN_TEXT};
}}
QScrollArea {{ border: none; background: {C_SECONDARY_BG}; }}
QWidget#listHost {{ background: {C_SECONDARY_BG}; }}

QPushButton {{
    background: {C_CARD};
    border: 1px solid {C_DIVIDER};
    border-radius: 8px;
    padding: 6px 14px;
    color: {C_MAIN_TEXT};
}}
QPushButton:hover {{ background: #f7f7f7; }}
QPushButton:pressed {{ background: #e8e8e8; }}
QPushButton:disabled {{ color: #aaaaaa; background: #f3f3f3; }}
QPushButton#flat {{ border: none; background: transparent; }}
QPushButton#flat:hover {{ background: #e6e6e6; }}

QPushButton#bigAction {{
    background: {C_CARD};
    border-radius: 8px;
    min-height: 38px;
    font-size: 15px;
}}

QSlider::groove:horizontal {{
    height: 6px; background: #d5d5d5; border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {C_ACCENT}; border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 22px; margin: -8px 0; border-radius: 11px;
    background: #ffffff; border: 2px solid {C_ACCENT};
}}
QSlider::handle:horizontal:hover {{ background: #e8fffc; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 40px; height: 22px; border-radius: 11px;
    background: #cccccc; border: none;
}}
QCheckBox::indicator:checked {{
    background: {C_ACCENT};
    image: none;
}}
QCheckBox::indicator:unchecked:disabled {{ background: #e3e3e3; }}
QCheckBox::indicator:checked:disabled {{ background: #9fd0cb; }}
QCheckBox::indicator:hover {{ border: 1px solid #b5b5b5; }}
QCheckBox::indicator:checked:hover {{ border: 1px solid {C_ACCENT}; }}

QLabel#rowLabel {{ font-size: 15px; color: {C_MAIN_TEXT}; }}
QLabel#rowValue {{ font-size: 15px; color: {C_HIGHLIGHT_TEXT}; }}
QLabel#hint {{ color: {C_SECONDARY_TEXT}; font-size: 12px; }}
QLabel#statusLinked {{ color: {C_STATUS_LINKED}; }}
QLabel#statusUnlink {{ color: {C_STATUS_UNLINK}; }}
QLabel#title {{ font-size: 17px; font-weight: 600; color: {C_HIGHLIGHT_TEXT}; }}
QLabel#sectionTitle {{ font-size: 14px; color: {C_SECONDARY_TEXT}; }}

QFrame#card {{
    background: {C_CARD};
    border-radius: 10px;
}}
QFrame#hr {{ background: {C_DIVIDER}; max-height: 1px; min-height: 1px; border: none; }}

QListWidget {{
    background: {C_CARD}; border: none; border-radius: 10px;
    outline: none;
}}
QListWidget::item {{ padding: 4px; }}
QListWidget::item:selected {{ background: #e0f2f0; border-radius: 8px; }}
QListWidget::item:hover {{ background: #f2f2f2; border-radius: 8px; }}

QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {C_CARD}; border: 1px solid {C_DIVIDER};
    border-radius: 6px; padding: 6px 10px;
    selection-background-color: {C_ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {C_ACCENT}; }}

QMenu {{
    background: {C_MENU_BG}; border: 1px solid {C_DIVIDER}; border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 24px 6px 16px; border-radius: 4px; }}
QMenu::item:selected {{ background: #dcdcdc; }}

QScrollBar:vertical {{
    background: transparent; width: 8px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #c4c4c4; border-radius: 4px; min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QToolTip {{
    background: {C_TOAST_BG}; color: white; border: none; padding: 4px 8px;
}}
"""


def toast_style() -> str:
    return (f"background: {C_TOAST_BG}; color: white; padding: 8px 18px;"
            "border-radius: 16px; font-size: 14px;")
