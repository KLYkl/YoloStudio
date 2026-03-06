"""
predict_preview.py - 预览画布
============================================

职责:
    - 显示实时推理结果
    - 自适应缩放，保持纵横比
    - 黑色背景填充空白区域

架构要点:
    - 继承 QLabel
    - 接收 OpenCV BGR 帧并转换为 QPixmap
"""

from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class PreviewCanvas(QLabel):
    """
    预览画布
    
    用于显示实时推理结果，支持自适应缩放。
    
    Features:
        - 接收 OpenCV BGR 帧
        - 保持纵横比缩放
        - 黑色背景填充空白区域
    """
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        
        self._current_pixmap: Optional[QPixmap] = None
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """设置 UI"""
        # 黑色背景
        self.setStyleSheet("""
            QLabel {
                background-color: #000000;
                border-radius: 8px;
            }
        """)
        
        # 居中对齐
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 尺寸策略
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        
        # 最小尺寸
        self.setMinimumSize(320, 240)
        
        # 初始占位文本
        self.setText("📷 等待预测...")
        self.setStyleSheet("""
            QLabel {
                background-color: #000000;
                border-radius: 8px;
                color: #6c7086;
            }
        """)
    
    @Slot(np.ndarray)
    def update_frame(self, frame: np.ndarray) -> None:
        """
        更新显示帧
        
        Args:
            frame: OpenCV BGR 格式的图像
        """
        if frame is None:
            return
        
        try:
            # BGR -> RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            
            # 创建 QImage
            q_img = QImage(
                rgb_frame.data,
                w,
                h,
                bytes_per_line,
                QImage.Format.Format_RGB888
            )
            
            # 转换为 QPixmap
            self._current_pixmap = QPixmap.fromImage(q_img)
            
            # 缩放并显示
            self._update_display()
            
        except Exception:
            pass
    
    def _update_display(self) -> None:
        """更新显示 (缩放到当前尺寸)"""
        if self._current_pixmap is None:
            return
        
        # 获取当前可用尺寸
        available_size = self.size()
        
        # 缩放 pixmap，保持纵横比
        scaled_pixmap = self._current_pixmap.scaled(
            available_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        self.setPixmap(scaled_pixmap)
    
    def resizeEvent(self, event: QResizeEvent) -> None:
        """窗口缩放时重新计算显示"""
        super().resizeEvent(event)
        self._update_display()
    
    def clear_display(self) -> None:
        """清空显示"""
        self._current_pixmap = None
        self.clear()
        self.setText("📷 等待预测...")
