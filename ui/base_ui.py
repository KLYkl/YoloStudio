"""
base_ui.py - 基础 UI 组件和样式
============================================

职责:
    - 提供可复用的基础 UI 组件
    - 定义全局样式表常量
    - 统一视觉风格

架构要点:
    - CardWidget: 带圆角和阴影的容器控件
    - DARK_THEME_QSS: 暗色主题样式表
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def set_button_class(btn: QPushButton, cls: str) -> None:
    """Dynamically switch a button's QSS class and refresh its style."""
    btn.setProperty("class", cls)
    btn.style().unpolish(btn)
    btn.style().polish(btn)


# ============================================================
# 全局样式常量
# ============================================================

# 暗色主题样式表
DARK_THEME_QSS = """
/* ========== 全局样式 ========== */
QWidget {
    background-color: transparent;
    color: #cdd6f4;
}

/* ========== 主窗口 ========== */
QMainWindow {
    background-color: #1e1e2e;
}

/* ========== Tab控件 ========== */
QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 8px;
    background-color: #1e1e2e;
    padding: 5px;
}

QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 10px 20px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}

QTabBar::tab:selected {
    background-color: #45475a;
    color: #f5e0dc;
}

QTabBar::tab:hover:!selected {
    background-color: #3b3d4f;
}

/* ========== 按钮 ========== */
QPushButton {
    background-color: #45475a;
    color: #cdd6f4;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #585b70;
}

QPushButton:pressed {
    background-color: #313244;
}

QPushButton:disabled {
    background-color: #313244;
    color: #6c7086;
}

/* 主要操作按钮 (带强调色) */
QPushButton[class="primary"] {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QPushButton[class="primary"]:hover {
    background-color: #b4befe;
}

/* 危险操作按钮 */
QPushButton[class="danger"] {
    background-color: #f38ba8;
    color: #1e1e2e;
}

QPushButton[class="danger"]:hover {
    background-color: #eba0ac;
}

QPushButton[class="danger"]:disabled {
    background-color: #45475a;
    color: #6c7086;
}

/* 成功/确认按钮 (绿色系) */
QPushButton[class="success"] {
    background-color: #a6e3a1;
    color: #1e1e2e;
}

QPushButton[class="success"]:hover {
    background-color: #94e2d5;
}

QPushButton[class="success"]:disabled {
    background-color: #45475a;
    color: #6c7086;
}

/* 警告/暂停按钮 (橙色系) */
QPushButton[class="warning"] {
    background-color: #fab387;
    color: #1e1e2e;
}

QPushButton[class="warning"]:hover {
    background-color: #f9e2af;
}

QPushButton[class="warning"]:disabled {
    background-color: #45475a;
    color: #6c7086;
}

QPushButton[class="primary"]:disabled {
    background-color: #45475a;
    color: #6c7086;
}

/* ========== 工具按钮 ========== */
QToolButton {
    background-color: #45475a;
    color: #cdd6f4;
    border: none;
    border-radius: 6px;
    padding: 4px;
}

QToolButton:hover {
    background-color: #585b70;
}

/* ========== 输入框 ========== */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 10px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #89b4fa;
}

/* ========== SpinBox ========== */
QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 4px 8px;
    color: #cdd6f4;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #89b4fa;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    border: none;
    border-left: 1px solid #45475a;
    border-top-right-radius: 6px;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    border: none;
    border-left: 1px solid #45475a;
    border-bottom-right-radius: 6px;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url(resources/arrow_up_dark.svg);
    width: 10px;
    height: 10px;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url(resources/spinbox_down_dark.svg);
    width: 10px;
    height: 10px;
}

/* ========== 下拉框 ========== */
QComboBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 10px;
    color: #cdd6f4;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox::down-arrow {
    image: url(resources/arrow_down_dark.svg);
    width: 12px;
    height: 12px;
}

QComboBox QAbstractItemView {
    background-color: #313244;
    border: 1px solid #45475a;
    selection-background-color: #45475a;
}

/* ========== 滚动条 ========== */
QScrollBar:vertical {
    background-color: #1e1e2e;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 6px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #585b70;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: #1e1e2e;
    height: 12px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal {
    background-color: #45475a;
    border-radius: 6px;
    min-width: 30px;
}

/* ========== 进度条 ========== */
QProgressBar {
    background-color: #313244;
    border-radius: 6px;
    text-align: center;
    color: #cdd6f4;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 6px;
}

/* ========== 标签 ========== */
QLabel {
    background-color: transparent;
    color: #cdd6f4;
}

/* ========== 分组框 ========== */
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #89b4fa;
}

/* ========== 日志面板 ========== */
QPlainTextEdit#logPanel {
    background-color: #11111b;
    border: 1px solid #313244;
    border-radius: 6px;
    color: #a6adc8;
}

/* ========== 自定义组件 ========== */
QFrame#settingsPanel, QFrame#statusBar {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 8px;
}

QFrame#collapsibleHeader {
    background-color: #313244;
    border-radius: 6px;
}
QFrame#collapsibleHeader:hover {
    background-color: #45475a;
}

QFrame#cardWidget {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 12px;
}

QPushButton#logPanelBtn, QToolButton#logPanelBtn {
    background-color: #45475a;
    color: #cdd6f4;
    border-radius: 4px;
    padding: 4px 10px;
}
QPushButton#logPanelBtn:hover, QToolButton#logPanelBtn:hover {
    background-color: #585b70;
}

/* 主题切换按钮 */
QToolButton#themeToggleBtn {
    background-color: #45475a;
    border: none;
    border-radius: 8px;
    padding: 0px;
    font-size: 16px;
}

QToolButton#themeToggleBtn:hover {
    background-color: #585b70;
}

/* ========== 终端输出 ========== */
QTextEdit#terminalOutput {
    background-color: #11111b;
    color: #a6e3a1;
    border: 1px solid #313244;
    border-radius: 4px;
}

/* ========== 滑块 ========== */
QSlider::groove:horizontal {
    background-color: #45475a;
    height: 6px;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background-color: #89b4fa;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background-color: #b4befe;
}

QSlider::sub-page:horizontal {
    background-color: #89b4fa;
    border-radius: 3px;
}

/* ========== 复选框和单选按钮 ========== */
QCheckBox, QRadioButton {
    color: #cdd6f4;
    background: transparent;
}

QCheckBox::indicator, QRadioButton::indicator {
    border: 2px solid #6c7086;
    background: transparent;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
}

QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border-radius: 7px;
}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    border: 2px solid #89b4fa;
    background: #89b4fa;
}

/* ========== 工具提示 ========== */
QToolTip {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
}

/* ========== 表格 ========== */
QTableWidget {
    background-color: #1e1e2e;
    alternate-background-color: #181825;
    border: 1px solid #313244;
    border-radius: 6px;
    gridline-color: #313244;
    selection-background-color: #45475a;
    selection-color: #cdd6f4;
}

QTableWidget::item {
    padding: 4px 8px;
}

QTableWidget::item:selected {
    background-color: #45475a;
}

QHeaderView::section {
    background-color: #313244;
    color: #89b4fa;
    border: none;
    border-right: 1px solid #45475a;
    border-bottom: 1px solid #45475a;
    padding: 6px 8px;
    font-weight: bold;
}

QHeaderView::section:hover {
    background-color: #45475a;
}

/* ========== 分割器 ========== */
QSplitter::handle {
    background-color: #313244;
    border-radius: 2px;
}

QSplitter::handle:hover {
    background-color: #89b4fa;
}

/* ========== 预览画布 ========== */
QLabel#previewCanvas {
    background-color: #000000;
    border-radius: 8px;
    color: #6c7086;
}

/* ========== 播放控制栏 ========== */
QFrame#playbackBar {
    background-color: #181825;
    border: 1px solid #313244;
    border-radius: 6px;
}

QSlider#playbackSlider::groove:horizontal {
    height: 4px;
    background: #45475a;
    border-radius: 2px;
}

QSlider#playbackSlider::handle:horizontal {
    width: 12px;
    height: 12px;
    margin: -4px 0;
    background: #cdd6f4;
    border-radius: 6px;
}

QSlider#playbackSlider::handle:horizontal:hover {
    background: #a6e3a1;
}

QSlider#playbackSlider::sub-page:horizontal {
    background: #89b4fa;
    border-radius: 2px;
}

QSlider#playbackSlider:disabled::handle:horizontal {
    background: #6c7086;
}

QSlider#playbackSlider:disabled::sub-page:horizontal {
    background: #45475a;
}

/* ========== 可折叠组件内部 ========== */
QToolButton#collapsibleToggle {
    background: transparent;
    border: none;
    color: #89b4fa;
    padding: 0;
    min-width: 16px;
}

QLabel#collapsibleTitle {
    color: #cdd6f4;
    font-weight: bold;
}

/* 高级参数折叠按钮 */
QToolButton#advancedToggle {
    border: none;
    color: #89b4fa;
    font-weight: bold;
    background: transparent;
}

QToolButton#advancedToggle:hover {
    color: #b4befe;
}

/* 日志面板标题 */
QLabel#logTitle {
    color: #6c7086;
    font-weight: bold;
}

/* ========== 子级 Tab (DataWidget 内部) ========== */
QTabWidget#subTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 6px;
    background-color: #1e1e2e;
    padding: 4px;
}

QTabWidget#subTabWidget > QTabBar::tab {
    background-color: transparent;
    color: #a6adc8;
    padding: 6px 14px;
    margin-right: 2px;
    border-bottom: 2px solid transparent;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabWidget#subTabWidget > QTabBar::tab:selected {
    color: #89b4fa;
    border-bottom: 2px solid #89b4fa;
    background-color: transparent;
}

QTabWidget#subTabWidget > QTabBar::tab:hover:!selected {
    color: #cdd6f4;
    background-color: rgba(69, 71, 90, 0.3);
}

/* 标签样式类 */
QLabel#accentLabel {
    color: #89b4fa;
    font-weight: bold;
}
QLabel#mutedLabel {
    color: #6c7086;
}
QLabel#successLabel {
    color: #a6e3a1;
    font-weight: bold;
}
QLabel#warningLabel {
    color: #f9e2af;
}
"""

# 亮色主题样式表
LIGHT_THEME_QSS = """
/* ========== 全局样式 ========== */
QWidget {
    background-color: transparent;
    color: #4c4f69;
}

/* ========== 主窗口 ========== */
QMainWindow {
    background-color: #eff1f5;
}

/* ========== Tab控件 ========== */
QTabWidget::pane {
    border: 1px solid #bcc0cc;
    border-radius: 8px;
    background-color: #eff1f5;
    padding: 5px;
}

QTabBar::tab {
    background-color: #ccd0da;
    color: #4c4f69;
    padding: 10px 20px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}

QTabBar::tab:selected {
    background-color: #dce0e8;
    color: #1e66f5;
}

QTabBar::tab:hover:!selected {
    background-color: #bcc0cc;
}

/* ========== 按钮 ========== */
QPushButton {
    background-color: #ccd0da;
    color: #4c4f69;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #bcc0cc;
}

QPushButton:pressed {
    background-color: #acb0be;
}

QPushButton:disabled {
    background-color: #dce0e8;
    color: #9ca0b0;
}

/* 主要操作按钮 (带强调色) */
QPushButton[class="primary"] {
    background-color: #1e66f5;
    color: #eff1f5;
}

QPushButton[class="primary"]:hover {
    background-color: #7287fd;
}

/* 危险操作按钮 */
QPushButton[class="danger"] {
    background-color: #d20f39;
    color: #eff1f5;
}

QPushButton[class="danger"]:hover {
    background-color: #e64553;
}

QPushButton[class="danger"]:disabled {
    background-color: #dce0e8;
    color: #9ca0b0;
}

/* 成功/确认按钮 (绿色系) */
QPushButton[class="success"] {
    background-color: #40a02b;
    color: #eff1f5;
}

QPushButton[class="success"]:hover {
    background-color: #179299;
}

QPushButton[class="success"]:disabled {
    background-color: #dce0e8;
    color: #9ca0b0;
}

/* 警告/暂停按钮 (橙色系) */
QPushButton[class="warning"] {
    background-color: #fe640b;
    color: #eff1f5;
}

QPushButton[class="warning"]:hover {
    background-color: #df8e1d;
}

QPushButton[class="warning"]:disabled {
    background-color: #dce0e8;
    color: #9ca0b0;
}

QPushButton[class="primary"]:disabled {
    background-color: #dce0e8;
    color: #9ca0b0;
}

/* ========== 工具按钮 ========== */
QToolButton {
    background-color: #ccd0da;
    color: #4c4f69;
    border: none;
    border-radius: 6px;
    padding: 4px;
}

QToolButton:hover {
    background-color: #bcc0cc;
}

/* ========== 输入框 ========== */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #eff1f5;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    padding: 6px 10px;
    color: #4c4f69;
    selection-background-color: #1e66f5;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #1e66f5;
}

/* ========== SpinBox ========== */
QSpinBox, QDoubleSpinBox {
    background-color: #eff1f5;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    padding: 4px 8px;
    color: #4c4f69;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #1e66f5;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 16px;
    border: none;
    border-left: 1px solid #bcc0cc;
    border-top-right-radius: 6px;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 16px;
    border: none;
    border-left: 1px solid #bcc0cc;
    border-bottom-right-radius: 6px;
}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url(resources/arrow_up_light.svg);
    width: 10px;
    height: 10px;
}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url(resources/spinbox_down_light.svg);
    width: 10px;
    height: 10px;
}

/* ========== 下拉框 ========== */
QComboBox {
    background-color: #eff1f5;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    padding: 6px 10px;
    color: #4c4f69;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox::down-arrow {
    image: url(resources/arrow_down_light.svg);
    width: 12px;
    height: 12px;
}

QComboBox QAbstractItemView {
    background-color: #dce0e8;
    border: 1px solid #bcc0cc;
    selection-background-color: #ccd0da;
}

/* ========== 滚动条 ========== */
QScrollBar:vertical {
    background-color: #eff1f5;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background-color: #bcc0cc;
    border-radius: 6px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #acb0be;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: #eff1f5;
    height: 12px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal {
    background-color: #bcc0cc;
    border-radius: 6px;
    min-width: 30px;
}

/* ========== 进度条 ========== */
QProgressBar {
    background-color: #dce0e8;
    border-radius: 6px;
    text-align: center;
    color: #4c4f69;
}

QProgressBar::chunk {
    background-color: #1e66f5;
    border-radius: 6px;
}

/* ========== 标签 ========== */
QLabel {
    background-color: transparent;
    color: #4c4f69;
}

/* ========== 分组框 ========== */
QGroupBox {
    border: 1px solid #bcc0cc;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #1e66f5;
}

/* ========== 日志面板 ========== */
QPlainTextEdit#logPanel {
    background-color: #e6e9ef;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    color: #5c5f77;
}

/* ========== 滑块 ========== */
QSlider::groove:horizontal {
    background-color: #ccd0da;
    height: 6px;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background-color: #1e66f5;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}

QSlider::sub-page:horizontal {
    background-color: #1e66f5;
    border-radius: 3px;
}

/* ========== 复选框和单选按钮 ========== */
QCheckBox, QRadioButton {
    color: #4c4f69;
    background: transparent;
}

QCheckBox::indicator, QRadioButton::indicator {
    border: 2px solid #8c8fa1;
    background: transparent;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
}

QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border-radius: 7px;
}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    border: 2px solid #1e66f5;
    background: #1e66f5;
}

/* ========== 自定义组件 ========== */
QFrame#settingsPanel, QFrame#statusBar {
    background-color: #e6e9ef;
    border: 1px solid #bcc0cc;
    border-radius: 8px;
}

QFrame#collapsibleHeader {
    background-color: #ccd0da;
    border-radius: 6px;
}
QFrame#collapsibleHeader:hover {
    background-color: #bcc0cc;
}

QFrame#cardWidget {
    background-color: #dce0e8;
    border: 1px solid #bcc0cc;
    border-radius: 12px;
}

QPushButton#logPanelBtn, QToolButton#logPanelBtn {
    background-color: #ccd0da;
    color: #4c4f69;
    border-radius: 4px;
    padding: 4px 10px;
}
QPushButton#logPanelBtn:hover, QToolButton#logPanelBtn:hover {
    background-color: #bcc0cc;
}

/* 主题切换按钮 */
QToolButton#themeToggleBtn {
    background-color: #ccd0da;
    border: none;
    border-radius: 8px;
    padding: 0px;
    font-size: 16px;
}

QToolButton#themeToggleBtn:hover {
    background-color: #bcc0cc;
}

/* ========== 终端输出 ========== */
QTextEdit#terminalOutput {
    background-color: #e6e9ef;
    color: #40a02b;
    border: 1px solid #bcc0cc;
    border-radius: 4px;
}

/* ========== 工具提示 ========== */
QToolTip {
    background-color: #e6e9ef;
    color: #4c4f69;
    border: 1px solid #bcc0cc;
    border-radius: 4px;
    padding: 4px 8px;
}

/* ========== 表格 ========== */
QTableWidget {
    background-color: #eff1f5;
    alternate-background-color: #e6e9ef;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    gridline-color: #bcc0cc;
    selection-background-color: #ccd0da;
    selection-color: #4c4f69;
}

QTableWidget::item {
    padding: 4px 8px;
}

QTableWidget::item:selected {
    background-color: #ccd0da;
}

QHeaderView::section {
    background-color: #dce0e8;
    color: #1e66f5;
    border: none;
    border-right: 1px solid #bcc0cc;
    border-bottom: 1px solid #bcc0cc;
    padding: 6px 8px;
    font-weight: bold;
}

QHeaderView::section:hover {
    background-color: #ccd0da;
}

/* ========== 分割器 ========== */
QSplitter::handle {
    background-color: #bcc0cc;
    border-radius: 2px;
}

QSplitter::handle:hover {
    background-color: #1e66f5;
}

/* ========== 预览画布 ========== */
QLabel#previewCanvas {
    background-color: #000000;
    border-radius: 8px;
    color: #9ca0b0;
}

/* ========== 播放控制栏 ========== */
QFrame#playbackBar {
    background-color: #e6e9ef;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
}

QSlider#playbackSlider::groove:horizontal {
    height: 4px;
    background: #ccd0da;
    border-radius: 2px;
}

QSlider#playbackSlider::handle:horizontal {
    width: 12px;
    height: 12px;
    margin: -4px 0;
    background: #4c4f69;
    border-radius: 6px;
}

QSlider#playbackSlider::handle:horizontal:hover {
    background: #40a02b;
}

QSlider#playbackSlider::sub-page:horizontal {
    background: #1e66f5;
    border-radius: 2px;
}

QSlider#playbackSlider:disabled::handle:horizontal {
    background: #9ca0b0;
}

QSlider#playbackSlider:disabled::sub-page:horizontal {
    background: #ccd0da;
}

/* ========== 可折叠组件内部 ========== */
QToolButton#collapsibleToggle {
    background: transparent;
    border: none;
    color: #1e66f5;
    padding: 0;
    min-width: 16px;
}

QLabel#collapsibleTitle {
    color: #4c4f69;
    font-weight: bold;
}

/* 高级参数折叠按钮 */
QToolButton#advancedToggle {
    border: none;
    color: #1e66f5;
    font-weight: bold;
    background: transparent;
}

QToolButton#advancedToggle:hover {
    color: #7287fd;
}

/* 日志面板标题 */
QLabel#logTitle {
    color: #6c6f85;
    font-weight: bold;
}

/* ========== 子级 Tab (DataWidget 内部) ========== */
QTabWidget#subTabWidget::pane {
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    background-color: #eff1f5;
    padding: 4px;
}

QTabWidget#subTabWidget > QTabBar::tab {
    background-color: transparent;
    color: #6c6f85;
    padding: 6px 14px;
    margin-right: 2px;
    border-bottom: 2px solid transparent;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabWidget#subTabWidget > QTabBar::tab:selected {
    color: #1e66f5;
    border-bottom: 2px solid #1e66f5;
    background-color: transparent;
}

QTabWidget#subTabWidget > QTabBar::tab:hover:!selected {
    color: #4c4f69;
    background-color: rgba(188, 192, 204, 0.3);
}

/* 标签样式类 */
QLabel#accentLabel {
    color: #1e66f5;
    font-weight: bold;
}
QLabel#mutedLabel {
    color: #6c6f85;
}
QLabel#successLabel {
    color: #40a02b;
    font-weight: bold;
}
QLabel#warningLabel {
    color: #df8e1d;
}
"""


# ============================================================
# 基础组件
# ============================================================

class CardWidget(QFrame):
    """
    卡片容器控件
    
    带圆角边框和微阴影的容器，用于包裹功能模块。
    
    Attributes:
        内部使用 QVBoxLayout 作为默认布局
    
    Example:
        card = CardWidget()
        card.layout().addWidget(QLabel("卡片标题"))
        card.layout().addWidget(QPushButton("操作按钮"))
    """
    
    def __init__(self, parent: QWidget | None = None) -> None:
        """
        初始化卡片控件
        
        Args:
            parent: 父控件
        """
        super().__init__(parent)
        
        # 设置样式 (颜色由全局 QSS 控制)
        self.setObjectName("cardWidget")
        
        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)
        
        # 设置默认布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)


class PlaceholderWidget(QWidget):
    """
    占位符控件
    
    用于标记尚未实现的模块，显示居中的提示文字。
    """
    
    def __init__(
        self, 
        message: str = "模块开发中...", 
        parent: QWidget | None = None
    ) -> None:
        """
        初始化占位符控件
        
        Args:
            message: 显示的提示信息
            parent: 父控件
        """
        super().__init__(parent)
        
        from PySide6.QtWidgets import QLabel, QVBoxLayout
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        label = QLabel(message)
        label.setObjectName("mutedLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(label)
