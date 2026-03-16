"""
_tabs_image_check.py - ImageCheckTabMixin: 图像检查 Tab UI + 逻辑
============================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.focus_widgets import FocusComboBox, FocusSpinBox

from core.data_handler import (
    ImageCheckResult,
    ImageSizeStats,
    DuplicateGroup,
)
from ui.styled_message_box import StyledMessageBox
from ui.data_widget.image_check_result_dialog import (
    DuplicateResultDialog,
    HealthCheckResultDialog,
    ImageCheckResultDialog,
    SizeAnalysisResultDialog,
)


# ============================================================
# 目标格式选项
# ============================================================

_TARGET_FORMATS = [
    "JPEG (.jpg)",
    "PNG (.png)",
    "BMP (.bmp)",
    "WebP (.webp)",
]

_FORMAT_KEY_MAP = {
    "JPEG (.jpg)": "JPEG",
    "PNG (.png)": "PNG",
    "BMP (.bmp)": "BMP",
    "WebP (.webp)": "WEBP",
}


class ImageCheckTabMixin:
    """图像检查 Tab 的 UI 构建 + 槽函数"""

    # ==================== UI 构建 ====================

    def _create_image_check_tab(self) -> QWidget:
        """
        创建图像检查 Tab (2×2 对称布局 + 底部按钮)

        左上: 图像完整性校验
        右上: 图像格式转换
        左下: 图像尺寸分析
        右下: 重复图片检测
        底部: 一键健康检查 + 导出报告
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        # QScrollArea 包裹主内容
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)

        # 2×2 网格布局
        content_grid = QGridLayout()
        content_grid.setHorizontalSpacing(15)
        content_grid.setVerticalSpacing(10)
        content_grid.setColumnStretch(0, 1)
        content_grid.setColumnStretch(1, 1)

        # ---- GroupBox 1: 图像完整性校验 (左上) ----
        content_grid.addWidget(self._create_integrity_group(), 0, 0)

        # ---- GroupBox 2: 图像格式转换 (右上) ----
        content_grid.addWidget(self._create_convert_image_group(), 0, 1)

        # ---- GroupBox 3: 图像尺寸分析 (左下) ----
        content_grid.addWidget(self._create_size_analysis_group(), 1, 0)

        # ---- GroupBox 4: 重复图片检测 (右下) ----
        content_grid.addWidget(self._create_duplicate_group(), 1, 1)

        scroll_layout.addLayout(content_grid, 0)
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll_content)
        tab_layout.addWidget(scroll_area, 1)

        # 底部按钮栏 (固定在 ScrollArea 外部)
        tab_layout.addWidget(self._create_image_check_bottom_bar())

        return tab

    # ---- 左上: 图像完整性校验 ----
    def _create_integrity_group(self) -> QGroupBox:
        group = QGroupBox("图像完整性校验")
        layout = QVBoxLayout(group)

        self.ic_corrupted_check = QCheckBox("损坏图片检测")
        self.ic_corrupted_check.setChecked(True)
        self.ic_corrupted_check.setToolTip(
            "使用 PIL verify() + load() 双重校验\n检测无法打开或截断的图片"
        )
        layout.addWidget(self.ic_corrupted_check)

        self.ic_zero_bytes_check = QCheckBox("零字节文件检测")
        self.ic_zero_bytes_check.setChecked(True)
        self.ic_zero_bytes_check.setToolTip("检测文件大小为 0 的图片")
        layout.addWidget(self.ic_zero_bytes_check)

        self.ic_format_mismatch_check = QCheckBox("文件头/扩展名不匹配")
        self.ic_format_mismatch_check.setChecked(True)
        self.ic_format_mismatch_check.setToolTip(
            "比对文件头 magic bytes 与扩展名\n"
            "例: .jpg 文件实际是 PNG 格式"
        )
        layout.addWidget(self.ic_format_mismatch_check)

        self.ic_exif_check = QCheckBox("EXIF 旋转标记检查")
        self.ic_exif_check.setChecked(False)
        self.ic_exif_check.setToolTip(
            "检测含有非标准 EXIF Orientation 的图片\n"
            "可能导致训练时图像方向不一致"
        )
        layout.addWidget(self.ic_exif_check)

        # 按钮 (右对齐)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.ic_integrity_btn = QPushButton("🔍 开始校验")
        self.ic_integrity_btn.setMinimumHeight(35)
        self.ic_integrity_btn.setMinimumWidth(120)
        self.ic_integrity_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.ic_integrity_btn.setProperty("class", "primary")
        self.ic_integrity_btn.setEnabled(False)
        btn_layout.addWidget(self.ic_integrity_btn)
        layout.addLayout(btn_layout)

        return group

    # ---- 右上: 图像格式转换 ----
    def _create_convert_image_group(self) -> QGroupBox:
        group = QGroupBox("图像格式转换")
        layout = QVBoxLayout(group)

        # 目标格式
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("目标格式:"))
        self.ic_target_format_combo = FocusComboBox()
        self.ic_target_format_combo.addItems(_TARGET_FORMATS)
        format_row.addWidget(self.ic_target_format_combo, 1)
        layout.addLayout(format_row)

        # 选项
        self.ic_convert_rgb_check = QCheckBox("统一转为 RGB 模式")
        self.ic_convert_rgb_check.setChecked(True)
        self.ic_convert_rgb_check.setToolTip(
            "将 RGBA、灰度、CMYK 等模式统一转为 RGB\n确保训练数据通道一致"
        )
        layout.addWidget(self.ic_convert_rgb_check)

        self.ic_sync_labels_check = QCheckBox("同步重命名标签文件")
        self.ic_sync_labels_check.setChecked(True)
        self.ic_sync_labels_check.setToolTip("转换后同步复制对应的标签文件到输出目录")
        layout.addWidget(self.ic_sync_labels_check)

        # 提示信息
        info_label = QLabel("原始图片保留，转换结果输出到新目录")
        info_label.setObjectName("mutedLabel")
        layout.addWidget(info_label)

        # 按钮 (右对齐)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.ic_convert_btn = QPushButton("🔄 执行转换")
        self.ic_convert_btn.setMinimumHeight(35)
        self.ic_convert_btn.setMinimumWidth(120)
        self.ic_convert_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.ic_convert_btn.setProperty("class", "success")
        self.ic_convert_btn.setEnabled(False)
        btn_layout.addWidget(self.ic_convert_btn)
        layout.addLayout(btn_layout)

        return group

    # ---- 左下: 图像尺寸分析 ----
    def _create_size_analysis_group(self) -> QGroupBox:
        group = QGroupBox("图像尺寸分析")
        layout = QVBoxLayout(group)

        # 统计卡片 (2×2 网格)
        self._ic_size_labels: dict[str, QLabel] = {}

        cards_grid = QGridLayout()
        cards_grid.setHorizontalSpacing(8)
        cards_grid.setVerticalSpacing(8)

        size_items = [
            ("min_size", "最小尺寸", "blue"),
            ("max_size", "最大尺寸", "green"),
            ("avg_size", "平均尺寸", "orange"),
            ("abnormal", "异常图片", "red"),
        ]

        for index, (key, title, accent) in enumerate(size_items):
            card = self._create_ic_stat_card(title, key, accent)
            cards_grid.addWidget(card, index // 2, index % 2)

        layout.addLayout(cards_grid)

        # 按钮 (右对齐)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.ic_analyze_btn = QPushButton("📐 分析尺寸")
        self.ic_analyze_btn.setMinimumHeight(35)
        self.ic_analyze_btn.setMinimumWidth(120)
        self.ic_analyze_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.ic_analyze_btn.setEnabled(False)
        btn_layout.addWidget(self.ic_analyze_btn)
        layout.addLayout(btn_layout)

        return group

    def _create_ic_stat_card(
        self, title: str, key: str, accent_key: str = "blue"
    ) -> QFrame:
        """创建尺寸统计卡片 (仿 Stats Tab 样式)"""
        card = QFrame()
        card.setObjectName("statsOverviewCard")
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        card.setMinimumHeight(62)

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 10, 0)
        card_layout.setSpacing(0)

        # 左侧彩色指示条
        accent_bar = QFrame()
        accent_bar.setObjectName("statsAccentBar")
        accent_bar.setFixedWidth(4)
        accent_bar.setProperty("accent", accent_key)
        card_layout.addWidget(accent_bar)

        # 右侧内容
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(10, 8, 0, 8)
        text_layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("statsCardTitle")

        value_label = QLabel("--")
        value_label.setObjectName("statsCardValue")
        value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        value_label.setProperty("accent", accent_key)

        text_layout.addWidget(title_label)
        text_layout.addWidget(value_label)
        card_layout.addLayout(text_layout)

        self._ic_size_labels[key] = value_label
        return card

    # ---- 右下: 重复图片检测 ----
    def _create_duplicate_group(self) -> QGroupBox:
        group = QGroupBox("重复图片检测")
        layout = QVBoxLayout(group)

        # 检测方法
        self.ic_md5_radio = QRadioButton("MD5 精确匹配")
        self.ic_phash_radio = QRadioButton("感知哈希 (相似图)")
        self.ic_md5_radio.setChecked(True)

        self.ic_dup_method_group = QButtonGroup(self)
        self.ic_dup_method_group.addButton(self.ic_md5_radio, 0)
        self.ic_dup_method_group.addButton(self.ic_phash_radio, 1)

        layout.addWidget(self.ic_md5_radio)
        layout.addWidget(self.ic_phash_radio)

        # 相似阈值
        threshold_row = QHBoxLayout()
        self._ic_threshold_label = QLabel("相似阈值:")
        threshold_row.addWidget(self._ic_threshold_label)
        self.ic_threshold_spin = FocusSpinBox()
        self.ic_threshold_spin.setRange(1, 32)
        self.ic_threshold_spin.setValue(8)
        self.ic_threshold_spin.setToolTip(
            "感知哈希汉明距离阈值\n"
            "值越小匹配越严格 (推荐 5~10)"
        )
        self.ic_threshold_spin.setEnabled(False)
        self._ic_threshold_label.setEnabled(False)
        threshold_row.addWidget(self.ic_threshold_spin)
        threshold_row.addStretch()
        layout.addLayout(threshold_row)

        # 按钮 (右对齐)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.ic_duplicate_btn = QPushButton("🔍 检测重复")
        self.ic_duplicate_btn.setMinimumHeight(35)
        self.ic_duplicate_btn.setMinimumWidth(120)
        self.ic_duplicate_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.ic_duplicate_btn.setProperty("class", "warning")
        self.ic_duplicate_btn.setEnabled(False)
        btn_layout.addWidget(self.ic_duplicate_btn)
        layout.addLayout(btn_layout)

        return group

    # ---- 底部按钮栏 ----
    def _create_image_check_bottom_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 5, 0, 0)

        self.ic_quarantine_check = QCheckBox(
            "异常文件自动隔离到 _quarantine 目录"
        )
        self.ic_quarantine_check.setChecked(False)
        self.ic_quarantine_check.setToolTip(
            "勾选后，完整性校验和重复检测发现的问题文件\n"
            "会被自动移动到图片目录下的 _quarantine 子目录"
        )
        layout.addWidget(self.ic_quarantine_check)

        layout.addStretch()

        self.ic_health_btn = QPushButton("📊 一键健康检查")
        self.ic_health_btn.setMinimumHeight(35)
        self.ic_health_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.ic_health_btn.setProperty("class", "primary")
        self.ic_health_btn.setEnabled(False)
        layout.addWidget(self.ic_health_btn)

        self.ic_export_btn = QPushButton("📄 导出报告")
        self.ic_export_btn.setMinimumHeight(35)
        self.ic_export_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.ic_export_btn.setEnabled(False)
        layout.addWidget(self.ic_export_btn)

        return bar

    # ==================== 信号连接 (由 _widget.py 调用) ====================

    def _connect_image_check_signals(self) -> None:
        """连接图像检查 Tab 的所有信号"""
        self.ic_integrity_btn.clicked.connect(self._on_ic_integrity)
        self.ic_convert_btn.clicked.connect(self._on_ic_convert)
        self.ic_analyze_btn.clicked.connect(self._on_ic_analyze)
        self.ic_duplicate_btn.clicked.connect(self._on_ic_duplicate)
        self.ic_health_btn.clicked.connect(self._on_ic_health_check)
        self.ic_export_btn.clicked.connect(self._on_ic_export_report)

        # 感知哈希 radio → 启用/禁用阈值 spin
        self.ic_phash_radio.toggled.connect(self._on_ic_dup_method_changed)

    def _update_image_check_action_states(self) -> None:
        """根据路径状态更新图像检查按钮"""
        img_path = self.path_group.get_image_dir()
        has_image_dir = bool(img_path and img_path.exists())
        is_busy = bool(self._worker and self._worker.isRunning())
        enabled = has_image_dir and not is_busy

        self.ic_integrity_btn.setEnabled(enabled)
        self.ic_convert_btn.setEnabled(enabled)
        self.ic_analyze_btn.setEnabled(enabled)
        self.ic_duplicate_btn.setEnabled(enabled)
        self.ic_health_btn.setEnabled(enabled)
        # 导出按钮: 有结果时才启用
        has_results = hasattr(self, "_ic_last_health_result") and self._ic_last_health_result is not None
        self.ic_export_btn.setEnabled(has_results and not is_busy)

    # ==================== 槽函数 ====================

    @Slot(bool)
    def _on_ic_dup_method_changed(self, phash_checked: bool) -> None:
        """感知哈希 radio 切换 → 启用/禁用阈值"""
        self.ic_threshold_spin.setEnabled(phash_checked)
        self._ic_threshold_label.setEnabled(phash_checked)

    def _get_ic_quarantine_dir(self) -> Optional[Path]:
        """获取隔离目录 (如果勾选了自动隔离)"""
        if not self.ic_quarantine_check.isChecked():
            return None
        img_path = self.path_group.get_image_dir()
        if not img_path:
            return None
        return img_path.parent / "_quarantine"

    # ---- 完整性校验 ----
    @Slot()
    def _on_ic_integrity(self) -> None:
        """开始图像完整性校验"""
        img_path = self.path_group.get_image_dir()
        if not img_path or not img_path.exists():
            self.log_message.emit("请先选择图片目录")
            return

        # 至少勾选一项
        if not any([
            self.ic_corrupted_check.isChecked(),
            self.ic_zero_bytes_check.isChecked(),
            self.ic_format_mismatch_check.isChecked(),
            self.ic_exif_check.isChecked(),
        ]):
            StyledMessageBox.warning(self, "图像完整性校验", "请至少勾选一项检查内容")
            return

        quarantine_dir = self._get_ic_quarantine_dir()

        self._start_worker(
            lambda: self._handler.check_image_integrity(
                img_path,
                check_corrupted=self.ic_corrupted_check.isChecked(),
                check_zero_bytes=self.ic_zero_bytes_check.isChecked(),
                check_format_mismatch=self.ic_format_mismatch_check.isChecked(),
                check_exif_rotation=self.ic_exif_check.isChecked(),
                quarantine_dir=quarantine_dir,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_ic_integrity_finished,
        )

    def _on_ic_integrity_finished(self, result: ImageCheckResult) -> None:
        """完整性校验完成"""
        # 存储结果以便导出
        if not hasattr(self, "_ic_last_health_result") or self._ic_last_health_result is None:
            self._ic_last_health_result = {}
        self._ic_last_health_result["integrity"] = result
        self._update_image_check_action_states()

        # 使用专用弹窗展示结果
        ImageCheckResultDialog.show_result(self, result)

    # ---- 格式转换 ----
    @Slot()
    def _on_ic_convert(self) -> None:
        """执行图像格式转换"""
        img_path = self.path_group.get_image_dir()
        if not img_path or not img_path.exists():
            self.log_message.emit("请先选择图片目录")
            return

        format_text = self.ic_target_format_combo.currentText()
        target_format = _FORMAT_KEY_MAP.get(format_text, "JPEG")
        label_dir = self.path_group.get_label_dir()

        message = (
            f"将把所有图片转换为 {format_text} 格式。\n"
            "原始图片保留，结果输出到新目录。\n\n"
            "是否继续？"
        )
        if not StyledMessageBox.question(self, "图像格式转换", message):
            return

        self._start_worker(
            lambda: self._handler.convert_image_format(
                img_path,
                target_format=target_format,
                convert_rgb=self.ic_convert_rgb_check.isChecked(),
                sync_labels=self.ic_sync_labels_check.isChecked(),
                label_dir=label_dir,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_ic_convert_finished,
        )

    def _on_ic_convert_finished(self, count: int) -> None:
        """格式转换完成"""
        StyledMessageBox.information(
            self, "图像格式转换",
            f"转换完成: 成功 {count} 张\n\n"
            "结果已保存到新目录 (详见系统日志)",
        )

    # ---- 尺寸分析 ----
    @Slot()
    def _on_ic_analyze(self) -> None:
        """分析图像尺寸"""
        img_path = self.path_group.get_image_dir()
        if not img_path or not img_path.exists():
            self.log_message.emit("请先选择图片目录")
            return

        self._start_worker(
            lambda: self._handler.analyze_image_sizes(
                img_path,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_ic_analyze_finished,
        )

    def _on_ic_analyze_finished(self, result: ImageSizeStats) -> None:
        """尺寸分析完成 → 更新统计卡片 + 弹窗"""
        if not hasattr(self, "_ic_last_health_result") or self._ic_last_health_result is None:
            self._ic_last_health_result = {}
        self._ic_last_health_result["sizes"] = result
        self._update_image_check_action_states()

        if result.total_images == 0:
            StyledMessageBox.information(self, "图像尺寸分析", "未找到图片文件")
            return

        # 更新卡片
        self._ic_size_labels["min_size"].setText(
            f"{result.min_size[0]}×{result.min_size[1]}"
        )
        self._ic_size_labels["max_size"].setText(
            f"{result.max_size[0]}×{result.max_size[1]}"
        )
        self._ic_size_labels["avg_size"].setText(
            f"{result.avg_size[0]}×{result.avg_size[1]}"
        )
        abnormal_count = len(result.abnormal_small) + len(result.abnormal_large)
        self._ic_size_labels["abnormal"].setText(str(abnormal_count))

        # 使用专用弹窗
        SizeAnalysisResultDialog.show_result(self, result)

    # ---- 重复检测 ----
    @Slot()
    def _on_ic_duplicate(self) -> None:
        """检测重复图片"""
        img_path = self.path_group.get_image_dir()
        if not img_path or not img_path.exists():
            self.log_message.emit("请先选择图片目录")
            return

        method = "phash" if self.ic_phash_radio.isChecked() else "md5"
        threshold = self.ic_threshold_spin.value()
        quarantine_dir = self._get_ic_quarantine_dir()

        self._start_worker(
            lambda: self._handler.detect_duplicates(
                img_path,
                method=method,
                hash_threshold=threshold,
                quarantine_dir=quarantine_dir,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_ic_duplicate_finished,
        )

    def _on_ic_duplicate_finished(self, groups: list[DuplicateGroup]) -> None:
        """重复检测完成"""
        if not hasattr(self, "_ic_last_health_result") or self._ic_last_health_result is None:
            self._ic_last_health_result = {}
        self._ic_last_health_result["duplicates"] = groups
        self._update_image_check_action_states()

        # 使用专用弹窗
        DuplicateResultDialog.show_result(self, groups)

    # ---- 一键健康检查 ----
    @Slot()
    def _on_ic_health_check(self) -> None:
        """一键健康检查"""
        img_path = self.path_group.get_image_dir()
        if not img_path or not img_path.exists():
            self.log_message.emit("请先选择图片目录")
            return

        label_dir = self.path_group.get_label_dir()
        quarantine_dir = self._get_ic_quarantine_dir()

        # 重置卡片
        for label in self._ic_size_labels.values():
            label.setText("--")

        self._start_worker(
            lambda: self._handler.run_health_check(
                img_path,
                label_dir=label_dir,
                quarantine_dir=quarantine_dir,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_ic_health_finished,
        )

    def _on_ic_health_finished(self, result: dict) -> None:
        """一键健康检查完成"""
        self._ic_last_health_result = result
        self._update_image_check_action_states()

        # 更新尺寸统计卡片
        sizes: Optional[ImageSizeStats] = result.get("sizes")
        if sizes and sizes.total_images > 0:
            self._ic_size_labels["min_size"].setText(
                f"{sizes.min_size[0]}×{sizes.min_size[1]}"
            )
            self._ic_size_labels["max_size"].setText(
                f"{sizes.max_size[0]}×{sizes.max_size[1]}"
            )
            self._ic_size_labels["avg_size"].setText(
                f"{sizes.avg_size[0]}×{sizes.avg_size[1]}"
            )
            abnormal_count = len(sizes.abnormal_small) + len(sizes.abnormal_large)
            self._ic_size_labels["abnormal"].setText(str(abnormal_count))

        # 使用专用综合报告弹窗
        HealthCheckResultDialog.show_result(
            self,
            integrity=result.get("integrity"),
            sizes=sizes,
            duplicates=result.get("duplicates"),
        )

    # ---- 导出报告 ----
    @Slot()
    def _on_ic_export_report(self) -> None:
        """导出检查报告"""
        if not hasattr(self, "_ic_last_health_result") or not self._ic_last_health_result:
            StyledMessageBox.warning(self, "导出报告", "请先执行检查操作")
            return

        img_path = self.path_group.get_image_dir()
        if not img_path:
            return

        output_path = img_path.parent / "image_check_report.txt"

        result = self._ic_last_health_result
        self._handler.export_check_report(
            output_path,
            integrity=result.get("integrity"),
            sizes=result.get("sizes"),
            duplicates=result.get("duplicates"),
            message_callback=self._emit_message,
        )
        self.log_message.emit(f"报告已导出: {output_path}")
