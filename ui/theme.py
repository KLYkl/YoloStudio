"""
theme.py - 统一主题管理模块
============================================

职责:
    - 集中定义所有主题的颜色令牌 (Design Token)
    - 共享形状参数 (圆角、间距、字重)
    - 通过模板统一生成 QSS 样式表
    - ThemeManager 单例管理当前主题状态

架构要点:
    - SHAPE_TOKENS: 暗色/亮色共享的形状参数 (以暗色统计卡片为标准)
    - DARK_TOKENS / LIGHT_TOKENS: 两套颜色令牌
    - generate_qss(): 一套模板 + 两套令牌 = 两套 QSS
    - ThemeManager: 单例, 提供 get_color() / is_dark() / apply()
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMainWindow


# ============================================================
# 形状令牌 (暗/亮共享，以暗色统计卡片为标准)
# ============================================================

SHAPE_TOKENS = {
    # 圆角
    "radius_sm": 2,       # 输入框、按钮、GroupBox
    "radius_md": 4,       # 卡片、面板
    "radius_lg": 4,       # 滑块 groove 等 (不使用大圆角)
    "radius_pill": 8,     # 滑块 handle
    "radius_circle": 13,  # 对话框图标

    # 间距
    "padding_input": "3px 6px",
    "padding_btn": "4px 12px",
    "padding_table_item": "4px 8px",
    "padding_header": "2px 4px",
    "padding_tooltip": "4px 8px",

    # 滚动条
    "scrollbar_width": 8,
    "scrollbar_min_handle": 20,

    # 滑块
    "slider_groove_h": 6,
    "slider_handle_size": 16,
    "slider_handle_margin": -5,

    # 进度条
    "progress_radius": 2,

    # 复选框 / 单选
    "check_size": 16,
    "radio_size": 14,

    # SpinBox 按钮
    "spinbox_btn_width": 16,

    # 字重
    "font_weight_normal": "normal",
    "font_weight_bold": "bold",

    # 边框
    "border_width": 1,
}


# ============================================================
# 暗色主题颜色令牌
# ============================================================

DARK_TOKENS = {
    # --- 背景层级 ---
    "bg_base":       "#1a1a1a",   # 主窗口, Tab pane, 表格
    "bg_surface":    "#1e1e1e",   # 面板, 卡片, 表格交替行
    "bg_elevated":   "#2b2b2b",   # Tab 标签, 输入框, 可折叠 header
    "bg_deep":       "#141414",   # 日志面板, 终端
    "bg_input":      "#2b2b2b",   # 输入框背景

    # --- 前景 / 文字 ---
    "text_primary":  "#e0e0e0",
    "text_secondary": "#a0a0a0",
    "text_dim":      "#555555",
    "text_tab_selected": "#f0e0d0",

    # --- 边框 ---
    "border":        "#2b2b2b",
    "border_hover":  "#3c3c3c",
    "border_input":  "#555555",

    # --- 强调色 ---
    "accent":        "#4a9eff",   # 主强调色 (按钮、选中、链接)
    "accent_hover":  "#6a8eff",

    # --- 语义色 ---
    "success":       "#7ec87e",
    "success_hover": "#6cc8c0",
    "warning":       "#e8a54a",
    "warning_hover": "#d4b84a",
    "danger":        "#e06060",
    "danger_hover":  "#e88090",
    "purple":        "#b07ee8",

    # --- 按钮 ---
    "btn_bg":        "#3c3c3c",
    "btn_hover":     "#4a4a4a",
    "btn_pressed":   "#2b2b2b",
    "btn_disabled_bg": "#2b2b2b",
    "btn_disabled_fg": "#555555",

    # --- 选中 ---
    "selection_bg":  "#3c3c3c",
    "selection_fg":  "#e0e0e0",
    "selection_input": "#4a9eff",

    # --- 日志 ---
    "log_text":      "#a0a0a0",
    "terminal_text": "#7ec87e",

    # --- 预览画布 ---
    "canvas_bg":     "#000000",
    "canvas_text":   "#555555",

    # --- 对话框颜色 (StyledMessageBox 用) ---
    "dialog_bg":     "#1e1e2e",
    "dialog_surface": "#181825",
    "dialog_border": "#313244",
    "dialog_text_primary": "#cdd6f4",
    "dialog_text_secondary": "#a6adc8",
    "dialog_text_muted": "#6c7086",
    "dialog_btn_bg": "#45475a",
    "dialog_btn_hover": "#585b70",
    "dialog_footer_bg": "#11111b",

    # --- 对话框类型强调色 ---
    "dialog_info_accent": "#89b4fa",
    "dialog_info_bg": "rgba(137, 180, 250, 25)",
    "dialog_warning_accent": "#f9e2af",
    "dialog_warning_bg": "rgba(249, 226, 175, 25)",
    "dialog_critical_accent": "#f38ba8",
    "dialog_critical_bg": "rgba(243, 139, 168, 25)",
    "dialog_question_accent": "#89dceb",
    "dialog_question_bg": "rgba(137, 220, 235, 25)",

    # --- 预览标签 (增强 Tab) ---
    "preview_bg":    "#11111b",
    "preview_border": "#313244",
    "preview_text":  "#6c7086",

    # --- 子 Tab 样式 ---
    "sub_tab_text":  "#a0a0a0",
    "sub_tab_hover_bg": "rgba(69, 71, 90, 0.3)",

    # --- 统计卡片颜色映射 ---
    "stats_blue":    "#4a9eff",
    "stats_green":   "#7ec87e",
    "stats_orange":  "#e8a54a",
    "stats_yellow":  "#d4b84a",
    "stats_purple":  "#b07ee8",
    "stats_red":     "#e06060",
}


# ============================================================
# 亮色主题颜色令牌 (Catppuccin Latte 色板)
# ============================================================

LIGHT_TOKENS = {
    # --- 背景层级 ---
    "bg_base":       "#eff1f5",
    "bg_surface":    "#e6e9ef",
    "bg_elevated":   "#ccd0da",
    "bg_deep":       "#e6e9ef",
    "bg_input":      "#eff1f5",

    # --- 前景 / 文字 ---
    "text_primary":  "#4c4f69",
    "text_secondary": "#5c5f77",
    "text_dim":      "#6c6f85",
    "text_tab_selected": "#1e66f5",

    # --- 边框 ---
    "border":        "#bcc0cc",
    "border_hover":  "#acb0be",
    "border_input":  "#bcc0cc",

    # --- 强调色 ---
    "accent":        "#1e66f5",
    "accent_hover":  "#7287fd",

    # --- 语义色 ---
    "success":       "#40a02b",
    "success_hover": "#179299",
    "warning":       "#fe640b",
    "warning_hover": "#df8e1d",
    "danger":        "#d20f39",
    "danger_hover":  "#e64553",
    "purple":        "#8839ef",

    # --- 按钮 ---
    "btn_bg":        "#ccd0da",
    "btn_hover":     "#bcc0cc",
    "btn_pressed":   "#acb0be",
    "btn_disabled_bg": "#dce0e8",
    "btn_disabled_fg": "#9ca0b0",

    # --- 选中 ---
    "selection_bg":  "#ccd0da",
    "selection_fg":  "#4c4f69",
    "selection_input": "#1e66f5",

    # --- 日志 ---
    "log_text":      "#5c5f77",
    "terminal_text": "#40a02b",

    # --- 预览画布 ---
    "canvas_bg":     "#000000",
    "canvas_text":   "#9ca0b0",

    # --- 对话框颜色 ---
    "dialog_bg":     "#eff1f5",
    "dialog_surface": "#e6e9ef",
    "dialog_border": "#bcc0cc",
    "dialog_text_primary": "#4c4f69",
    "dialog_text_secondary": "#5c5f77",
    "dialog_text_muted": "#7c7f93",
    "dialog_btn_bg": "#ccd0da",
    "dialog_btn_hover": "#bcc0cc",
    "dialog_footer_bg": "#dce0e8",

    # --- 对话框类型强调色 ---
    "dialog_info_accent": "#1e66f5",
    "dialog_info_bg": "rgba(30, 102, 245, 20)",
    "dialog_warning_accent": "#df8e1d",
    "dialog_warning_bg": "rgba(223, 142, 29, 20)",
    "dialog_critical_accent": "#d20f39",
    "dialog_critical_bg": "rgba(210, 15, 57, 20)",
    "dialog_question_accent": "#179299",
    "dialog_question_bg": "rgba(23, 146, 153, 20)",

    # --- 预览标签 (增强 Tab) ---
    "preview_bg":    "#e6e9ef",
    "preview_border": "#bcc0cc",
    "preview_text":  "#6c6f85",

    # --- 子 Tab 样式 ---
    "sub_tab_text":  "#6c6f85",
    "sub_tab_hover_bg": "rgba(188, 192, 204, 0.3)",

    # --- 统计卡片颜色映射 ---
    "stats_blue":    "#1e66f5",
    "stats_green":   "#40a02b",
    "stats_orange":  "#fe640b",
    "stats_yellow":  "#df8e1d",
    "stats_purple":  "#8839ef",
    "stats_red":     "#d20f39",
}


# ============================================================
# QSS 生成器
# ============================================================

def _arrow_prefix(is_dark: bool) -> str:
    """返回箭头 SVG 的主题前缀"""
    return "dark" if is_dark else "light"


def generate_qss(tokens: dict, shape: dict, is_dark: bool) -> str:
    """用颜色令牌与形状令牌渲染完整 QSS

    Args:
        tokens: 颜色令牌字典 (DARK_TOKENS 或 LIGHT_TOKENS)
        shape: 形状令牌字典 (SHAPE_TOKENS)
        is_dark: 是否暗色主题 (影响箭头 SVG 路径)

    Returns:
        完整的 QSS 字符串
    """
    t = tokens
    s = shape
    arrow = _arrow_prefix(is_dark)

    return f"""
/* ========== 全局样式 ========== */
QWidget {{
    background-color: transparent;
    color: {t['text_primary']};
}}

/* ========== 主窗口 ========== */
QMainWindow {{
    background-color: {t['bg_base']};
}}

/* ========== Tab控件 ========== */
QTabWidget::pane {{
    border: {s['border_width']}px solid {t['border']};
    border-radius: {s['radius_sm']}px;
    background-color: {t['bg_base']};
    padding: 2px;
}}

QTabBar::tab {{
    background-color: {t['bg_elevated']};
    color: {t['text_primary']};
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: {s['radius_sm']}px;
    border-top-right-radius: {s['radius_sm']}px;
}}

QTabBar::tab:selected {{
    background-color: {t['btn_bg']};
    color: {t['text_tab_selected']};
}}

QTabBar::tab:hover:!selected {{
    background-color: {t['border_hover']};
}}

/* ========== 按钮 ========== */
QPushButton {{
    background-color: {t['btn_bg']};
    color: {t['text_primary']};
    border: {s['border_width']}px solid {t['border_input']};
    border-radius: {s['radius_sm']}px;
    padding: {s['padding_btn']};
    font-weight: {s['font_weight_normal']};
    outline: none;
}}

QPushButton:focus {{
    border: {s['border_width']}px solid {t['accent']};
}}

QPushButton:hover {{
    background-color: {t['btn_hover']};
}}

QPushButton:pressed {{
    background-color: {t['btn_pressed']};
}}

QPushButton:disabled {{
    background-color: {t['btn_disabled_bg']};
    color: {t['btn_disabled_fg']};
}}

/* 主要操作按钮 */
QPushButton[class="primary"] {{
    background-color: {t['accent']};
    color: {t['bg_base']};
}}

QPushButton[class="primary"]:hover {{
    background-color: {t['accent_hover']};
}}

QPushButton[class="primary"]:disabled {{
    background-color: {t['btn_disabled_bg']};
    color: {t['btn_disabled_fg']};
}}

/* 危险操作按钮 */
QPushButton[class="danger"] {{
    background-color: {t['danger']};
    color: {t['bg_base']};
}}

QPushButton[class="danger"]:hover {{
    background-color: {t['danger_hover']};
}}

QPushButton[class="danger"]:disabled {{
    background-color: {t['btn_disabled_bg']};
    color: {t['btn_disabled_fg']};
}}

/* 成功/确认按钮 */
QPushButton[class="success"] {{
    background-color: {t['success']};
    color: {t['bg_base']};
}}

QPushButton[class="success"]:hover {{
    background-color: {t['success_hover']};
}}

QPushButton[class="success"]:disabled {{
    background-color: {t['btn_disabled_bg']};
    color: {t['btn_disabled_fg']};
}}

/* 警告/暂停按钮 */
QPushButton[class="warning"] {{
    background-color: {t['warning']};
    color: {t['bg_base']};
}}

QPushButton[class="warning"]:hover {{
    background-color: {t['warning_hover']};
}}

QPushButton[class="warning"]:disabled {{
    background-color: {t['btn_disabled_bg']};
    color: {t['btn_disabled_fg']};
}}

/* ========== 工具按钮 ========== */
QToolButton {{
    background-color: {t['btn_bg']};
    color: {t['text_primary']};
    border: {s['border_width']}px solid {t['border_input']};
    border-radius: {s['radius_sm']}px;
    padding: 2px;
}}

QToolButton:hover {{
    background-color: {t['btn_hover']};
}}

/* ========== 输入框 ========== */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {t['bg_input']};
    border: {s['border_width']}px solid {t['border_input']};
    border-radius: {s['radius_sm']}px;
    padding: {s['padding_input']};
    color: {t['text_primary']};
    selection-background-color: {t['selection_input']};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: {s['border_width']}px solid {t['accent']};
}}

/* ========== SpinBox ========== */
QSpinBox, QDoubleSpinBox {{
    background-color: {t['bg_input']};
    border: {s['border_width']}px solid {t['border_input']};
    border-radius: {s['radius_sm']}px;
    padding: 2px 4px;
    color: {t['text_primary']};
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border: {s['border_width']}px solid {t['accent']};
}}

QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: {s['spinbox_btn_width']}px;
    border: none;
    border-left: {s['border_width']}px solid {t['btn_bg']};
    border-top-right-radius: {s['radius_sm']}px;
}}

QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: {s['spinbox_btn_width']}px;
    border: none;
    border-left: {s['border_width']}px solid {t['btn_bg']};
    border-bottom-right-radius: {s['radius_sm']}px;
}}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url(resources/arrow_up_{arrow}.svg);
    width: 10px;
    height: 10px;
}}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url(resources/spinbox_down_{arrow}.svg);
    width: 10px;
    height: 10px;
}}

/* ========== 下拉框 ========== */
QComboBox {{
    background-color: {t['bg_input']};
    border: {s['border_width']}px solid {t['border_input']};
    border-radius: {s['radius_sm']}px;
    padding: {s['padding_input']};
    color: {t['text_primary']};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox::down-arrow {{
    image: url(resources/arrow_down_{arrow}.svg);
    width: 12px;
    height: 12px;
}}

QComboBox QAbstractItemView {{
    background-color: {t['bg_elevated']};
    border: {s['border_width']}px solid {t['border_input']};
    selection-background-color: {t['selection_bg']};
}}

/* ========== 滚动条 ========== */
QScrollBar:vertical {{
    background-color: {t['bg_base']};
    width: {s['scrollbar_width']}px;
    border-radius: {s['radius_md']}px;
}}

QScrollBar::handle:vertical {{
    background-color: {t['btn_bg']};
    border-radius: {s['radius_md']}px;
    min-height: {s['scrollbar_min_handle']}px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {t['btn_hover']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background-color: {t['bg_base']};
    height: {s['scrollbar_width']}px;
    border-radius: {s['radius_md']}px;
}}

QScrollBar::handle:horizontal {{
    background-color: {t['btn_bg']};
    border-radius: {s['radius_md']}px;
    min-width: {s['scrollbar_min_handle']}px;
}}

/* ========== 进度条 ========== */
QProgressBar {{
    background-color: {t['bg_elevated']};
    border-radius: {s['progress_radius']}px;
    text-align: center;
    color: {t['text_primary']};
}}

QProgressBar::chunk {{
    background-color: {t['accent']};
    border-radius: {s['progress_radius']}px;
}}

/* ========== 标签 ========== */
QLabel {{
    background-color: transparent;
    color: {t['text_primary']};
}}

/* ========== 分组框 ========== */
QGroupBox {{
    border: {s['border_width']}px solid {t['border_hover']};
    border-radius: {s['radius_sm']}px;
    margin-top: 8px;
    padding-top: 6px;
    font-weight: {s['font_weight_normal']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: {t['accent']};
}}

/* ========== 日志面板 ========== */
QPlainTextEdit#logPanel {{
    background-color: {t['bg_deep']};
    border: {s['border_width']}px solid {t['border']};
    border-radius: {s['radius_sm']}px;
    color: {t['log_text']};
}}

/* ========== 自定义组件 ========== */
QFrame#settingsPanel, QFrame#statusBar {{
    background-color: {t['bg_surface']};
    border: {s['border_width']}px solid {t['border']};
    border-radius: {s['radius_sm']}px;
}}

QFrame#collapsibleHeader {{
    background-color: {t['bg_elevated']};
    border-radius: {s['radius_sm']}px;
}}
QFrame#collapsibleHeader:hover {{
    background-color: {t['btn_bg']};
}}

QFrame#cardWidget {{
    background-color: {t['bg_surface']};
    border: {s['border_width']}px solid {t['border']};
    border-radius: {s['radius_md']}px;
}}

QFrame#statsOverviewCard {{
    background-color: {t['bg_surface']};
    border: {s['border_width']}px solid {t['border']};
    border-radius: {s['radius_md']}px;
}}

QFrame#statsOverviewCard:hover {{
    background-color: {t['bg_base']};
    border: {s['border_width']}px solid {t['border_hover']};
}}

/* 统计卡片 - 指示条颜色 */
QFrame#statsAccentBar {{ border-top-left-radius: {s['radius_md']}px; border-bottom-left-radius: {s['radius_md']}px; }}
QFrame#statsAccentBar[accent="blue"]   {{ background-color: {t['stats_blue']}; }}
QFrame#statsAccentBar[accent="green"]  {{ background-color: {t['stats_green']}; }}
QFrame#statsAccentBar[accent="orange"] {{ background-color: {t['stats_orange']}; }}
QFrame#statsAccentBar[accent="yellow"] {{ background-color: {t['stats_yellow']}; }}
QFrame#statsAccentBar[accent="purple"] {{ background-color: {t['stats_purple']}; }}
QFrame#statsAccentBar[accent="red"]    {{ background-color: {t['stats_red']}; }}

/* 统计卡片 - 标题 */
QLabel#statsCardTitle {{ font-size: 11px; color: {t['text_secondary']}; }}

/* 统计卡片 - 数值 */
QLabel#statsCardValue {{ font-size: 18px; font-weight: 700; }}
QLabel#statsCardValue[accent="blue"]   {{ color: {t['stats_blue']}; }}
QLabel#statsCardValue[accent="green"]  {{ color: {t['stats_green']}; }}
QLabel#statsCardValue[accent="orange"] {{ color: {t['stats_orange']}; }}
QLabel#statsCardValue[accent="yellow"] {{ color: {t['stats_yellow']}; }}
QLabel#statsCardValue[accent="purple"] {{ color: {t['stats_purple']}; }}
QLabel#statsCardValue[accent="red"]    {{ color: {t['stats_red']}; }}

QFrame#statsOverviewSep {{
    color: {t['border']};
}}

QPushButton#logPanelBtn, QToolButton#logPanelBtn {{
    background-color: {t['btn_bg']};
    color: {t['text_primary']};
    border-radius: {s['radius_md']}px;
    padding: 4px 10px;
}}
QPushButton#logPanelBtn:hover, QToolButton#logPanelBtn:hover {{
    background-color: {t['btn_hover']};
}}

/* 主题切换按钮 */
QToolButton#themeToggleBtn {{
    background-color: {t['btn_bg']};
    border: none;
    border-radius: {s['radius_sm']}px;
    padding: 0px;
}}

QToolButton#themeToggleBtn:hover {{
    background-color: {t['btn_hover']};
}}

/* ========== 终端输出 ========== */
QTextEdit#terminalOutput {{
    background-color: {t['bg_deep']};
    color: {t['terminal_text']};
    border: {s['border_width']}px solid {t['border']};
    border-radius: {s['radius_md']}px;
}}

/* ========== 滑块 ========== */
QSlider::groove:horizontal {{
    background-color: {t['btn_bg']};
    height: {s['slider_groove_h']}px;
    border-radius: {s['slider_groove_h'] // 2}px;
}}

QSlider::handle:horizontal {{
    background-color: {t['accent']};
    width: {s['slider_handle_size']}px;
    height: {s['slider_handle_size']}px;
    margin: {s['slider_handle_margin']}px 0;
    border-radius: {s['radius_pill']}px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {t['accent_hover']};
}}

QSlider::sub-page:horizontal {{
    background-color: {t['accent']};
    border-radius: {s['slider_groove_h'] // 2}px;
}}

/* ========== 复选框和单选按钮 ========== */
QCheckBox, QRadioButton {{
    color: {t['text_primary']};
    background: transparent;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    border: 2px solid {t['border_input']};
    background: transparent;
}}

QCheckBox::indicator {{
    width: {s['check_size']}px;
    height: {s['check_size']}px;
    border-radius: {s['radius_md']}px;
}}

QRadioButton::indicator {{
    width: {s['radio_size']}px;
    height: {s['radio_size']}px;
    border-radius: {s['radio_size'] // 2}px;
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    border: 2px solid {t['accent']};
    background: {t['accent']};
}}

/* ========== 工具提示 ========== */
QToolTip {{
    background-color: {t['bg_elevated']};
    color: {t['text_primary']};
    border: {s['border_width']}px solid {t['border_hover']};
    border-radius: {s['radius_md']}px;
    padding: {s['padding_tooltip']};
}}

/* ========== 表格 ========== */
QTableWidget {{
    background-color: {t['bg_base']};
    alternate-background-color: {t['bg_surface']};
    border: {s['border_width']}px solid {t['border']};
    border-radius: {s['radius_sm']}px;
    gridline-color: {t['border']};
    selection-background-color: {t['selection_bg']};
    selection-color: {t['selection_fg']};
}}

QTableWidget::item {{
    padding: {s['padding_table_item']};
}}

QTableWidget::item:selected {{
    background-color: {t['selection_bg']};
}}

QHeaderView::section {{
    background-color: {t['bg_elevated']};
    color: {t['accent']};
    border: none;
    border-right: {s['border_width']}px solid {t['border_hover']};
    border-bottom: {s['border_width']}px solid {t['border_hover']};
    padding: {s['padding_header']};
    font-weight: {s['font_weight_normal']};
}}

QHeaderView::section:hover {{
    background-color: {t['btn_bg']};
}}

/* ========== 分割器 ========== */
QSplitter::handle {{
    background-color: {t['border']};
    border-radius: {s['radius_sm']}px;
}}

QSplitter::handle:hover {{
    background-color: {t['accent']};
}}

/* ========== 预览画布 ========== */
QLabel#previewCanvas {{
    background-color: {t['canvas_bg']};
    border-radius: {s['radius_sm']}px;
    color: {t['canvas_text']};
}}

/* ========== 播放控制栏 ========== */
QFrame#playbackBar {{
    background-color: {t['bg_surface']};
    border: {s['border_width']}px solid {t['border']};
    border-radius: {s['radius_sm']}px;
}}

QSlider#playbackSlider::groove:horizontal {{
    height: 4px;
    background: {t['btn_bg']};
    border-radius: 2px;
}}

QSlider#playbackSlider::handle:horizontal {{
    width: 12px;
    height: 12px;
    margin: -4px 0;
    background: {t['text_primary']};
    border-radius: 6px;
}}

QSlider#playbackSlider::handle:horizontal:hover {{
    background: {t['success']};
}}

QSlider#playbackSlider::sub-page:horizontal {{
    background: {t['accent']};
    border-radius: 2px;
}}

QSlider#playbackSlider:disabled::handle:horizontal {{
    background: {t['text_dim']};
}}

QSlider#playbackSlider:disabled::sub-page:horizontal {{
    background: {t['btn_bg']};
}}

/* ========== 可折叠组件内部 ========== */
QToolButton#collapsibleToggle {{
    background: transparent;
    border: none;
    color: {t['accent']};
    padding: 0;
    min-width: 16px;
}}

QLabel#collapsibleTitle {{
    color: {t['text_primary']};
    font-weight: {s['font_weight_bold']};
}}

/* 高级参数折叠按钮 */
QToolButton#advancedToggle {{
    border: none;
    color: {t['accent']};
    font-weight: {s['font_weight_bold']};
    background: transparent;
}}

QToolButton#advancedToggle:hover {{
    color: {t['accent_hover']};
}}

/* 日志面板标题 */
QLabel#logTitle {{
    color: {t['text_dim']};
    font-weight: {s['font_weight_bold']};
}}

/* ========== 子级 Tab (DataWidget 内部) ========== */
QTabWidget#subTabWidget::pane {{
    border: {s['border_width']}px solid {t['border']};
    border-radius: {s['radius_sm']}px;
    background-color: {t['bg_base']};
    padding: 2px;
}}

QTabWidget#subTabWidget > QTabBar::tab {{
    background-color: transparent;
    color: {t['sub_tab_text']};
    padding: 6px 14px;
    margin-right: 2px;
    border-bottom: 2px solid transparent;
    border-top-left-radius: {s['radius_md']}px;
    border-top-right-radius: {s['radius_md']}px;
}}

QTabWidget#subTabWidget > QTabBar::tab:selected {{
    color: {t['accent']};
    border-bottom: 2px solid {t['accent']};
    background-color: transparent;
}}

QTabWidget#subTabWidget > QTabBar::tab:hover:!selected {{
    color: {t['text_primary']};
    background-color: {t['sub_tab_hover_bg']};
}}

/* 标签样式类 */
QLabel#accentLabel {{
    color: {t['accent']};
    font-weight: {s['font_weight_bold']};
}}
QLabel#mutedLabel {{
    color: {t['text_dim']};
}}
QLabel#successLabel {{
    color: {t['success']};
    font-weight: {s['font_weight_bold']};
}}
QLabel#warningLabel {{
    color: {t['warning']};
}}

/* ========== 预览图片标签 (增强 Tab) ========== */
QLabel#previewImageLabel {{
    background-color: {t['preview_bg']};
    border: {s['border_width']}px solid {t['preview_border']};
    border-radius: {s['radius_md']}px;
    color: {t['preview_text']};
    padding: 8px;
}}
"""


# ============================================================
# ThemeManager 单例
# ============================================================

class ThemeManager:
    """全局主题管理器 (单例模式)

    提供:
        - apply(window): 将当前主题 QSS 应用到窗口
        - toggle(): 切换暗/亮主题
        - get_color(role): 获取当前主题下的颜色值
        - is_dark(): 判断当前是否暗色主题
        - get_dialog_type_colors(type): 获取对话框类型相关颜色

    Example:
        tm = ThemeManager.instance()
        tm.apply(main_window)
        bg = tm.get_color("bg_base")
    """

    _instance: Optional[ThemeManager] = None

    def __init__(self) -> None:
        """请勿直接实例化，使用 ThemeManager.instance()"""
        self._is_dark = True
        self._tokens = DARK_TOKENS
        self._qss_cache: Optional[str] = None

    @classmethod
    def instance(cls) -> ThemeManager:
        """获取全局唯一实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── 查询接口 ──

    def is_dark(self) -> bool:
        """当前是否暗色主题"""
        return self._is_dark

    def get_color(self, role: str) -> str:
        """获取当前主题下指定角色的颜色值

        Args:
            role: 颜色令牌名称, 如 'bg_base', 'accent', 'dialog_border'

        Returns:
            颜色字符串, 如 '#1a1a1a'

        Raises:
            KeyError: 如果 role 不存在
        """
        return self._tokens[role]

    def get_dialog_type_colors(self, msg_type: str) -> dict:
        """获取对话框类型相关的颜色配置

        Args:
            msg_type: 'info' / 'warning' / 'critical' / 'question'

        Returns:
            dict 包含 'accent' 和 'icon_bg' 两个键
        """
        accent_key = f"dialog_{msg_type}_accent"
        bg_key = f"dialog_{msg_type}_bg"
        return {
            "accent": self._tokens.get(accent_key, self._tokens["accent"]),
            "icon_bg": self._tokens.get(bg_key, "transparent"),
        }

    # ── 控制接口 ──

    def set_dark(self, is_dark: bool) -> None:
        """设置主题模式 (不自动应用)"""
        if self._is_dark != is_dark:
            self._is_dark = is_dark
            self._tokens = DARK_TOKENS if is_dark else LIGHT_TOKENS
            self._qss_cache = None  # 清除缓存

    def toggle(self) -> None:
        """切换暗/亮主题 (不自动应用)"""
        self.set_dark(not self._is_dark)

    def apply(self, window: QMainWindow) -> None:
        """将当前主题 QSS 应用到指定主窗口

        Args:
            window: 要应用样式的 QMainWindow 实例
        """
        if self._qss_cache is None:
            self._qss_cache = generate_qss(self._tokens, SHAPE_TOKENS, self._is_dark)
        window.setStyleSheet(self._qss_cache)

    def get_qss(self) -> str:
        """获取当前主题的完整 QSS 字符串"""
        if self._qss_cache is None:
            self._qss_cache = generate_qss(self._tokens, SHAPE_TOKENS, self._is_dark)
        return self._qss_cache

    # ── 辅助方法 ──

    @staticmethod
    def lighten(hex_color: str, factor: float) -> str:
        """提亮颜色

        Args:
            hex_color: 十六进制颜色, 如 '#4a9eff'
            factor: 提亮因子 (0.0~1.0)

        Returns:
            提亮后的十六进制颜色
        """
        from PySide6.QtGui import QColor
        c = QColor(hex_color)
        h, s, l, a = c.getHslF()
        l = min(1.0, l + factor)
        c.setHslF(h, s, l, a)
        return c.name()

    @staticmethod
    def darken(hex_color: str, factor: float) -> str:
        """加深颜色

        Args:
            hex_color: 十六进制颜色, 如 '#4a9eff'
            factor: 加深因子 (0.0~1.0)

        Returns:
            加深后的十六进制颜色
        """
        from PySide6.QtGui import QColor
        c = QColor(hex_color)
        h, s, l, a = c.getHslF()
        l = max(0.0, l - factor)
        c.setHslF(h, s, l, a)
        return c.name()
