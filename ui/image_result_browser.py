"""
image_result_browser.py - 图片结果浏览器
============================================

职责:
    - 显示图片推理结果
    - 支持翻页浏览已处理图片
    - 支持切换原图/标注图

架构要点:
    - 独立于视频预览，专用于图片模式
    - 复用 PreviewCanvas 进行图片显示
    - 通过 Signal/Slot 与主控件通信
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.predict_preview import PreviewCanvas


class ImageResultBrowser(QWidget):
    """
    图片结果浏览器
    
    用于图片模式下显示推理结果和翻页浏览。
    
    布局:
        - 中间: PreviewCanvas (显示图片)
        - 底部: 导航栏 (翻页按钮 + 页码 + 预测框开关)
    
    Signals:
        prev_requested(): 请求上一张
        next_requested(): 请求下一张
        toggle_boxes_changed(bool): 预测框显示状态变化
    """
    
    prev_requested = Signal()
    next_requested = Signal()
    toggle_boxes_changed = Signal(bool)
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        
        # 当前显示的图片
        self._original: Optional[np.ndarray] = None
        self._annotated: Optional[np.ndarray] = None
        self._show_boxes: bool = True
        
        self._setup_ui()
        self._setup_shortcuts()
    
    def _setup_ui(self) -> None:
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # 预览画布
        self._preview_canvas = PreviewCanvas()
        layout.addWidget(self._preview_canvas, 1)
        
        # 导航栏
        nav_bar = self._create_nav_bar()
        layout.addWidget(nav_bar)
    
    def _create_nav_bar(self) -> QFrame:
        """创建导航栏"""
        bar = QFrame()
        bar.setObjectName("statusBar")
        bar.setFixedHeight(36)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(12)
        
        # 左侧弹性空间 (使中间内容居中)
        layout.addStretch()
        
        # 上一张按钮
        self._prev_btn = QPushButton("◀ 上一张")
        self._prev_btn.setFixedSize(80, 28)
        self._prev_btn.setEnabled(False)
        self._prev_btn.clicked.connect(self._on_prev_clicked)
        layout.addWidget(self._prev_btn)
        
        # 页码显示
        self._page_label = QLabel("0 / 0 已处理")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setMinimumWidth(100)
        layout.addWidget(self._page_label)
        
        # 下一张按钮
        self._next_btn = QPushButton("下一张 ▶")
        self._next_btn.setFixedSize(80, 28)
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self._on_next_clicked)
        layout.addWidget(self._next_btn)
        
        # 右侧弹性空间 (使中间内容居中)
        layout.addStretch()
        
        # 显示预测框开关（固定在右侧）
        self._show_boxes_check = QCheckBox("显示预测框")
        self._show_boxes_check.setChecked(True)
        self._show_boxes_check.toggled.connect(self._on_toggle_boxes)
        layout.addWidget(self._show_boxes_check)
        
        return bar
    
    def _setup_shortcuts(self) -> None:
        """设置快捷键"""
        # 左箭头 - 上一张
        shortcut_prev = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        shortcut_prev.activated.connect(self._on_prev_clicked)
        
        # 右箭头 - 下一张
        shortcut_next = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        shortcut_next.activated.connect(self._on_next_clicked)
    
    def show_result(
        self,
        original: np.ndarray,
        annotated: np.ndarray,
        detections: list[dict]
    ) -> None:
        """
        显示推理结果
        
        Args:
            original: 原图 (BGR)
            annotated: 标注后的图片 (BGR)
            detections: 检测结果列表
        """
        self._original = original
        self._annotated = annotated
        
        # 根据开关状态显示
        if self._show_boxes:
            self._preview_canvas.update_frame(annotated)
        else:
            self._preview_canvas.update_frame(original)
    
    def update_navigation(self, current: int, total: int) -> None:
        """
        更新导航状态
        
        Args:
            current: 当前索引 (0-based)
            total: 已处理总数
        """
        # 更新页码显示 (显示为 1-based)
        if total > 0:
            self._page_label.setText(f"{current + 1} / {total} 已处理")
        else:
            self._page_label.setText("0 / 0 已处理")
        
        # 更新按钮状态
        self._prev_btn.setEnabled(current > 0)
        self._next_btn.setEnabled(current < total - 1)
    
    def clear(self) -> None:
        """清空显示"""
        self._original = None
        self._annotated = None
        self._preview_canvas.clear_display()
        self.update_navigation(-1, 0)
    
    @Slot()
    def _on_prev_clicked(self) -> None:
        """上一张按钮点击"""
        if self._prev_btn.isEnabled():
            self.prev_requested.emit()
    
    @Slot()
    def _on_next_clicked(self) -> None:
        """下一张按钮点击"""
        if self._next_btn.isEnabled():
            self.next_requested.emit()
    
    @Slot(bool)
    def _on_toggle_boxes(self, checked: bool) -> None:
        """预测框开关变化"""
        self._show_boxes = checked
        
        # 立即更新显示
        if checked and self._annotated is not None:
            self._preview_canvas.update_frame(self._annotated)
        elif not checked and self._original is not None:
            self._preview_canvas.update_frame(self._original)
        
        self.toggle_boxes_changed.emit(checked)
    
    @property
    def show_boxes(self) -> bool:
        """当前是否显示预测框"""
        return self._show_boxes
    
    @show_boxes.setter
    def show_boxes(self, value: bool) -> None:
        """设置是否显示预测框"""
        self._show_boxes_check.setChecked(value)


class ImageProgressBar(QFrame):
    """
    图片批量处理进度条
    
    用于批量处理时显示进度。
    """
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        
        self.setObjectName("statusBar")
        self.setFixedHeight(36)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(12)
        
        # 进度文本
        self._status_label = QLabel("准备中...")
        layout.addWidget(self._status_label)
        
        layout.addStretch()
        
        # 进度数值
        self._progress_label = QLabel("0 / 0")
        self._progress_label.setObjectName("accentLabel")
        layout.addWidget(self._progress_label)
    
    def update_progress(self, current: int, total: int, status: str = "正在处理...") -> None:
        """
        更新进度
        
        Args:
            current: 当前处理数
            total: 总数
            status: 状态文本
        """
        self._status_label.setText(status)
        self._progress_label.setText(f"{current} / {total}")
    
    def set_finished(self, message: str = "处理完成") -> None:
        """设置为完成状态"""
        self._status_label.setText(message)
        self._status_label.setObjectName("successLabel")
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)
