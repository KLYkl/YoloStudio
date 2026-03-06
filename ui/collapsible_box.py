"""
collapsible_box.py - 可折叠分组控件
============================================

职责:
    - 提供可折叠的分组容器
    - 点击标题栏展开/折叠内容
    - 带平滑动画效果

架构要点:
    - 继承 QWidget
    - 使用 QPropertyAnimation 实现动画
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QParallelAnimationGroup,
    QPropertyAnimation,
    Qt,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class CollapsibleGroupBox(QWidget):
    """
    可折叠分组容器
    
    点击标题栏可展开/折叠内容区域，带平滑动画。
    
    Example:
        group = CollapsibleGroupBox("输入源")
        group.add_widget(some_widget)
        group.set_collapsed(False)  # 默认展开
    """
    
    def __init__(
        self,
        title: str = "",
        parent: Optional[QWidget] = None,
        collapsed: bool = False
    ) -> None:
        """
        初始化可折叠分组
        
        Args:
            title: 标题文本
            parent: 父控件
            collapsed: 初始是否折叠
        """
        super().__init__(parent)
        
        self._collapsed = collapsed
        self._animation_duration = 150  # 动画时长 (毫秒)
        
        self._setup_ui(title)
        self._setup_animations()
        
        # 设置初始状态
        if collapsed:
            self._content_area.setMaximumHeight(0)
            self._toggle_btn.setText("▶")
        else:
            self._toggle_btn.setText("▼")
    
    def _setup_ui(self, title: str) -> None:
        """构建 UI"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # ========== 标题栏 ==========
        self._header = QFrame()
        self._header.setObjectName("collapsibleHeader")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(8, 6, 8, 6)
        header_layout.setSpacing(8)
        
        # 折叠按钮
        self._toggle_btn = QToolButton()
        self._toggle_btn.setObjectName("collapsibleToggle")
        self._toggle_btn.setText("▼")
        self._toggle_btn.clicked.connect(self.toggle)
        
        # 标题标签
        self._title_label = QLabel(title)
        self._title_label.setObjectName("collapsibleTitle")
        
        header_layout.addWidget(self._toggle_btn)
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()
        
        # 点击标题栏也能折叠
        self._header.mousePressEvent = lambda e: self.toggle()
        
        main_layout.addWidget(self._header)
        
        # ========== 内容区域 ==========
        self._content_area = QScrollArea()
        self._content_area.setFrameShape(QFrame.Shape.NoFrame)
        self._content_area.setWidgetResizable(True)
        self._content_area.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        
        # 内容容器
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(8, 8, 8, 8)
        self._content_layout.setSpacing(8)
        
        self._content_area.setWidget(self._content_widget)
        
        main_layout.addWidget(self._content_area)
    
    def _setup_animations(self) -> None:
        """设置动画"""
        self._animation_group = QParallelAnimationGroup(self)
        
        # 内容区域高度动画
        self._content_animation = QPropertyAnimation(
            self._content_area,
            b"maximumHeight"
        )
        self._content_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._content_animation.setDuration(self._animation_duration)
        
        self._animation_group.addAnimation(self._content_animation)
    
    def add_widget(self, widget: QWidget) -> None:
        """
        添加子控件到内容区
        
        Args:
            widget: 要添加的控件
        """
        self._content_layout.addWidget(widget)
    
    def add_layout(self, layout) -> None:
        """
        添加布局到内容区
        
        Args:
            layout: 要添加的布局
        """
        self._content_layout.addLayout(layout)
    
    def set_title(self, title: str) -> None:
        """设置标题"""
        self._title_label.setText(title)
    
    def is_collapsed(self) -> bool:
        """返回当前是否折叠"""
        return self._collapsed
    
    def set_collapsed(self, collapsed: bool, animate: bool = True) -> None:
        """
        设置折叠状态
        
        Args:
            collapsed: 是否折叠
            animate: 是否使用动画
        """
        if collapsed == self._collapsed:
            return
        
        self._collapsed = collapsed
        
        # 计算目标高度
        content_height = self._content_widget.sizeHint().height()
        
        if animate:
            self._content_animation.setStartValue(
                0 if not collapsed else content_height
            )
            self._content_animation.setEndValue(
                content_height if not collapsed else 0
            )
            self._animation_group.start()
        else:
            self._content_area.setMaximumHeight(
                content_height if not collapsed else 0
            )
        
        # 更新按钮文本
        self._toggle_btn.setText("▶" if collapsed else "▼")
    
    def toggle(self) -> None:
        """切换折叠状态"""
        self.set_collapsed(not self._collapsed)
    
    def content_layout(self) -> QVBoxLayout:
        """返回内容区布局"""
        return self._content_layout
