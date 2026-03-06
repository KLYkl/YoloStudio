"""
styled_message_box.py - 自定义样式消息弹窗
============================================

职责:
    - 替代原生 QMessageBox，提供与项目 Catppuccin 主题一致的弹窗样式
    - 参考微软 Fluent Design / Windows 11 对话框风格
    - 自动居中到应用主窗口
    - 提供 information / warning / critical 三种静态方法

架构要点:
    - 继承 QDialog，完全自绘界面
    - 通过查找 QMainWindow 实例确保弹窗居中到主窗口
    - 支持 detailedText 展开/收起
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QBrush, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class StyledMessageBox(QDialog):
    """自定义样式消息弹窗 — 微软 Fluent Design 风格 + Catppuccin 配色"""

    # 消息类型常量
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

    # 各类型对应的配置
    _TYPE_CONFIG = {
        "info": {
            "icon": "✓",
            "accent_dark": "#89b4fa",
            "accent_light": "#1e66f5",
            "bg_dark": "rgba(137, 180, 250, 25)",
            "bg_light": "rgba(30, 102, 245, 20)",
        },
        "warning": {
            "icon": "!",
            "accent_dark": "#f9e2af",
            "accent_light": "#df8e1d",
            "bg_dark": "rgba(249, 226, 175, 25)",
            "bg_light": "rgba(223, 142, 29, 20)",
        },
        "critical": {
            "icon": "✕",
            "accent_dark": "#f38ba8",
            "accent_light": "#d20f39",
            "bg_dark": "rgba(243, 139, 168, 25)",
            "bg_light": "rgba(210, 15, 57, 20)",
        },
    }

    def __init__(
        self,
        parent: QWidget | None,
        msg_type: str,
        title: str,
        text: str,
        detailed_text: str = "",
    ) -> None:
        # 查找主窗口作为 parent，确保居中
        main_window = self._find_main_window(parent)
        super().__init__(main_window)

        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedWidth(340)

        config = self._TYPE_CONFIG.get(msg_type, self._TYPE_CONFIG["info"])
        is_dark = self._is_dark_theme()
        accent = config["accent_dark"] if is_dark else config["accent_light"]
        icon_bg = config["bg_dark"] if is_dark else config["bg_light"]

        # 主题色
        if is_dark:
            bg = "#1e1e2e"
            surface = "#181825"
            border = "#313244"
            text_primary = "#cdd6f4"
            text_secondary = "#a6adc8"
            text_muted = "#6c7086"
            btn_bg = "#45475a"
            btn_hover = "#585b70"
            footer_bg = "#11111b"
        else:
            bg = "#eff1f5"
            surface = "#e6e9ef"
            border = "#bcc0cc"
            text_primary = "#4c4f69"
            text_secondary = "#5c5f77"
            text_muted = "#7c7f93"
            btn_bg = "#ccd0da"
            btn_hover = "#bcc0cc"
            footer_bg = "#dce0e8"

        # ==================== 主布局 ====================
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # 主卡片 (使用自绘圆角)
        self._bg_color = bg
        self._border_color = border
        self._radius = 10

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---------- 内容区域 ----------
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(24, 20, 24, 16)
        content_layout.setSpacing(0)

        # 图标 + 标题 同一行
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 10)
        header_row.setSpacing(10)

        icon_label = QLabel(config["icon"])
        icon_label.setFixedSize(26, 26)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(f"""
            background-color: {icon_bg};
            color: {accent};
            border: 1.5px solid {accent};
            border-radius: 13px;
            font-size: 13px;
            font-weight: bold;
        """)
        header_row.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            color: {text_primary};
            font-size: 15px;
            font-weight: 600;
            background: transparent;
        """)
        header_row.addWidget(title_label)
        header_row.addStretch()

        # 关闭按钮 (微软风格: hover 红底白字)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("msgBoxCloseBtn")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton#msgBoxCloseBtn {{
                background: transparent;
                color: {text_secondary};
                border: none;
                border-radius: 6px;
                font-size: 14px;
                padding: 0;
            }}
            QPushButton#msgBoxCloseBtn:hover {{
                background-color: #c42b1c;
                color: #ffffff;
            }}
            QPushButton#msgBoxCloseBtn:pressed {{
                background-color: #b22a1a;
                color: #ffffff;
            }}
        """)
        close_btn.clicked.connect(self.reject)
        header_row.addWidget(close_btn)

        content_layout.addLayout(header_row)

        # 消息正文
        msg_label = QLabel(text)
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_label.setStyleSheet(f"""
            color: {text_secondary};
            font-size: 15px;
            background: transparent;
            padding: 4px 0;
        """)
        content_layout.addWidget(msg_label)

        # 详细信息 (可选)
        self._detail_edit = None
        self._detail_btn = None
        if detailed_text:
            detail_btn = QPushButton("显示详细信息")
            detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            detail_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {accent};
                    border: none;
                    font-size: 12px;
                    padding: 8px 0 4px 0;
                    text-align: left;
                }}
                QPushButton:hover {{
                    color: {text_primary};
                }}
            """)
            content_layout.addWidget(detail_btn)

            detail_edit = QTextEdit()
            detail_edit.setReadOnly(True)
            detail_edit.setPlainText(detailed_text)
            detail_edit.setVisible(False)
            detail_edit.setMaximumHeight(140)
            detail_edit.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {footer_bg};
                    color: {text_muted};
                    border: 1px solid {border};
                    border-radius: 6px;
                    font-size: 11px;
                    font-family: Consolas, 'Courier New', monospace;
                    padding: 8px;
                    margin-top: 4px;
                }}
            """)
            content_layout.addWidget(detail_edit)

            self._detail_edit = detail_edit
            self._detail_btn = detail_btn
            detail_btn.clicked.connect(self._toggle_detail)

        main_layout.addWidget(content_widget)

        # ---------- 底部按钮栏 ----------
        footer = QWidget()
        footer.setStyleSheet(f"background: transparent;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 0, 24, 16)
        footer_layout.setSpacing(10)
        footer_layout.addStretch()

        ok_btn = QPushButton("确定")
        ok_btn.setFixedSize(80, 30)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent};
                color: {"#1e1e2e" if is_dark else "#eff1f5"};
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {self._lighten(accent, 0.1)};
            }}
            QPushButton:pressed {{
                background-color: {self._darken(accent, 0.08)};
            }}
        """)
        ok_btn.clicked.connect(self.accept)
        footer_layout.addWidget(ok_btn)

        main_layout.addWidget(footer)
        root.addLayout(main_layout)

    def paintEvent(self, event) -> None:
        """绘制圆角背景和边框"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(float(rect.x()), float(rect.y()),
                            float(rect.width()), float(rect.height()),
                            self._radius, self._radius)

        # 填充背景
        painter.fillPath(path, QBrush(QColor(self._bg_color)))

        # 绘制边框
        painter.setPen(QPen(QColor(self._border_color), 1))
        painter.drawPath(path)
        painter.end()

    def _toggle_detail(self) -> None:
        """展开/折叠详细信息"""
        if self._detail_edit and self._detail_btn:
            visible = not self._detail_edit.isVisible()
            self._detail_edit.setVisible(visible)
            self._detail_btn.setText("收起详细信息" if visible else "显示详细信息")
            self.adjustSize()

    @staticmethod
    def _find_main_window(widget: QWidget | None) -> QMainWindow | None:
        """
        向上查找 QMainWindow 实例，确保弹窗相对于主窗口居中显示。
        如果找不到，使用 QApplication 的 activeWindow。
        """
        if widget is None:
            app = QApplication.instance()
            return app.activeWindow() if app else None

        current = widget
        while current is not None:
            if isinstance(current, QMainWindow):
                return current
            current = current.parent()

        app = QApplication.instance()
        return app.activeWindow() if app else None

    @staticmethod
    def _is_dark_theme() -> bool:
        """通过检测主窗口背景色判断当前是否为暗色主题"""
        app = QApplication.instance()
        if app:
            for w in app.topLevelWidgets():
                if isinstance(w, QMainWindow):
                    palette = w.palette()
                    bg = palette.color(palette.ColorRole.Window)
                    return bg.lightness() < 128
        return True

    @staticmethod
    def _lighten(hex_color: str, factor: float) -> str:
        """提亮颜色"""
        c = QColor(hex_color)
        h, s, l, a = c.getHslF()
        l = min(1.0, l + factor)
        c.setHslF(h, s, l, a)
        return c.name()

    @staticmethod
    def _darken(hex_color: str, factor: float) -> str:
        """加深颜色"""
        c = QColor(hex_color)
        h, s, l, a = c.getHslF()
        l = max(0.0, l - factor)
        c.setHslF(h, s, l, a)
        return c.name()

    def showEvent(self, event) -> None:
        """显示事件：居中弹窗到父窗口"""
        super().showEvent(event)
        parent = self.parent()
        if parent:
            parent_geo = parent.geometry()
            self_size = self.size()
            x = parent_geo.x() + (parent_geo.width() - self_size.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self_size.height()) // 2
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self_size = self.size()
                x = (geo.width() - self_size.width()) // 2
                y = (geo.height() - self_size.height()) // 2
                self.move(x, y)

    # ==================== 静态方法接口 ====================

    @staticmethod
    def information(parent: QWidget | None, title: str, text: str) -> None:
        """显示信息提示弹窗"""
        dlg = StyledMessageBox(parent, StyledMessageBox.INFO, title, text)
        dlg.exec()

    @staticmethod
    def warning(parent: QWidget | None, title: str, text: str) -> None:
        """显示警告弹窗"""
        dlg = StyledMessageBox(parent, StyledMessageBox.WARNING, title, text)
        dlg.exec()

    @staticmethod
    def critical(
        parent: QWidget | None,
        title: str,
        text: str,
        detailed_text: str = "",
    ) -> None:
        """显示错误弹窗，支持展开详细信息"""
        dlg = StyledMessageBox(
            parent, StyledMessageBox.CRITICAL, title, text,
            detailed_text=detailed_text,
        )
        dlg.exec()
