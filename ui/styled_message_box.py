"""
styled_message_box.py - 自定义样式消息弹窗
============================================

职责:
    - 替代原生 QMessageBox，提供与项目主题一致的弹窗样式
    - 参考微软 Fluent Design / Windows 11 对话框风格
    - 自动居中到应用主窗口
    - 提供 information / warning / critical / question 静态方法

架构要点:
    - 继承 QDialog，完全自绘界面
    - 通过 ThemeManager 令牌获取颜色，跟随主题切换
    - 支持 detailedText 展开/收起
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QBrush, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.theme import ThemeManager
from utils.i18n import t


class StyledMessageBox(QDialog):
    """自定义样式消息弹窗 — 微软 Fluent Design 风格 + ThemeManager 配色"""

    # 消息类型常量
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    QUESTION = "question"

    # 各类型对应的图标
    _TYPE_ICONS = {
        "info": "✓",
        "warning": "!",
        "critical": "✕",
        "question": "?",
    }

    def __init__(
        self,
        parent: QWidget | None,
        msg_type: str,
        title: str,
        text: str,
        detailed_text: str = "",
        accept_text: str | None = None,
        reject_text: str = "",
        third_text: str = "",
    ) -> None:
        if accept_text is None:
            accept_text = t("ok")

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

        # 从 ThemeManager 获取颜色
        tm = ThemeManager.instance()
        type_colors = tm.get_dialog_type_colors(msg_type)
        accent = type_colors["accent"]
        icon_bg = type_colors["icon_bg"]
        icon_char = self._TYPE_ICONS.get(msg_type, "✓")

        bg = tm.get_color("dialog_bg")
        surface = tm.get_color("dialog_surface")
        border = tm.get_color("dialog_border")
        text_primary = tm.get_color("dialog_text_primary")
        text_secondary = tm.get_color("dialog_text_secondary")
        text_muted = tm.get_color("dialog_text_muted")
        btn_bg = tm.get_color("dialog_btn_bg")
        btn_hover = tm.get_color("dialog_btn_hover")
        footer_bg = tm.get_color("dialog_footer_bg")

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

        icon_label = QLabel(icon_char)
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
            detail_btn = QPushButton(t("show_details"))
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
        footer.setStyleSheet("background: transparent;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 0, 24, 16)
        footer_layout.setSpacing(10)
        footer_layout.addStretch()

        _secondary_btn_style = f"""
            QPushButton {{
                background-color: {btn_bg};
                color: {text_primary};
                border: 1px solid {border};
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
            }}
            QPushButton:pressed {{
                background-color: {surface};
            }}
        """

        if reject_text:
            cancel_btn = QPushButton(reject_text)
            cancel_btn.setFixedSize(80, 30)
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel_btn.setStyleSheet(_secondary_btn_style)
            cancel_btn.clicked.connect(self.reject)
            footer_layout.addWidget(cancel_btn)

        if third_text:
            third_btn = QPushButton(third_text)
            third_btn.setFixedSize(80, 30)
            third_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            third_btn.setStyleSheet(_secondary_btn_style)
            third_btn.clicked.connect(lambda: self.done(2))
            footer_layout.addWidget(third_btn)

        ok_btn = QPushButton(accept_text)
        ok_btn.setFixedSize(80, 30)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent};
                color: {tm.get_color("dialog_bg")};
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {tm.lighten(accent, 0.1)};
            }}
            QPushButton:pressed {{
                background-color: {tm.darken(accent, 0.08)};
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
            self._detail_btn.setText(t("hide_details") if visible else t("show_details"))
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
    def information(
        parent: QWidget | None,
        title: str,
        text: str,
        detailed_text: str = "",
    ) -> None:
        """显示信息提示弹窗"""
        dlg = StyledMessageBox(
            parent, StyledMessageBox.INFO, title, text,
            detailed_text=detailed_text,
        )
        dlg.exec()

    @staticmethod
    def warning(
        parent: QWidget | None,
        title: str,
        text: str,
        detailed_text: str = "",
    ) -> None:
        """显示警告弹窗"""
        dlg = StyledMessageBox(
            parent, StyledMessageBox.WARNING, title, text,
            detailed_text=detailed_text,
        )
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

    @staticmethod
    def question(
        parent: QWidget | None,
        title: str,
        text: str,
        accept_text: str | None = None,
        reject_text: str | None = None,
    ) -> bool:
        """显示确认弹窗，返回是否确认"""
        if accept_text is None:
            accept_text = t("ok")
        if reject_text is None:
            reject_text = t("cancel")
        dlg = StyledMessageBox(
            parent,
            StyledMessageBox.QUESTION,
            title,
            text,
            accept_text=accept_text,
            reject_text=reject_text,
        )
        return dlg.exec() == QDialog.DialogCode.Accepted

    @staticmethod
    def three_way_question(
        parent: QWidget | None,
        title: str,
        text: str,
        accept_text: str | None = None,
        reject_text: str | None = None,
        third_text: str | None = None,
    ) -> str:
        """
        显示三选一确认弹窗

        Returns:
            "overwrite" - 用户选择覆盖 (accept)
            "new"       - 用户选择新建 (third)
            "cancel"    - 用户选择取消 (reject / 关闭)
        """
        if accept_text is None:
            accept_text = t("overwrite")
        if reject_text is None:
            reject_text = t("cancel")
        if third_text is None:
            third_text = t("create_new")
        dlg = StyledMessageBox(
            parent,
            StyledMessageBox.QUESTION,
            title,
            text,
            accept_text=accept_text,
            reject_text=reject_text,
            third_text=third_text,
        )
        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted:
            return "overwrite"
        elif result == 2:
            return "new"
        return "cancel"


class StyledProgressDialog(QDialog):
    """自定义样式进度弹窗，与 StyledMessageBox 保持一致风格"""

    canceled = Signal()

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        text: str,
        cancel_text: str | None = None,
    ) -> None:
        if cancel_text is None:
            cancel_text = t("cancel")

        main_window = StyledMessageBox._find_main_window(parent)
        super().__init__(main_window)

        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedWidth(360)

        # 从 ThemeManager 获取颜色
        tm = ThemeManager.instance()
        type_colors = tm.get_dialog_type_colors(StyledMessageBox.QUESTION)
        accent = type_colors["accent"]
        icon_bg = type_colors["icon_bg"]

        bg = tm.get_color("dialog_bg")
        surface = tm.get_color("dialog_surface")
        border = tm.get_color("dialog_border")
        text_primary = tm.get_color("dialog_text_primary")
        text_secondary = tm.get_color("dialog_text_secondary")
        btn_bg = tm.get_color("dialog_btn_bg")
        btn_hover = tm.get_color("dialog_btn_hover")

        self._bg_color = bg
        self._border_color = border
        self._radius = 10

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(24, 20, 24, 16)
        content_layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)

        icon_label = QLabel("⟳")
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

        close_btn = QPushButton("✕")
        close_btn.setObjectName("styledProgressCloseBtn")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton#styledProgressCloseBtn {{
                background: transparent;
                color: {text_secondary};
                border: none;
                border-radius: 6px;
                font-size: 14px;
                padding: 0;
            }}
            QPushButton#styledProgressCloseBtn:hover {{
                background-color: #c42b1c;
                color: #ffffff;
            }}
            QPushButton#styledProgressCloseBtn:pressed {{
                background-color: #b22a1a;
                color: #ffffff;
            }}
        """)
        close_btn.clicked.connect(self._emit_canceled)
        header_row.addWidget(close_btn)
        content_layout.addLayout(header_row)

        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(f"""
            color: {text_secondary};
            font-size: 14px;
            background: transparent;
            padding: 4px 0;
        """)
        content_layout.addWidget(self._label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {surface};
                color: {text_primary};
                border: 1px solid {border};
                border-radius: 6px;
                text-align: center;
                height: 20px;
                padding: 1px;
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 5px;
            }}
        """)
        content_layout.addWidget(self._progress_bar)
        main_layout.addWidget(content_widget)

        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 0, 24, 16)
        footer_layout.setSpacing(10)
        footer_layout.addStretch()

        self._cancel_btn = QPushButton(cancel_text)
        self._cancel_btn.setFixedSize(80, 30)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                color: {text_primary};
                border: 1px solid {border};
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
            }}
            QPushButton:pressed {{
                background-color: {surface};
            }}
        """)
        self._cancel_btn.clicked.connect(self._emit_canceled)
        footer_layout.addWidget(self._cancel_btn)
        main_layout.addWidget(footer)

        root.addLayout(main_layout)

    def _emit_canceled(self) -> None:
        """发射取消信号"""
        if self._cancel_btn.isEnabled():
            self._cancel_btn.setEnabled(False)
            self.canceled.emit()

    def setLabelText(self, text: str) -> None:
        """更新说明文字"""
        self._label.setText(text)

    def setRange(self, minimum: int, maximum: int) -> None:
        """设置进度范围"""
        self._progress_bar.setRange(minimum, maximum)

    def setMaximum(self, maximum: int) -> None:
        """设置最大值"""
        self._progress_bar.setMaximum(maximum)

    def maximum(self) -> int:
        """获取最大值"""
        return self._progress_bar.maximum()

    def setValue(self, value: int) -> None:
        """设置当前值"""
        self._progress_bar.setValue(value)

    def value(self) -> int:
        """获取当前值"""
        return self._progress_bar.value()

    def paintEvent(self, event) -> None:
        """绘制圆角背景和边框"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(
            float(rect.x()),
            float(rect.y()),
            float(rect.width()),
            float(rect.height()),
            self._radius,
            self._radius,
        )

        painter.fillPath(path, QBrush(QColor(self._bg_color)))
        painter.setPen(QPen(QColor(self._border_color), 1))
        painter.drawPath(path)
        painter.end()

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
