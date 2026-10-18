# -*- coding: utf-8 -*-
"""云姬桌面工具（非官方 Windows 版）- 全局常量与配置

本项目为第三方非官方工具，不含任何厂商版权资源，仅用于设备互操作性目的。
"""
APP_NAME = "云姬"
APP_NAME_FULL = "云姬设置（非官方 Windows 版）"
APP_VERSION = "1.7.6.2"
VERSION_NOTE = "移植自官方安卓版 v1.7.6"
WINDOW_TITLE = f"云姬设置 v{APP_VERSION}（非官方 Windows 版）"

# ---- 项目链接 ----
GITHUB_REPO = "Binbin-miao/yunji-win"
GITHUB_URL = f"https://github.com/{GITHUB_REPO}"
ISSUES_URL = f"{GITHUB_URL}/issues"
RELEASES_URL = f"{GITHUB_URL}/releases"

# ---- 关于页 / 声明 用常量 ----
PROJECT_NAME = "YunjiSettings Windows Port"
ORIGINAL_APP_NOTE = "移植自官方安卓版 v1.7.5"
GITHUB_ISSUES_URL = ISSUES_URL
GITHUB_RELEASES_URL = RELEASES_URL
GITHUB_DOCS_URL = f"{GITHUB_URL}/blob/main/docs/%E5%8D%8F%E8%AE%AE%E5%8F%82%E8%80%83.md"
LICENSE_SUMMARY = "MIT License · Copyright (c) 2026 宾宾"
DISCLAIMER_TEXT = (
    "本项目为独立开源移植工具，与各音频硬件品牌官方无商业关联；"
    "相关品牌与型号名称仅用于指示硬件兼容性，其商标权归原权利人所有。"
)

# ---- 厂商 ID（= USB VID，事实性设备标识）----
VENDER_ID_XUAN_RUN = 12230     # 旋润
VENDER_ID_TTGK = 13058         # TTGK

VENDER_NAMES = {
    VENDER_ID_XUAN_RUN: "旋润",
    VENDER_ID_TTGK: "TTGK",
}

# ---- 芯片平台 ----
CHIP_CB1200 = "cb1200"
CHIP_CB5100 = "cb5100"

# ---- EQ / 音量参数 ----
EQ_MAX_PRESET_COUNT = 64
GET_INFO_MAX_RETRY_TIME = 3
TTGK_MIN_EQ_GAIN = -12
TTGK_MAX_EQ_GAIN = 12
TTGK_EQ_GAIN_RESOLUTION = 10   # 0.1 dB / 步
TTGK_MIN_EQ_OFFSET = -8
TTGK_MAX_EQ_OFFSET = 4
TTGK_BALANCE_RANGE = 40
TTGK_MIC_VOL_RANGE = 60

# TTGK DAC 音量范围（按芯片）
TTGK_DAC_VOL_OFFSET = {CHIP_CB1200: 0, CHIP_CB5100: 60}
TTGK_DAC_VOL_RESOLUTION = {CHIP_CB1200: 1, CHIP_CB5100: 1}
TTGK_MAX_DAC_VOL = {CHIP_CB1200: 4, CHIP_CB5100: 0}
TTGK_MIN_DAC_VOL = {CHIP_CB1200: -8, CHIP_CB5100: -60}

# ---- 旋润音量码表：滑块 0..60 -> 设备码 ----
XUANRUN_VOL_TABLE = [
    0xFF, 0xC8, 0xB4, 0xAA, 0xA0, 0x96, 0x8C, 0x82,
    122, 116, 110, 106, 102, 98, 94, 90,
    88, 86, 84, 82, 80, 78, 76, 74, 72, 70, 68, 66, 64, 62,
    60, 58, 56, 54, 52, 50, 48, 46, 44, 42, 40, 38, 36, 34, 32,
    30, 28, 26, 24, 22, 20, 18, 16, 14, 12, 10, 8, 6, 4, 2, 0,
]  # 61 项

# 旋润声道平衡码表：滑块 0..36，中位 18
XUANRUN_BALANCE_VALUE_L = [max(0, i - 18) for i in range(37)]
XUANRUN_BALANCE_VALUE_R = [max(0, 18 - i) for i in range(37)]

# ---- 滤波器模式（共用 5 档）----
FILTER_MODE_NAMES = [
    "低延迟陡降",
    "相位补偿陡降",
    "低延迟缓降",
    "相位补偿缓降",
    "无过采样",
]

# ---- ProEQ 默认频点 ----
PROEQ_DEFAULT_FREQ = [60, 120, 250, 500, 1000, 2000, 4000, 8000]
PROEQ_DEFAULT_Q = [0.75] * 8
PROEQ_DEFAULT_TYPE = 2         # peaking

# ---- EQ 滤波器类型码（写入设备包的 type 字节）----
# 逆向确认：官方 Android 版只会发送 2（peaking），typeList 是死数据。
# 下面 shelf 的编码值是**推测**，未经真机验证，如需实验可在本处调整。
EQ_TYPE_PEAKING = 2
EQ_TYPE_LOW_SHELF = 1
EQ_TYPE_HIGH_SHELF = 3

# ---- 实验性功能开关（默认关闭）----
# 开启后允许在 ProEQ 中选择低架/高架滤波器。风险：设备是否支持未知，
# biquad 参数若不匹配可能导致滤波器不稳定（刺耳噪音）。
EXPERIMENTAL_SHELF_ENABLED = False

# ---- EQ 计算采样率 ----
EQ_DEVICE_SAMPLE_RATE = 96000.0
EQ_DISPLAY_SAMPLE_RATE = 48000.0


# ---- UI 文案 ----
S = {
    "title_device_list": "我的设备",
    "title_about": "关于",
    "device_status_connected": "已连接",
    "device_status_unconnected": "未连接",
    "device_empty_list": "请插入云姬设备\n插入后会自动识别\n（本工具为非官方第三方软件，支持旋润 / TTGK 品牌设备）",
    "toast_unlink": "设备未连接",
    "toast_linking": "正在连接...",
    "toast_empty_device": "获取设备信息失败",
    "toast_no_interface": "未找到设备通信界面",
    "toast_no_end_point": "未找到设备端口",
    "toast_eq_upload_failed": "上传EQ失败",
    "toast_eq_max_preset_reached": "达到最大预设数量，无法创建新预设",
    "toast_copied": "已复制到剪贴板",
    "toast_invalid_clipboard": "未读取到有效内容",
    "toast_invalid_data": "无效数据",
    "toast_saved": "已保存",
    "toast_press_again_to_quit": "再次点击返回退出",
    "main_setting_vol": "硬件音量:",
    "main_setting_vol_gain": "音量增益:",
    "main_setting_balance": "音量平衡:",
    "main_setting_elelevel": "增益:",
    "main_setting_led": "LED:",
    "main_setting_depop": "防插拔噪音:",
    "main_setting_mic_vol": "麦克风音量：",
    "main_setting_firmware": "固件版本:",
    "main_setting_more": "高级",
    "main_setting_filter": "滤波器",
    "main_setting_filter_mode": "滤波器模式",
    "main_setting_eq_ez": "简易均衡器",
    "main_setting_eq_pro": "参数均衡器",
    "main_setting_sw_on": "开",
    "main_setting_sw_off": "关",
    "main_setting_sw_high": "高",
    "main_setting_sw_low": "低",
    "main_setting_vol_alert": "若增益过大产生爆音，请调整至0或更低",
    "eq_help": "帮助",
    "eq_ez_game": "游戏模式",
    "eq_ez_music": "音乐模式",
    "eq_ez_random": "随机模板",
    "eq_ez_reset": "重置数值",
    "eq_reset": "恢复出厂设置",
    "eq_save_preset": "保存预设",
    "eq_load_preset": "加载预设",
    "eq_save_to_file": "保存至文件",
    "eq_load_from_file": "从文件加载",
    "eq_new_preset_name": "新预设",
    "eq_preset_name": "预设名称",
    "eq_name_cannot_empty": "预设名称不能为空",
    "eq_config_load_confirm": "确认加载预设 %d: %s?",
    "eq_config_delete_confirm": "确认删除预设 %d: %s",
    "eq_select_title_load": "加载位置",
    "eq_select_title_save": "保存位置",
    "eq_select_notice_selecting": "选择中",
    "eq_select_notice_using": "使用中",
    "eq_select_title": "请选择%s",
    "eq_offset_label": "整体音量偏移",
    "eq_import_alert": "导入操作将会覆盖当前设置，是否继续？",
    "text_confirm": "确认",
    "text_cancel": "取消",
    "text_close": "关闭",
    "text_save": "保存",
    "text_load": "加载",
    "text_delete": "删除",
    "text_reset": "重置",
    "text_back": "返回",
    "text_exit": "退出",
    "text_please_select": "请选择",
    "text_preset": "预设",
    "number_frequncy_value": "调整频率",
    "number_gain_value": "调整增益",
    "number_q_value": "调整q值",
    "title_edit": "编辑",
    # ---- 关于页 ----
    "about_item_version": "版本：",
    "about_version_note": "（移植自官方安卓版 v1.7.5）",
    "about_github": "GitHub 仓库",
    "about_issues": "问题反馈",
    "about_license": "开源许可",
    "about_notice": "非官方声明",
    "about_check_update": "检查更新",
    "about_copyright": "第三方非官方项目 · 与云姬品牌方无任何关联 · 以 MIT 许可证开源",
    "update_message_checking_new_version": "正在检查版本...",
    "update_message_already_up_to_date": "已经是最新版本",
    "update_message_failed_get_new_version_info": "获取最新版本信息失败（请检查网络）",
    "update_new_version_title": "发现新版本",
    # ---- 非官方声明 ----
    "notice_title": "非官方项目声明",
    "notice_body": (
        "本软件是第三方非官方工具，与「云姬」品牌方无任何关联。\n\n"
        "· 本软件仅通过 USB 与本机设备通信，用于设备设置与均衡器调节，属于互操作性用途；\n"
        "· 本软件不包含任何厂商版权资源，也不收集任何个人数据；\n"
        "· 所有设置仅保存在本机（%APPDATA%\\YunjiSettings）；\n"
        "· 使用本软件产生的风险由使用者自行承担；\n"
        "· 「云姬」及相关商标、产品名称归其权利人所有。\n\n"
        "继续使用即表示您已阅读并知悉以上内容。"
    ),
    "notice_agree": "同意并继续",
    "notice_exit": "退出",
    "load_failed_prefix": "加载失败：",
    # ---- 旁通 / A-B 对比 ----
    "bypass_on": "已旁通",
    "bypass_off": "已恢复",
    "bypass_hint": "旁通：临时把 EQ 置为平直以便对比原声（按住空格键临时旁通）",
    "bypass_button": "旁通",
    # ---- 增益补偿 ----
    "preamp_button": "增益补偿",
    "preamp_none_needed": "当前曲线无正增益，无需补偿",
    "preamp_applied": "已设置整体偏移为 %d dB（峰值 %+.1f dB）",
    "preamp_clamped": (
        "峰值增益 %+.1f dB，但整体偏移下限为 %d dB，"
        "无法完全补偿。建议降低增益最大的频段以避免削波。"
    ),
    "preamp_title": "增益补偿",
    # ---- 导入 ----
    "import_title": "导入 EQ",
    "import_hint": (
        "支持以下格式（可直接从 AutoEQ / squig.link 复制）：\n"
        "· Equalizer APO：Filter 1: ON PK Fc 105 Hz Gain -3.2 dB Q 0.70\n"
        "· GraphicEQ：GraphicEQ: 20 -3.5; 25 -3.2; 31 -2.9; ...\n"
        "· Wavelet：{\"graphicEQ\": [[20,-3.5],[25,-3.2], ...]}\n"
        "· 本工具格式：{\"bands\":[{\"freq\":60,\"q\":0.75,\"gain\":0,\"type\":2}]}"
    ),
    "import_ok": "导入成功（%d 段，拟合误差 %.2f dB）",
    "import_ok_exact": "导入成功（%d 段）",
    "import_no_bands": "未识别到任何滤波器参数",
    "import_failed": "导入失败：%s",
    "import_fit_note": "源曲线为 %d 段，已自动拟合为设备的 8 段",
    # ---- 导出分享 ----
    "export_image_title": "导出分享图",
    "export_image_saved": "分享图已保存：%s",
    "export_image_failed": "保存失败：%s",
    # ---- 目标曲线 ----
    "target_none": "不显示",
    "target_label": "目标曲线",
    # ---- 滤波器类型 ----
    "eq_type_peak": "峰值",
    "eq_type_low_shelf": "低架",
    "eq_type_high_shelf": "高架",
    "shelf_warning_title": "实验性功能确认",
    "shelf_warning_body": (
        "<p><b>低架 / 高架滤波器尚未经过真机验证。</b></p>"
        "<p>官方 App 只使用过「峰值」类型，硬件是否识别其他类型未知。"
        "若设备不支持，屏幕上显示的曲线与实际听到的效果会不一致；"
        "极端参数下还可能出现不稳定的声音。</p>"
        "<p>建议先用一段小幅度的低架滤波试听确认。确定要继续吗？</p>"
    ),
    # ---- 扫描失败提示 ----
    "scan_failed_prefix": "设备扫描异常：",
}
