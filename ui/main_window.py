"""
main_window.py - 主窗口框架
============================================

职责:
    - 应用程序的主 UI 框架
    - 使用 QTabWidget 容纳各功能模块
    - 底部全局日志面板 (可折叠)

架构要点:
    - 继承 QMainWindow
    - GlobalLogPanel 作为可折叠日志控制台
    - 窗口关闭时保存配置
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import AppConfig
from ui.base_ui import PlaceholderWidget
from ui.theme import ThemeManager
from utils.i18n import t, LanguageManager
from utils.logger import get_logger


def _set_windows_titlebar_dark(hwnd: int, dark: bool) -> None:
    """通过 Windows DWM API 设置标题栏暗色/亮色模式"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value), ctypes.sizeof(value),
        )
    except Exception:
        pass


# ============================================================
# 全局日志面板
# ============================================================

class GlobalLogPanel(QWidget):
    """
    全局日志面板 (可折叠, 智能展开)
    
    特性:
        - 窗口模式: 展开时向下扩展窗口高度
        - 最大化模式: 展开时限制高度避免挤压内容
    
    包含:
        - Header: 标题 + 清空按钮 + 切换按钮
        - Body: 日志文本框 (默认隐藏)
    """
    
    LOG_HEIGHT = 150  # 日志面板高度
    
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._main_window = None  # 延迟设置
        self._setup_ui()
    
    def set_main_window(self, window: "MainWindow") -> None:
        """设置主窗口引用以便控制窗口大小"""
        self._main_window = window
    
    def _setup_ui(self) -> None:
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 0)
        layout.setSpacing(5)
        
        # ========== Header 行 ==========
        header = QHBoxLayout()
        
        title = QLabel(t("system_log"))
        title.setObjectName("logTitle")
        
        self.clear_btn = QPushButton(t("clear"))
        self.clear_btn.setObjectName("logPanelBtn")
        self.clear_btn.setFixedSize(60, 28)
        self.clear_btn.clicked.connect(self._on_clear)
        
        self.toggle_btn = QPushButton(t("expand"))
        self.toggle_btn.setObjectName("logPanelBtn")
        self.toggle_btn.setFixedSize(70, 28)
        self.toggle_btn.clicked.connect(self._on_toggle)
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.clear_btn)
        header.addWidget(self.toggle_btn)
        
        layout.addLayout(header)
        
        # ========== Body: 日志文本框 ==========
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText(t("log_placeholder"))
        self.log_text.setMaximumBlockCount(500)
        self.log_text.setObjectName("logPanel")
        self.log_text.setVisible(False)  # 默认隐藏
        
        layout.addWidget(self.log_text)
    
    @Slot(str)
    def append_log(self, message: str) -> None:
        """添加日志消息"""
        self.log_text.appendPlainText(message)
        # 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    @Slot()
    def _on_clear(self) -> None:
        """清空日志"""
        self.log_text.clear()
    
    @Slot()
    def _on_toggle(self) -> None:
        """切换日志显示状态 (使用窗口 15% 高度)"""
        is_visible = self.log_text.isVisible()
        
        if not is_visible:
            self.log_text.setVisible(True)
            self.toggle_btn.setText(t("collapse"))
            self._update_log_height()
        else:
            self.log_text.setVisible(False)
            self.toggle_btn.setText(t("expand"))
    
    def _update_log_height(self) -> None:
        """根据窗口高度动态调整日志面板高度"""
        if self._main_window and self.log_text.isVisible():
            window_height = self._main_window.height()
            log_height = max(80, int(window_height * 0.15))
            self.log_text.setMinimumHeight(log_height)
            self.log_text.setMaximumHeight(log_height)


# ============================================================
# 主窗口
# ============================================================

class MainWindow(QMainWindow):
    """
    YoloStudio 主窗口
    
    包含:
        - 顶部 Tab 区域 (数据准备 / 模型训练 / 预测推理)
        - 底部全局日志面板 (可折叠)
    
    Attributes:
        config: 全局配置管理器
        log_manager: 日志管理器
    """
    
    MIN_WIDTH = 1024
    MIN_HEIGHT = 700
    
    def __init__(self) -> None:
        """初始化主窗口"""
        super().__init__()
        
        # 获取全局实例
        self.config = AppConfig()
        self.log_manager = get_logger()
        
        # 主题状态
        self._is_dark_theme = self.config.get("dark_theme", True)
        # 同步 ThemeManager
        ThemeManager.instance().set_dark(self._is_dark_theme)
        
        # 初始化 UI
        self._setup_window()
        self._setup_ui()
        self._connect_signals()
        
        self.log_manager.info(t("app_started"))
        self.log_manager.info(t("config_path", path=self.config.CONFIG_FILE))
    
    def _setup_window(self) -> None:
        """设置窗口属性"""
        self.setWindowTitle(t("app_title"))
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        
        # 应用主题
        self._apply_theme()
        
        # 设置默认窗口大小并居中
        default_width = 1280
        default_height = 800
        self.resize(default_width, default_height)
        
        # 获取屏幕中心并移动窗口
        screen = self.screen().availableGeometry()
        x = (screen.width() - default_width) // 2
        y = (screen.height() - default_height) // 2
        self.move(x, y)
    
    def _setup_ui(self) -> None:
        """构建 UI 布局"""
        # 创建中央控件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # ========== Tab区域 ==========
        self.tab_widget = QTabWidget()
        
        # 语言切换按钮 (悬浮在 Tab 栏右侧)
        self._lang_btn = QToolButton(self.tab_widget)
        self._lang_btn.setFixedSize(24, 24)
        self._lang_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lang_btn.setText("EN")
        self._lang_btn.setToolTip(t("switch_language"))
        self._lang_btn.setObjectName("themeToggleBtn")
        self._lang_btn.clicked.connect(self._toggle_language)
        self._lang_btn.raise_()

        # 主题切换按钮
        self._theme_btn = QToolButton(self.tab_widget)
        self._theme_btn.setFixedSize(24, 24)
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_theme_button()
        self._theme_btn.clicked.connect(self._toggle_theme)
        self._theme_btn.raise_()
        
        main_layout.addWidget(self.tab_widget, 1)  # Flex 1
        
        # ========== 底部: 全局日志面板 ==========
        self.global_log = GlobalLogPanel()
        self.global_log.set_main_window(self)  # 传递主窗口引用
        main_layout.addWidget(self.global_log, 0)  # Flex 0 (不占用额外空间)
        
        # 添加三个功能模块 Tab (需要先创建 global_log)
        self._add_tabs()
    
    def _add_tabs(self) -> None:
        """添加功能模块 Tab"""
        # Tab 1: 数据准备 (使用 DataWidget)
        from ui.data_widget import DataWidget
        self.data_widget = DataWidget()
        # 连接数据模块日志信号到全局日志面板
        self.data_widget.log_message.connect(self.global_log.append_log)
        self.tab_widget.addTab(self.data_widget, t("tab_data"))
        
        # Tab 2: 模型训练 (使用 TrainWidget)
        from ui.train_widget import TrainWidget
        self.train_widget = TrainWidget()
        # 连接训练模块日志信号到全局日志面板
        self.train_widget.log_message.connect(self.global_log.append_log)
        self.tab_widget.addTab(self.train_widget, t("tab_train"))
        
        # Tab 3: 预测推理 (使用 PredictWidget)
        from ui.predict_widget import PredictWidget
        self.predict_widget = PredictWidget()
        # 连接预测模块日志信号到全局日志面板
        self.predict_widget.log_message.connect(self.global_log.append_log)
        self.tab_widget.addTab(self.predict_widget, t("tab_predict"))
    
    def _connect_signals(self) -> None:
        """连接信号与槽"""
        # 系统日志信号 -> 全局日志面板
        self.log_manager.log_emitted.connect(self.global_log.append_log)
    
    def _apply_theme(self) -> None:
        """应用当前主题"""
        tm = ThemeManager.instance()
        tm.set_dark(self._is_dark_theme)
        tm.apply(self)
        # 同步 Windows 标题栏颜色
        if self.isVisible():
            _set_windows_titlebar_dark(int(self.winId()), self._is_dark_theme)
    
    def _update_theme_button(self) -> None:
        """更新主题按钮图标"""
        self._theme_btn.setObjectName("themeToggleBtn")
        button_font = QFont(self.font())
        button_font.setPointSize(12)
        self._theme_btn.setFont(button_font)
        # 切换主题后需要刷新样式
        self._theme_btn.style().unpolish(self._theme_btn)
        self._theme_btn.style().polish(self._theme_btn)
        if self._is_dark_theme:
            self._theme_btn.setText("☀️")
            self._theme_btn.setToolTip(t("switch_to_light"))
        else:
            self._theme_btn.setText("🌙")
            self._theme_btn.setToolTip(t("switch_to_dark"))
    
    @Slot()
    def _toggle_theme(self) -> None:
        """切换主题"""
        self._is_dark_theme = not self._is_dark_theme
        self._apply_theme()
        self._update_theme_button()
        
        # 保存主题偏好
        self.config.set("dark_theme", self._is_dark_theme)
        self.config.save()
        
        theme_key = "switched_to_dark" if self._is_dark_theme else "switched_to_light"
        self.log_manager.info(t(theme_key))
    
    def resizeEvent(self, event) -> None:
        """窗口大小改变时更新主题按钮位置和日志面板高度"""
        super().resizeEvent(event)
        self._update_theme_button_position()
        if hasattr(self, 'global_log'):
            self.global_log._update_log_height()
    
    def showEvent(self, event) -> None:
        """窗口显示时更新主题按钮位置和标题栏颜色"""
        super().showEvent(event)
        self._update_theme_button_position()
        _set_windows_titlebar_dark(int(self.winId()), self._is_dark_theme)
    
    def _update_theme_button_position(self) -> None:
        """更新主题按钮和语言按钮位置到 Tab 栏右侧"""
        if hasattr(self, '_theme_btn') and hasattr(self, 'tab_widget'):
            btn_y = 1
            theme_x = self.tab_widget.width() - self._theme_btn.width() - 5
            self._theme_btn.move(theme_x, btn_y)

            if hasattr(self, '_lang_btn'):
                lang_x = theme_x - self._lang_btn.width() - 4
                self._lang_btn.move(lang_x, btn_y)
    
    @Slot()
    def _toggle_language(self) -> None:
        """切换语言 (需要重启生效)"""
        mgr = LanguageManager.instance()
        next_lang = mgr.get_next_language()
        mgr.switch(next_lang)

        from ui.styled_message_box import StyledMessageBox
        StyledMessageBox.information(
            self,
            t("switch_language"),
            t("language_restart_hint"),
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        窗口关闭事件
        
        保存窗口大小到配置文件
        
        Args:
            event: 关闭事件
        """
        # 保存窗口大小
        size = self.size()
        self.config.set("window_width", size.width())
        self.config.set("window_height", size.height())
        self.config.save()
        
        self.log_manager.info(t("app_closing"))
        
        # 显式关闭子模块，触发各自的 closeEvent 清理
        self.predict_widget.close()
        self.data_widget.close()
        self.train_widget.close()
        
        event.accept()
