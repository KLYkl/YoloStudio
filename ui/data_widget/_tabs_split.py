"""
_tabs_split.py - SplitTabMixin: 划分 + YAML Tab UI + 逻辑
============================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.data_handler import SplitMode, SplitResult
from ui.focus_widgets import FocusSlider, FocusSpinBox


class SplitTabMixin:
    """划分 + YAML Tab 的 UI 构建 + 槽函数"""

    # ==================== UI 构建 ====================

    def _create_split_tab(self) -> QWidget:
        """
        创建划分 Tab (路径区 + 左右分栏布局)

        顶部: 路径输入组
        下方:
            左侧: 划分参数
            右侧: 执行详情
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setSpacing(6)

        # 路径输入组已提升到 DataWidget 外层 (self.path_group)

        # 下方内容区 (水平布局)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(8)

        # ========== 左侧: 划分工具 (Flex 1) ==========
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)

        left_group = QGroupBox("划分工具")
        left_group_layout = QVBoxLayout(left_group)
        left_group_layout.setSpacing(6)

        # --- Group 1: 划分参数 ---
        param_group = QGroupBox("划分参数")
        param_layout = QVBoxLayout(param_group)

        ratio_row = QHBoxLayout()
        ratio_row.addWidget(QLabel("划分比例:"))
        self.ratio_slider = FocusSlider(Qt.Orientation.Horizontal)
        self.ratio_slider.setRange(50, 95)
        self.ratio_slider.setValue(80)
        self.ratio_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.ratio_slider.setTickInterval(5)

        self.ratio_label = QLabel("训练: 80% | 验证: 20%")
        self.ratio_label.setFixedWidth(130)

        ratio_row.addWidget(self.ratio_slider, 1)
        ratio_row.addWidget(self.ratio_label)
        param_layout.addLayout(ratio_row)

        # 随机种子
        seed_row = QHBoxLayout()
        seed_row.addWidget(QLabel("随机种子:"))
        self.seed_spin = FocusSpinBox()
        self.seed_spin.setRange(0, 99999)
        self.seed_spin.setValue(42)
        self.seed_spin.setFixedWidth(80)
        seed_row.addWidget(self.seed_spin)
        seed_row.addStretch()
        param_layout.addLayout(seed_row)

        # 忽略无标签图片
        self.ignore_orphans_check = QCheckBox("忽略无标签图片")
        self.ignore_orphans_check.setToolTip("跳过没有对应标签文件的图片")
        param_layout.addWidget(self.ignore_orphans_check)

        left_group_layout.addWidget(param_group)

        # --- Group 2: 输出策略 ---
        output_group = QGroupBox("输出策略")
        output_layout = QVBoxLayout(output_group)

        # 划分模式 (横排)
        mode_row = QHBoxLayout()
        self.copy_radio = QRadioButton("复制")
        self.move_radio = QRadioButton("移动")
        self.index_radio = QRadioButton("索引")
        self.copy_radio.setChecked(True)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.copy_radio, 0)
        self.mode_group.addButton(self.move_radio, 1)
        self.mode_group.addButton(self.index_radio, 2)

        mode_row.addWidget(self.copy_radio)
        mode_row.addWidget(self.move_radio)
        mode_row.addWidget(self.index_radio)
        mode_row.addStretch()
        output_layout.addLayout(mode_row)

        # 清空目标
        self.clear_output_check = QCheckBox("清空目标目录")
        self.clear_output_check.setToolTip("删除 train/ 和 val/ 目录后再写入")
        output_layout.addWidget(self.clear_output_check)

        output_layout.addSpacing(2)

        # 输出目录
        output_layout.addWidget(QLabel("输出目录:"))

        dir_row = QHBoxLayout()
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setPlaceholderText("划分后保存位置")
        dir_row.addWidget(self.output_dir_input, 1)

        self.output_browse_btn = QPushButton("浏览")
        self.output_browse_btn.setFixedWidth(60)
        dir_row.addWidget(self.output_browse_btn)
        output_layout.addLayout(dir_row)

        output_layout.addSpacing(4)

        # 执行按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.split_btn = QPushButton("🚀 开始划分")
        self.split_btn.setMinimumHeight(28)
        self.split_btn.setProperty("class", "primary")
        btn_row.addWidget(self.split_btn)
        output_layout.addLayout(btn_row)

        left_group_layout.addWidget(output_group)

        left_scroll.setWidget(left_group)
        content_layout.addWidget(left_scroll, 1)  # Flex 1

        # YAML panel embedded beside split controls
        content_layout.addWidget(self._create_yaml_tab(), 2)  # Flex 2

        tab_layout.addLayout(content_layout, 1)  # 拉伸填充

        return tab

    def _create_yaml_tab(self) -> QWidget:
        """
        创建 YAML 配置面板 (统一 GroupBox)

        内部左右分栏:
            左侧: 路径配置 (Train/Val/Output)
            右侧: 类别列表 (可编辑)
        底部: 保存按钮
        """
        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # ========== 统一 GroupBox ==========
        yaml_group = QGroupBox("YAML 配置")
        yaml_layout = QVBoxLayout(yaml_group)

        # ========== 左右分栏布局 ==========
        content_layout = QHBoxLayout()
        content_layout.setSpacing(8)

        # ========== 左侧: 路径配置 (Flex 3) ==========
        left_group = QGroupBox("路径配置")
        left_layout = QVBoxLayout(left_group)

        grid = QGridLayout()
        grid.setSpacing(8)

        # Train 路径
        grid.addWidget(QLabel("Train:"), 0, 0)
        self.train_path_input = QLineEdit()
        self.train_path_input.setPlaceholderText("训练集路径 (划分后自动填充)")
        grid.addWidget(self.train_path_input, 0, 1)
        self.train_browse_btn = QPushButton("...")
        self.train_browse_btn.setFixedWidth(40)
        grid.addWidget(self.train_browse_btn, 0, 2)

        # Val 路径
        grid.addWidget(QLabel("Val:"), 1, 0)
        self.val_path_input = QLineEdit()
        self.val_path_input.setPlaceholderText("验证集路径 (划分后自动填充)")
        grid.addWidget(self.val_path_input, 1, 1)
        self.val_browse_btn = QPushButton("...")
        self.val_browse_btn.setFixedWidth(40)
        grid.addWidget(self.val_browse_btn, 1, 2)

        # YAML 输出路径
        grid.addWidget(QLabel("输出:"), 2, 0)
        self.yaml_output_input = QLineEdit()
        self.yaml_output_input.setPlaceholderText("选择 YAML 保存路径...")
        grid.addWidget(self.yaml_output_input, 2, 1)
        self.yaml_browse_btn = QPushButton("...")
        self.yaml_browse_btn.setFixedWidth(40)
        grid.addWidget(self.yaml_browse_btn, 2, 2)

        left_layout.addLayout(grid)
        left_layout.addStretch()

        content_layout.addWidget(left_group, 3)  # Flex 3

        # ========== 右侧: 类别列表 (Flex 2) ==========
        right_group = QGroupBox("类别列表 (每行一个)")
        right_layout = QVBoxLayout(right_group)

        self.classes_edit = QPlainTextEdit()
        self.classes_edit.setPlaceholderText("扫描后自动填充，也可手动编辑...\n例如:\nexcavator\nbulldozer\ncrane")
        self.classes_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_layout.addWidget(self.classes_edit)

        content_layout.addWidget(right_group, 2)  # Flex 2

        yaml_layout.addLayout(content_layout, 1)  # 拉伸填充

        # ========== 保存按钮 (右对齐) ==========
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.save_yaml_btn = QPushButton("💾 保存 YAML 配置")
        self.save_yaml_btn.setMinimumHeight(28)
        self.save_yaml_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.save_yaml_btn.setProperty("class", "success")
        btn_layout.addWidget(self.save_yaml_btn)
        yaml_layout.addLayout(btn_layout)

        main_layout.addWidget(yaml_group, 1)  # 拉伸填充

        return tab

    # ==================== 槽函数 ====================

    @Slot(int)
    def _on_ratio_changed(self, value: int) -> None:
        """比例滑块变化"""
        self.ratio_label.setText(f"训练: {value}% | 验证: {100 - value}%")

    @Slot()
    def _on_browse_output_dir(self) -> None:
        """选择输出目录"""
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.output_dir_input.setText(path)

    @Slot()
    def _on_split(self) -> None:
        """开始划分数据集"""
        img_path = self.path_group.get_image_dir()
        if not img_path:
            self.log_message.emit("请先选择图片目录")
            return

        if not img_path.exists():
            self.log_message.emit(f"图片目录不存在: {img_path}")
            return

        label_path = self.path_group.get_label_dir()

        output_dir = self.output_dir_input.text().strip()
        if not output_dir:
            self.log_message.emit("请选择输出目录")
            return
        output_path = Path(output_dir)

        from ui.output_dir_check import check_output_dir
        checked = check_output_dir(self, output_path)
        if checked is None:
            return
        output_path = checked
        self.output_dir_input.setText(str(output_path))

        ratio = self.ratio_slider.value() / 100.0
        seed = self.seed_spin.value()

        if self.copy_radio.isChecked():
            mode = SplitMode.COPY
        elif self.move_radio.isChecked():
            mode = SplitMode.MOVE
        else:
            mode = SplitMode.INDEX

        ignore_orphans = self.ignore_orphans_check.isChecked()
        clear_output = self.clear_output_check.isChecked()

        def split_message_callback(msg: str) -> None:
            if "images/train" in msg or "images/val" in msg:
                return
            self._emit_message(msg)

        self._start_worker(
            lambda: self._handler.split_dataset(
                img_path,
                label_dir=label_path,
                output_dir=output_path,
                ratio=ratio,
                seed=seed,
                mode=mode,
                ignore_orphans=ignore_orphans,
                clear_output=clear_output,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
                message_callback=split_message_callback,
            ),
            on_finished=self._on_split_finished,
        )

    def _on_split_finished(self, result: SplitResult) -> None:
        """划分完成回调"""
        self.split_paths = {
            "train": result.train_path,
            "val": result.val_path,
        }

        # Auto-fill YAML panel
        self.train_path_input.setText(result.train_path)
        self.val_path_input.setText(result.val_path)

        # Default YAML output lives next to the split dataset.
        output_dir = self.output_dir_input.text().strip()
        if output_dir:
            self.yaml_output_input.setText(str(Path(output_dir) / "data.yaml"))

        self.log_message.emit(
            f"划分完成: 训练集 {result.train_count} 张, 验证集 {result.val_count} 张"
        )

    @Slot()
    def _on_browse_train(self) -> None:
        """手动选择训练集目录"""
        path = QFileDialog.getExistingDirectory(self, "选择训练集目录")
        if path:
            self.train_path_input.setText(path)

    @Slot()
    def _on_browse_val(self) -> None:
        """手动选择验证集目录"""
        path = QFileDialog.getExistingDirectory(self, "选择验证集目录")
        if path:
            self.val_path_input.setText(path)

    @Slot()
    def _on_browse_yaml(self) -> None:
        """选择 YAML 保存路径"""
        path, _ = QFileDialog.getSaveFileName(
            self, "保存 YAML 配置", "", "YAML 文件 (*.yaml *.yml)"
        )
        if path:
            self.yaml_output_input.setText(path)

    @Slot()
    def _on_save_yaml(self) -> None:
        """保存 YAML 配置"""
        train_path = self.train_path_input.text().strip()
        val_path = self.val_path_input.text().strip()
        output_path = self.yaml_output_input.text().strip()

        if not train_path or not val_path:
            self.log_message.emit("请先填写训练集和验证集路径")
            return

        if not output_path:
            self.log_message.emit("请选择 YAML 保存路径")
            return

        # 从编辑框获取类别
        classes_text = self.classes_edit.toPlainText().strip()
        classes = [line.strip() for line in classes_text.split("\n") if line.strip()]

        if not classes:
            self.log_message.emit("请填写类别列表")
            return

        success = self._handler.generate_yaml(
            train_path,
            val_path,
            classes,
            Path(output_path),
            message_callback=lambda msg: self.log_message.emit(msg),
        )

        if success:
            self.log_message.emit(f"YAML 配置已保存: {output_path}")
