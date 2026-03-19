"""
base_ui.py - 基础 UI 组件和样式
============================================

职责:
    - 提供可复用的基础 UI 组件
    - 导出全局样式表常量 (兼容旧代码)
    - 统一视觉风格

架构要点:
    - CardWidget: 带圆角和阴影的容器控件
    - DARK_THEME_QSS / LIGHT_THEME_QSS: 从 ui.theme 生成
    - ThemeManager: 推荐使用的新接口
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

from ui.theme import (
    DARK_TOKENS,
    LIGHT_TOKENS,
    SHAPE_TOKENS,
    ThemeManager,
    generate_qss,
)


def set_button_class(btn: QPushButton, cls: str) -> None:
    """Dynamically switch a button's QSS class and refresh its style."""
    btn.setProperty("class", cls)
    btn.style().unpolish(btn)
    btn.style().polish(btn)


# ============================================================
# 全局样式常量 (兼容旧代码，从 theme 模块生成)
# ============================================================

DARK_THEME_QSS = generate_qss(DARK_TOKENS, SHAPE_TOKENS, is_dark=True)
LIGHT_THEME_QSS = generate_qss(LIGHT_TOKENS, SHAPE_TOKENS, is_dark=False)


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
