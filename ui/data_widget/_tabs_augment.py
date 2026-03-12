"""
_tabs_augment.py - AugmentTabMixin: 增强 Tab UI + 逻辑
============================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QSizePolicy,
    QFileDialog,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.data_handler import AugmentConfig, AugmentResult
from ui.focus_widgets import FocusDoubleSpinBox, FocusSpinBox
from ui.path_input_group import PathInputGroup


class AugmentTabMixin:
    """增强 Tab 的 UI 构建 + 槽函数"""

    # ==================== UI 构建 ====================

    def _create_augment_tab(self) -> QWidget:
        """Build the augmentation tab."""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setSpacing(10)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        self.augment_path_group = PathInputGroup(
            show_image_dir=True,
            show_label_dir=True,
            show_classes=True,
            group_title="数据源路径",
        )
        tab_layout.addWidget(self.augment_path_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        settings_group = QGroupBox("输出与生成")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(10)

        settings_form = QFormLayout()
        settings_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        settings_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        settings_form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        settings_form.setHorizontalSpacing(12)
        settings_form.setVerticalSpacing(10)

        self.augment_mode_combo = QComboBox()
        self.augment_mode_combo.addItems(["随机生成", "固定生成"])
        settings_form.addRow("生成方式:", self.augment_mode_combo)

        fixed_mode_row = QWidget()
        fixed_mode_layout = QHBoxLayout(fixed_mode_row)
        fixed_mode_layout.setContentsMargins(0, 0, 0, 0)
        fixed_mode_layout.setSpacing(10)
        self.augment_fixed_single_check = QCheckBox("单项覆盖")
        self.augment_fixed_single_check.setChecked(True)
        self.augment_fixed_combo_check = QCheckBox("组合增强")
        self.augment_fixed_combo_check.setChecked(True)
        fixed_mode_layout.addWidget(self.augment_fixed_single_check)
        fixed_mode_layout.addWidget(self.augment_fixed_combo_check)
        fixed_mode_layout.addStretch()
        settings_form.addRow("固定模式:", fixed_mode_row)

        output_row = QWidget()
        output_row_layout = QHBoxLayout(output_row)
        output_row_layout.setContentsMargins(0, 0, 0, 0)
        output_row_layout.setSpacing(8)
        self.augment_output_input = QLineEdit()
        self.augment_output_input.setPlaceholderText("增强结果保存位置...")
        output_row_layout.addWidget(self.augment_output_input, 1)
        self.augment_output_browse_btn = QPushButton("浏览")
        self.augment_output_browse_btn.setFixedWidth(68)
        output_row_layout.addWidget(self.augment_output_browse_btn)
        settings_form.addRow("输出目录:", output_row)

        count_row = QWidget()
        count_row_layout = QHBoxLayout(count_row)
        count_row_layout.setContentsMargins(0, 0, 0, 0)
        count_row_layout.setSpacing(8)
        self.augment_count_spin = FocusSpinBox()
        self.augment_count_spin.setRange(1, 20)
        self.augment_count_spin.setValue(1)
        self.augment_count_spin.setFixedWidth(90)
        count_row_layout.addWidget(self.augment_count_spin)
        self.augment_count_hint = QLabel("份")
        count_row_layout.addWidget(self.augment_count_hint)
        count_row_layout.addStretch()
        settings_form.addRow("每项份数:", count_row)

        seed_row = QWidget()
        seed_row_layout = QHBoxLayout(seed_row)
        seed_row_layout.setContentsMargins(0, 0, 0, 0)
        seed_row_layout.setSpacing(8)
        self.augment_seed_spin = FocusSpinBox()
        self.augment_seed_spin.setRange(0, 99999)
        self.augment_seed_spin.setValue(42)
        self.augment_seed_spin.setFixedWidth(90)
        seed_row_layout.addWidget(self.augment_seed_spin)
        seed_row_layout.addWidget(QLabel("固定后结果可复现"))
        seed_row_layout.addStretch()
        settings_form.addRow("随机种子:", seed_row)

        settings_layout.addLayout(settings_form)
        self.augment_include_original_check = QCheckBox("保留原图到输出目录")
        self.augment_include_original_check.setChecked(True)
        settings_layout.addWidget(self.augment_include_original_check)

        self.augment_mode_hint_label = QLabel()
        self.augment_mode_hint_label.setWordWrap(True)
        self.augment_mode_hint_label.setObjectName("mutedLabel")
        settings_layout.addWidget(self.augment_mode_hint_label)
        content_layout.addWidget(settings_group)

        common_group = QGroupBox("常用增强")
        common_layout = QVBoxLayout(common_group)
        common_layout.setSpacing(10)

        flip_row = QWidget()
        flip_row_layout = QHBoxLayout(flip_row)
        flip_row_layout.setContentsMargins(0, 0, 0, 0)
        flip_row_layout.setSpacing(10)
        flip_row_layout.addWidget(QLabel("翻转:"))
        self.augment_hflip_check = QCheckBox("水平")
        self.augment_vflip_check = QCheckBox("垂直")
        flip_row_layout.addWidget(self.augment_hflip_check)
        flip_row_layout.addWidget(self.augment_vflip_check)
        flip_row_layout.addStretch()
        common_layout.addWidget(flip_row)

        rotate_row = QWidget()
        rotate_row_layout = QHBoxLayout(rotate_row)
        rotate_row_layout.setContentsMargins(0, 0, 0, 0)
        rotate_row_layout.setSpacing(10)
        self.augment_rotate_check = QCheckBox("旋转")
        rotate_row_layout.addWidget(self.augment_rotate_check)
        self.augment_rotate_random_radio = QRadioButton("随机")
        self.augment_rotate_clockwise_radio = QRadioButton("顺时针")
        self.augment_rotate_counterclockwise_radio = QRadioButton("逆时针")
        self.augment_rotate_random_radio.setChecked(True)
        self.augment_rotate_mode_group = QButtonGroup(self)
        self.augment_rotate_mode_group.addButton(self.augment_rotate_random_radio)
        self.augment_rotate_mode_group.addButton(self.augment_rotate_clockwise_radio)
        self.augment_rotate_mode_group.addButton(self.augment_rotate_counterclockwise_radio)
        rotate_row_layout.addWidget(self.augment_rotate_random_radio)
        rotate_row_layout.addWidget(self.augment_rotate_clockwise_radio)
        rotate_row_layout.addWidget(self.augment_rotate_counterclockwise_radio)
        rotate_row_layout.addWidget(QLabel("角度"))
        self.augment_rotate_degrees_spin = FocusDoubleSpinBox()
        self.augment_rotate_degrees_spin.setRange(0.0, 180.0)
        self.augment_rotate_degrees_spin.setValue(15.0)
        self.augment_rotate_degrees_spin.setSingleStep(1.0)
        self.augment_rotate_degrees_spin.setDecimals(1)
        self.augment_rotate_degrees_spin.setFixedWidth(100)
        rotate_row_layout.addWidget(self.augment_rotate_degrees_spin)
        rotate_row_layout.addWidget(QLabel("°"))
        rotate_row_layout.addStretch()
        common_layout.addWidget(rotate_row)

        def add_strength_row(
            title: str,
            check_name: str,
            spin_name: str,
            default_value: float,
            *,
            maximum: float,
            step: float,
            decimals: int = 2,
            suffix_text: str = "幅度 ±",
        ) -> None:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)
            checkbox = QCheckBox(title)
            spin = FocusDoubleSpinBox()
            spin.setRange(0.0, maximum)
            spin.setValue(default_value)
            spin.setSingleStep(step)
            spin.setDecimals(decimals)
            spin.setFixedWidth(100)
            setattr(self, check_name, checkbox)
            setattr(self, spin_name, spin)
            row_layout.addWidget(checkbox)
            row_layout.addWidget(QLabel(suffix_text))
            row_layout.addWidget(spin)
            row_layout.addStretch()
            common_layout.addWidget(row)

        add_strength_row("亮度", "augment_brightness_check", "augment_brightness_spin", 0.20, maximum=1.0, step=0.05)
        add_strength_row("对比度", "augment_contrast_check", "augment_contrast_spin", 0.25, maximum=1.0, step=0.05)
        add_strength_row("饱和度", "augment_color_check", "augment_color_spin", 0.25, maximum=1.0, step=0.05)
        add_strength_row("噪点", "augment_noise_check", "augment_noise_spin", 0.08, maximum=0.50, step=0.01, suffix_text="强度")
        content_layout.addWidget(common_group)

        advanced_group = QGroupBox("高级增强")
        advanced_outer = QVBoxLayout(advanced_group)
        advanced_outer.setSpacing(8)

        self.augment_advanced_toggle = QToolButton()
        self.augment_advanced_toggle.setObjectName("advancedToggle")
        self.augment_advanced_toggle.setText("▼ 展开高级增强")
        self.augment_advanced_toggle.setCheckable(True)
        self.augment_advanced_toggle.setChecked(False)
        self.augment_advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        advanced_outer.addWidget(self.augment_advanced_toggle)

        self.augment_advanced_container = QWidget()
        advanced_layout = QVBoxLayout(self.augment_advanced_container)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(8)

        hue_row = QWidget()
        hue_row_layout = QHBoxLayout(hue_row)
        hue_row_layout.setContentsMargins(0, 0, 0, 0)
        hue_row_layout.setSpacing(10)
        self.augment_hue_check = QCheckBox("色相偏移")
        self.augment_hue_spin = FocusDoubleSpinBox()
        self.augment_hue_spin.setRange(0.0, 45.0)
        self.augment_hue_spin.setValue(12.0)
        self.augment_hue_spin.setSingleStep(1.0)
        self.augment_hue_spin.setDecimals(1)
        self.augment_hue_spin.setFixedWidth(100)
        hue_row_layout.addWidget(self.augment_hue_check)
        hue_row_layout.addWidget(QLabel("最大偏移"))
        hue_row_layout.addWidget(self.augment_hue_spin)
        hue_row_layout.addWidget(QLabel("°"))
        hue_row_layout.addStretch()
        advanced_layout.addWidget(hue_row)

        sharpness_row = QWidget()
        sharpness_row_layout = QHBoxLayout(sharpness_row)
        sharpness_row_layout.setContentsMargins(0, 0, 0, 0)
        sharpness_row_layout.setSpacing(10)
        self.augment_sharpness_check = QCheckBox("锐度")
        self.augment_sharpness_spin = FocusDoubleSpinBox()
        self.augment_sharpness_spin.setRange(0.0, 1.5)
        self.augment_sharpness_spin.setValue(0.40)
        self.augment_sharpness_spin.setSingleStep(0.05)
        self.augment_sharpness_spin.setDecimals(2)
        self.augment_sharpness_spin.setFixedWidth(100)
        sharpness_row_layout.addWidget(self.augment_sharpness_check)
        sharpness_row_layout.addWidget(QLabel("幅度 ±"))
        sharpness_row_layout.addWidget(self.augment_sharpness_spin)
        sharpness_row_layout.addStretch()
        advanced_layout.addWidget(sharpness_row)

        blur_row = QWidget()
        blur_row_layout = QHBoxLayout(blur_row)
        blur_row_layout.setContentsMargins(0, 0, 0, 0)
        blur_row_layout.setSpacing(10)
        self.augment_blur_check = QCheckBox("高斯模糊")
        self.augment_blur_spin = FocusDoubleSpinBox()
        self.augment_blur_spin.setRange(0.0, 10.0)
        self.augment_blur_spin.setValue(1.20)
        self.augment_blur_spin.setSingleStep(0.1)
        self.augment_blur_spin.setDecimals(1)
        self.augment_blur_spin.setFixedWidth(100)
        blur_row_layout.addWidget(self.augment_blur_check)
        blur_row_layout.addWidget(QLabel("最大半径"))
        blur_row_layout.addWidget(self.augment_blur_spin)
        blur_row_layout.addStretch()
        advanced_layout.addWidget(blur_row)

        advanced_tip = QLabel(
            "说明：固定生成会按勾选项稳定导出单项图和组合图；随机生成则按概率抽样，更适合批量扩充。"
        )
        advanced_tip.setWordWrap(True)
        advanced_tip.setObjectName("mutedLabel")
        advanced_layout.addWidget(advanced_tip)

        self.augment_advanced_container.setVisible(False)
        advanced_outer.addWidget(self.augment_advanced_container)
        content_layout.addWidget(advanced_group)

        scroll.setWidget(content)
        tab_layout.addWidget(scroll, 1)

        # 固定底栏: 开始增强按钮 (始终可见, 不随滚动)
        button_row = QHBoxLayout()
        button_row.setContentsMargins(10, 5, 10, 5)
        button_row.addStretch()
        self.augment_btn = QPushButton("🧪 开始增强")
        self.augment_btn.setMinimumHeight(35)
        self.augment_btn.setMinimumWidth(120)
        self.augment_btn.setProperty("class", "primary")
        self.augment_btn.setEnabled(False)
        button_row.addWidget(self.augment_btn)
        tab_layout.addLayout(button_row)

        self._update_augment_mode_controls()
        return tab

    # ==================== 增强状态管理 ====================

    def _update_augment_mode_controls(self) -> None:
        """Refresh mode-specific augmentation controls."""
        is_fixed_mode = self.augment_mode_combo.currentIndex() == 1
        self.augment_fixed_single_check.setEnabled(is_fixed_mode)
        self.augment_fixed_combo_check.setEnabled(is_fixed_mode)
        self.augment_count_hint.setText("份 / 每个方案" if is_fixed_mode else "份 / 每次随机采样")
        self.augment_mode_hint_label.setText(
            "固定生成：按勾选项稳定输出单项图和组合图，适合稀缺类别补样。"
            if is_fixed_mode
            else "随机生成：按启用项随机采样，更适合快速扩充数据量。"
        )

    def _update_augment_action_states(self) -> None:
        """Refresh button and control states for augmentation."""
        img_path = self.augment_path_group.get_image_dir()
        has_image_dir = bool(img_path and img_path.exists())
        is_busy = bool(self._worker and self._worker.isRunning())
        is_fixed_mode = self.augment_mode_combo.currentIndex() == 1

        self._update_augment_mode_controls()

        rotate_enabled = self.augment_rotate_check.isChecked()
        self.augment_rotate_random_radio.setEnabled(rotate_enabled)
        self.augment_rotate_clockwise_radio.setEnabled(rotate_enabled)
        self.augment_rotate_counterclockwise_radio.setEnabled(rotate_enabled)
        self.augment_rotate_degrees_spin.setEnabled(rotate_enabled)

        toggle_pairs = (
            (self.augment_brightness_check, self.augment_brightness_spin),
            (self.augment_contrast_check, self.augment_contrast_spin),
            (self.augment_color_check, self.augment_color_spin),
            (self.augment_noise_check, self.augment_noise_spin),
            (self.augment_hue_check, self.augment_hue_spin),
            (self.augment_sharpness_check, self.augment_sharpness_spin),
            (self.augment_blur_check, self.augment_blur_spin),
        )
        for checkbox, spin in toggle_pairs:
            spin.setEnabled(checkbox.isChecked())

        enabled_operations = [
            self.augment_hflip_check.isChecked(),
            self.augment_vflip_check.isChecked(),
            rotate_enabled and self.augment_rotate_degrees_spin.value() > 0,
            self.augment_brightness_check.isChecked() and self.augment_brightness_spin.value() > 0,
            self.augment_contrast_check.isChecked() and self.augment_contrast_spin.value() > 0,
            self.augment_color_check.isChecked() and self.augment_color_spin.value() > 0,
            self.augment_noise_check.isChecked() and self.augment_noise_spin.value() > 0,
            self.augment_hue_check.isChecked() and self.augment_hue_spin.value() > 0,
            self.augment_sharpness_check.isChecked() and self.augment_sharpness_spin.value() > 0,
            self.augment_blur_check.isChecked() and self.augment_blur_spin.value() > 0,
        ]
        has_operation = any(enabled_operations)
        has_recipe_strategy = True
        if is_fixed_mode:
            has_recipe_strategy = (
                self.augment_fixed_single_check.isChecked()
                or self.augment_fixed_combo_check.isChecked()
            )
        self.augment_btn.setEnabled(
            has_image_dir and has_operation and has_recipe_strategy and not is_busy
        )

    def _resolve_augment_config(self) -> AugmentConfig:
        """Read the augmentation form into a backend config object."""
        if self.augment_rotate_clockwise_radio.isChecked():
            rotate_mode = "clockwise"
        elif self.augment_rotate_counterclockwise_radio.isChecked():
            rotate_mode = "counterclockwise"
        else:
            rotate_mode = "random"

        return AugmentConfig(
            copies_per_image=self.augment_count_spin.value(),
            include_original=self.augment_include_original_check.isChecked(),
            seed=self.augment_seed_spin.value(),
            mode="fixed" if self.augment_mode_combo.currentIndex() == 1 else "random",
            fixed_include_individual=self.augment_fixed_single_check.isChecked(),
            fixed_include_combo=self.augment_fixed_combo_check.isChecked(),
            enable_horizontal_flip=self.augment_hflip_check.isChecked(),
            enable_vertical_flip=self.augment_vflip_check.isChecked(),
            enable_rotate=self.augment_rotate_check.isChecked(),
            rotate_mode=rotate_mode,
            rotate_degrees=self.augment_rotate_degrees_spin.value(),
            enable_brightness=self.augment_brightness_check.isChecked(),
            brightness_strength=self.augment_brightness_spin.value(),
            enable_contrast=self.augment_contrast_check.isChecked(),
            contrast_strength=self.augment_contrast_spin.value(),
            enable_color=self.augment_color_check.isChecked(),
            color_strength=self.augment_color_spin.value(),
            enable_noise=self.augment_noise_check.isChecked(),
            noise_strength=self.augment_noise_spin.value(),
            enable_hue=self.augment_hue_check.isChecked(),
            hue_degrees=self.augment_hue_spin.value(),
            enable_sharpness=self.augment_sharpness_check.isChecked(),
            sharpness_strength=self.augment_sharpness_spin.value(),
            enable_blur=self.augment_blur_check.isChecked(),
            blur_radius=self.augment_blur_spin.value(),
        )

    # ==================== 槽函数 ====================

    @Slot(int)
    def _on_augment_mode_changed(self, index: int) -> None:
        """React to random/fixed mode changes."""
        self._update_augment_action_states()

    @Slot(bool)
    def _toggle_augment_advanced(self, checked: bool) -> None:
        """Show or hide advanced augmentation controls."""
        self.augment_advanced_container.setVisible(checked)
        self.augment_advanced_toggle.setText("▲ 收起高级增强" if checked else "▼ 展开高级增强")

    @Slot()
    def _on_browse_augment_output_dir(self) -> None:
        """选择增强输出目录"""
        path = QFileDialog.getExistingDirectory(self, "选择增强输出目录")
        if path:
            self.augment_output_input.setText(path)

    @Slot()
    def _on_augment(self) -> None:
        """启动数据增强后台任务"""
        img_path = self.augment_path_group.get_image_dir()
        if not img_path:
            self.log_message.emit("请先选择图片目录")
            return

        if not img_path.exists():
            self.log_message.emit(f"图片目录不存在: {img_path}")
            return

        config = self._resolve_augment_config()
        if not config.has_any_operation():
            self.log_message.emit("请至少启用一种增强方式")
            return

        label_path = self.augment_path_group.get_label_dir()
        classes_txt = self.augment_path_group.get_classes_path()
        output_dir = self.augment_output_input.text().strip()
        output_path = Path(output_dir) if output_dir else img_path.parent / f"{img_path.name}_augmented"
        self.augment_output_input.setText(str(output_path))

        self._start_worker(
            lambda: self._handler.augment_dataset(
                img_path,
                config,
                label_dir=label_path,
                output_dir=output_path,
                classes_txt=classes_txt,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_augment_finished,
        )

    def _on_augment_finished(self, result: AugmentResult) -> None:
        """增强完成回调"""
        self.augment_output_input.setText(result.output_dir)
        total_outputs = result.copied_originals + result.augmented_images
        self.log_message.emit(
            f"数据增强完成: 输出 {total_outputs} 张图片，标签 {result.label_files_written} 个"
        )
