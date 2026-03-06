"""
path_input_group.py - 可复用的路径输入组件
============================================

职责:
    - 提供图片目录、标签目录、classes.txt 的输入 UI
    - 支持按需显示/隐藏各类路径输入
    - 发射 paths_changed 信号通知路径变化
    - 支持多实例间路径同步

使用示例:
    # 显示全部路径输入
    path_group = PathInputGroup(show_image_dir=True, show_label_dir=True, show_classes=True)
    
    # 只显示图片和标签目录
    path_group = PathInputGroup(show_image_dir=True, show_label_dir=True, show_classes=False)
    
    # 获取路径
    img_dir = path_group.get_image_dir()  # -> Optional[Path]
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


class PathInputGroup(QWidget):
    """
    可复用的路径输入组 (图片目录 / 标签目录 / classes.txt)
    
    Signals:
        paths_changed(): 任一路径发生变化时发射
    """
    
    # 路径变化信号
    paths_changed = Signal()
    
    def __init__(
        self,
        show_image_dir: bool = True,
        show_label_dir: bool = True,
        show_classes: bool = True,
        group_title: str = "数据源路径",
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        初始化路径输入组
        
        Args:
            show_image_dir: 是否显示图片目录输入
            show_label_dir: 是否显示标签目录输入
            show_classes: 是否显示 classes.txt 输入
            group_title: GroupBox 标题
            parent: 父控件
        """
        super().__init__(parent)
        
        # 配置
        self._show_image_dir = show_image_dir
        self._show_label_dir = show_label_dir
        self._show_classes = show_classes
        
        # UI 控件引用
        self._image_dir_input: Optional[QLineEdit] = None
        self._label_dir_input: Optional[QLineEdit] = None
        self._classes_input: Optional[QLineEdit] = None
        
        # 构建 UI
        self._setup_ui(group_title)
        self._connect_signals()
    
    def _setup_ui(self, group_title: str) -> None:
        """构建 UI"""
        from PySide6.QtWidgets import QVBoxLayout
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        group = QGroupBox(group_title)
        grid = QGridLayout(group)
        grid.setColumnStretch(1, 1)  # 输入框列拉伸
        grid.setColumnStretch(2, 0)  # 按钮列固定
        
        row = 0
        
        # 图片目录
        if self._show_image_dir:
            grid.addWidget(QLabel("图片目录:"), row, 0)
            self._image_dir_input = QLineEdit()
            self._image_dir_input.setPlaceholderText("选择图片所在目录 (必填)")
            grid.addWidget(self._image_dir_input, row, 1)
            
            self._image_browse_btn = QPushButton("浏览")
            self._image_browse_btn.setFixedWidth(60)
            grid.addWidget(self._image_browse_btn, row, 2)
            row += 1
        
        # 标签目录
        if self._show_label_dir:
            grid.addWidget(QLabel("标签目录:"), row, 0)
            self._label_dir_input = QLineEdit()
            self._label_dir_input.setPlaceholderText("可选 - 留空则自动搜索 labels/Annotations/")
            self._label_dir_input.setToolTip(
                "标签源目录 (可选)\n\n"
                "留空时自动检测:\n"
                "• images/ → labels/ (YOLO)\n"
                "• JPEGImages/ → Annotations/ (VOC)"
            )
            grid.addWidget(self._label_dir_input, row, 1)
            
            self._label_browse_btn = QPushButton("浏览")
            self._label_browse_btn.setFixedWidth(60)
            grid.addWidget(self._label_browse_btn, row, 2)
            row += 1
        
        # classes.txt
        if self._show_classes:
            grid.addWidget(QLabel("类别文件:"), row, 0)
            self._classes_input = QLineEdit()
            self._classes_input.setPlaceholderText("classes.txt (可选)")
            grid.addWidget(self._classes_input, row, 1)
            
            self._classes_btn = QPushButton("加载")
            self._classes_btn.setFixedWidth(60)
            grid.addWidget(self._classes_btn, row, 2)
            row += 1
        
        main_layout.addWidget(group)
    
    def _connect_signals(self) -> None:
        """连接信号"""
        # 浏览按钮
        if self._show_image_dir:
            self._image_browse_btn.clicked.connect(self._on_browse_image_dir)
            self._image_dir_input.textChanged.connect(self._on_path_changed)
        
        if self._show_label_dir:
            self._label_browse_btn.clicked.connect(self._on_browse_label_dir)
            self._label_dir_input.textChanged.connect(self._on_path_changed)
        
        if self._show_classes:
            self._classes_btn.clicked.connect(self._on_browse_classes)
            self._classes_input.textChanged.connect(self._on_path_changed)
    
    # ============================================================
    # 公开 API
    # ============================================================
    
    def get_image_dir(self) -> Optional[Path]:
        """获取图片目录路径"""
        if self._image_dir_input:
            text = self._image_dir_input.text().strip()
            if text:
                return Path(text)
        return None
    
    def get_label_dir(self) -> Optional[Path]:
        """获取标签目录路径"""
        if self._label_dir_input:
            text = self._label_dir_input.text().strip()
            if text:
                return Path(text)
        return None
    
    def get_classes_path(self) -> Optional[Path]:
        """获取 classes.txt 路径"""
        if self._classes_input:
            text = self._classes_input.text().strip()
            if text:
                return Path(text)
        return None
    
    def set_image_dir(self, path: str) -> None:
        """设置图片目录路径"""
        if self._image_dir_input:
            self._image_dir_input.setText(path)
    
    def set_label_dir(self, path: str) -> None:
        """设置标签目录路径"""
        if self._label_dir_input:
            self._label_dir_input.setText(path)
    
    def set_classes_path(self, path: str) -> None:
        """设置 classes.txt 路径"""
        if self._classes_input:
            self._classes_input.setText(path)
    
    def get_all_paths(self) -> dict:
        """获取所有路径 (用于同步)"""
        return {
            "image_dir": self._image_dir_input.text().strip() if self._image_dir_input else "",
            "label_dir": self._label_dir_input.text().strip() if self._label_dir_input else "",
            "classes": self._classes_input.text().strip() if self._classes_input else "",
        }
    
    def set_all_paths(self, paths: dict, emit_signal: bool = False) -> None:
        """
        设置所有路径 (用于同步)
        
        Args:
            paths: 包含 image_dir, label_dir, classes 的字典
            emit_signal: 是否发射 paths_changed 信号
        """
        # 暂时阻止信号发射以避免循环
        if not emit_signal:
            if self._image_dir_input:
                self._image_dir_input.blockSignals(True)
            if self._label_dir_input:
                self._label_dir_input.blockSignals(True)
            if self._classes_input:
                self._classes_input.blockSignals(True)
        
        if self._image_dir_input and "image_dir" in paths:
            self._image_dir_input.setText(paths["image_dir"])
        if self._label_dir_input and "label_dir" in paths:
            self._label_dir_input.setText(paths["label_dir"])
        if self._classes_input and "classes" in paths:
            self._classes_input.setText(paths["classes"])
        
        # 恢复信号
        if not emit_signal:
            if self._image_dir_input:
                self._image_dir_input.blockSignals(False)
            if self._label_dir_input:
                self._label_dir_input.blockSignals(False)
            if self._classes_input:
                self._classes_input.blockSignals(False)
    
    # ============================================================
    # 槽函数
    # ============================================================
    
    @Slot()
    def _on_browse_image_dir(self) -> None:
        """选择图片目录"""
        path = QFileDialog.getExistingDirectory(self, "选择图片目录")
        if path:
            self._image_dir_input.setText(path)
    
    @Slot()
    def _on_browse_label_dir(self) -> None:
        """选择标签目录"""
        path = QFileDialog.getExistingDirectory(self, "选择标签目录")
        if path:
            self._label_dir_input.setText(path)
    
    @Slot()
    def _on_browse_classes(self) -> None:
        """选择 classes.txt"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择类别文件", "", "文本文件 (*.txt)"
        )
        if path:
            self._classes_input.setText(path)
    
    @Slot()
    def _on_path_changed(self) -> None:
        """路径变化时发射信号"""
        self.paths_changed.emit()
