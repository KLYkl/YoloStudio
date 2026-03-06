"""
focus_widgets.py - 防误触控件
============================================

提供需要焦点才能响应滚轮的 SpinBox 和 Slider 控件。
避免在滚动页面时意外修改参数值。
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QSlider,
    QSpinBox,
)


class FocusSpinBox(QSpinBox):
    """需要焦点才能响应滚轮的 SpinBox"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 设置焦点策略为强焦点 (点击/Tab 可获取焦点)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        """只有在获得焦点时才响应滚轮"""
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            # 将事件传递给父控件 (滚动区域)
            event.ignore()


class FocusDoubleSpinBox(QDoubleSpinBox):
    """需要焦点才能响应滚轮的 DoubleSpinBox"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        """只有在获得焦点时才响应滚轮"""
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class FocusSlider(QSlider):
    """需要焦点才能响应滚轮的 Slider"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        """只有在获得焦点时才响应滚轮"""
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class FocusComboBox(QComboBox):
    """需要焦点才能响应滚轮的 ComboBox"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        """只有在获得焦点时才响应滚轮"""
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
