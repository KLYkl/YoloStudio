"""
_tabs_video_extract.py - VideoExtractTabMixin: 视频抽帧 Tab UI + 逻辑
============================================

支持三种抽帧模式:
    - interval: 按帧间隔抽取
    - time: 按时间间隔抽取
    - scene: 按场景切换抽取 (HSV 直方图)

抽帧后可选 pHash 全局去重。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.focus_widgets import FocusComboBox, FocusDoubleSpinBox, FocusSpinBox

from core.data_handler import VideoExtractConfig, VideoExtractResult
from ui.styled_message_box import StyledMessageBox
from utils.i18n import t

# SpinBox 统一宽度
_SPIN_WIDTH = 100


class VideoExtractTabMixin:
    """视频抽帧 Tab 的 UI 构建 + 槽函数"""

    # ==================== UI 构建 ====================

    def _create_video_extract_tab(self) -> QWidget:
        """
        创建视频抽帧 Tab

        结构:
            左侧: 视频列表 (TreeWidget + 添加/扫描/全选/清空)
            右侧: 抽帧参数 (模式选择 + 动态参数 + 去重 + 通用参数)
            底部: 预估 / 开始按钮
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setSpacing(6)

        # ===== 中部: 左右分栏 =====
        content_layout = QHBoxLayout()
        content_layout.setSpacing(8)

        # ===== 左侧: 视频列表 =====
        left_widget = self._create_ve_video_list_panel()
        content_layout.addWidget(left_widget, 1)

        # ===== 右侧: 抽帧参数 =====
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)

        right_widget = self._create_ve_params_panel()
        right_scroll.setWidget(right_widget)
        content_layout.addWidget(right_scroll, 1)

        tab_layout.addLayout(content_layout, 1)

        # ===== 底部: 按钮行 =====
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.ve_estimate_btn = QPushButton(t("ve_estimate_frames"))
        self.ve_estimate_btn.setToolTip(t("ve_estimate_frames_tooltip"))
        self.ve_start_btn = QPushButton(t("ve_start_extract"))
        self.ve_start_btn.setProperty("class", "primary")
        self.ve_start_btn.setMinimumHeight(36)

        btn_layout.addStretch()
        btn_layout.addWidget(self.ve_estimate_btn)
        btn_layout.addWidget(self.ve_start_btn)

        tab_layout.addLayout(btn_layout)
        return tab

    def _create_ve_video_list_panel(self) -> QWidget:
        """创建左侧视频列表面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 视频列表标题
        title = QLabel(t("ve_video_list"))
        layout.addWidget(title)

        # TreeWidget - 视频文件列表
        self.ve_video_tree = QTreeWidget()
        self.ve_video_tree.setHeaderLabels(
            [t("ve_col_filename"), t("ve_col_frames"), "FPS",
             t("ve_col_duration"), t("ve_col_size")]
        )
        self.ve_video_tree.setAlternatingRowColors(True)
        self.ve_video_tree.setSelectionMode(
            QTreeWidget.SelectionMode.ExtendedSelection
        )
        self.ve_video_tree.setRootIsDecorated(False)
        self.ve_video_tree.header().setStretchLastSection(True)
        # 列宽设置
        self.ve_video_tree.setColumnWidth(0, 200)
        self.ve_video_tree.setColumnWidth(1, 60)
        self.ve_video_tree.setColumnWidth(2, 50)
        self.ve_video_tree.setColumnWidth(3, 70)
        self.ve_video_tree.setColumnWidth(4, 70)
        layout.addWidget(self.ve_video_tree, 1)

        # 操作按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self.ve_add_files_btn = QPushButton(t("ve_add_files"))
        self.ve_scan_dir_btn = QPushButton(t("ve_scan_dir"))
        self.ve_select_all_btn = QPushButton(t("ve_select_all"))
        self.ve_clear_btn = QPushButton(t("ve_clear"))

        btn_row.addWidget(self.ve_add_files_btn)
        btn_row.addWidget(self.ve_scan_dir_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.ve_select_all_btn)
        btn_row.addWidget(self.ve_clear_btn)

        layout.addLayout(btn_row)
        return panel

    def _create_ve_params_panel(self) -> QWidget:
        """创建右侧参数面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ===== 抽帧模式 =====
        mode_group = QGroupBox(t("ve_extract_mode"))
        mode_layout = QVBoxLayout(mode_group)

        self.ve_interval_radio = QRadioButton(t("ve_mode_interval"))
        self.ve_time_radio = QRadioButton(t("ve_mode_time"))
        self.ve_scene_radio = QRadioButton(t("ve_mode_scene"))
        self.ve_interval_radio.setChecked(True)

        self.ve_mode_group = QButtonGroup()
        self.ve_mode_group.addButton(self.ve_interval_radio, 0)
        self.ve_mode_group.addButton(self.ve_time_radio, 1)
        self.ve_mode_group.addButton(self.ve_scene_radio, 2)

        mode_layout.addWidget(self.ve_interval_radio)
        mode_layout.addWidget(self.ve_time_radio)
        mode_layout.addWidget(self.ve_scene_radio)
        layout.addWidget(mode_group)

        # ===== 模式参数 (动态显示) =====
        self.ve_params_stack = QWidget()
        self.ve_params_layout = QVBoxLayout(self.ve_params_stack)
        self.ve_params_layout.setContentsMargins(0, 0, 0, 0)

        # -- 等间隔参数 --
        self.ve_interval_widget = QWidget()
        iv_layout = QHBoxLayout(self.ve_interval_widget)
        iv_layout.setContentsMargins(0, 0, 0, 0)
        iv_layout.addWidget(QLabel(t("ve_frame_interval_label")))
        self.ve_frame_interval_spin = FocusSpinBox()
        self.ve_frame_interval_spin.setRange(1, 10000)
        self.ve_frame_interval_spin.setValue(30)
        self.ve_frame_interval_spin.setSuffix(t("ve_suffix_frames"))
        self.ve_frame_interval_spin.setFixedWidth(_SPIN_WIDTH)
        self.ve_frame_interval_spin.setToolTip(t("ve_frame_interval_tooltip"))
        iv_layout.addWidget(self.ve_frame_interval_spin)
        iv_layout.addStretch()

        # -- 按时间参数 --
        self.ve_time_widget = QWidget()
        tv_layout = QHBoxLayout(self.ve_time_widget)
        tv_layout.setContentsMargins(0, 0, 0, 0)
        tv_layout.addWidget(QLabel(t("ve_time_interval_label")))
        self.ve_time_interval_spin = FocusDoubleSpinBox()
        self.ve_time_interval_spin.setRange(0.1, 600.0)
        self.ve_time_interval_spin.setValue(1.0)
        self.ve_time_interval_spin.setSingleStep(0.5)
        self.ve_time_interval_spin.setSuffix(t("ve_suffix_seconds"))
        self.ve_time_interval_spin.setFixedWidth(_SPIN_WIDTH)
        self.ve_time_interval_spin.setToolTip(t("ve_time_interval_tooltip"))
        tv_layout.addWidget(self.ve_time_interval_spin)
        tv_layout.addStretch()

        # -- 场景变化参数 --
        self.ve_scene_widget = QWidget()
        sv_layout = QVBoxLayout(self.ve_scene_widget)
        sv_layout.setContentsMargins(0, 0, 0, 0)
        sv_layout.setSpacing(4)

        # HSV 阈值
        hsv_row = QHBoxLayout()
        hsv_row.addWidget(QLabel(t("ve_hsv_threshold_label")))
        self.ve_scene_threshold_spin = FocusDoubleSpinBox()
        self.ve_scene_threshold_spin.setRange(0.01, 1.0)
        self.ve_scene_threshold_spin.setValue(0.4)
        self.ve_scene_threshold_spin.setSingleStep(0.05)
        self.ve_scene_threshold_spin.setFixedWidth(_SPIN_WIDTH)
        self.ve_scene_threshold_spin.setToolTip(t("ve_hsv_threshold_tooltip"))
        hsv_row.addWidget(self.ve_scene_threshold_spin)
        hsv_row.addStretch()
        sv_layout.addLayout(hsv_row)

        # 最小帧间隔 (防抖)
        gap_row = QHBoxLayout()
        gap_row.addWidget(QLabel(t("ve_min_gap_label")))
        self.ve_min_scene_gap_spin = FocusSpinBox()
        self.ve_min_scene_gap_spin.setRange(1, 1000)
        self.ve_min_scene_gap_spin.setValue(15)
        self.ve_min_scene_gap_spin.setSuffix(t("ve_suffix_frames"))
        self.ve_min_scene_gap_spin.setFixedWidth(_SPIN_WIDTH)
        self.ve_min_scene_gap_spin.setToolTip(t("ve_min_gap_tooltip"))
        gap_row.addWidget(self.ve_min_scene_gap_spin)
        gap_row.addStretch()
        sv_layout.addLayout(gap_row)

        self.ve_params_layout.addWidget(self.ve_interval_widget)
        self.ve_params_layout.addWidget(self.ve_time_widget)
        self.ve_params_layout.addWidget(self.ve_scene_widget)
        layout.addWidget(self.ve_params_stack)

        # 初始显示等间隔参数
        self.ve_time_widget.setVisible(False)
        self.ve_scene_widget.setVisible(False)

        # ===== 分隔线 =====
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep1)

        # ===== 全局去重 =====
        dedup_group = QGroupBox(t("ve_global_dedup"))
        dedup_layout = QVBoxLayout(dedup_group)
        dedup_layout.setSpacing(4)

        self.ve_dedup_check = QCheckBox(t("ve_enable_phash_dedup"))
        self.ve_dedup_check.setChecked(True)
        self.ve_dedup_check.setToolTip(t("ve_enable_phash_dedup_tooltip"))
        dedup_layout.addWidget(self.ve_dedup_check)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel(t("ve_hamming_threshold_label")))
        self.ve_dedup_threshold_spin = FocusSpinBox()
        self.ve_dedup_threshold_spin.setRange(0, 64)
        self.ve_dedup_threshold_spin.setValue(8)
        self.ve_dedup_threshold_spin.setFixedWidth(_SPIN_WIDTH)
        self.ve_dedup_threshold_spin.setToolTip(t("ve_hamming_threshold_tooltip"))
        threshold_row.addWidget(self.ve_dedup_threshold_spin)
        threshold_row.addStretch()
        dedup_layout.addLayout(threshold_row)

        layout.addWidget(dedup_group)

        # ===== 分隔线 =====
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep2)

        # ===== 通用参数 =====
        general_group = QGroupBox(t("ve_general_params"))
        general_layout = QVBoxLayout(general_group)
        general_layout.setSpacing(4)

        # 最大帧数
        max_row = QHBoxLayout()
        max_row.addWidget(QLabel(t("ve_max_frames_label")))
        self.ve_max_frames_spin = FocusSpinBox()
        self.ve_max_frames_spin.setRange(0, 999999)
        self.ve_max_frames_spin.setValue(0)
        self.ve_max_frames_spin.setSpecialValueText(t("ve_no_limit"))
        self.ve_max_frames_spin.setFixedWidth(_SPIN_WIDTH)
        self.ve_max_frames_spin.setToolTip(t("ve_max_frames_tooltip"))
        max_row.addWidget(self.ve_max_frames_spin)
        max_row.addStretch()
        general_layout.addLayout(max_row)

        # 时间范围
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel(t("ve_start_time_label")))
        self.ve_start_time_spin = FocusDoubleSpinBox()
        self.ve_start_time_spin.setRange(0.0, 36000.0)
        self.ve_start_time_spin.setValue(0.0)
        self.ve_start_time_spin.setSuffix(t("ve_suffix_seconds"))
        self.ve_start_time_spin.setFixedWidth(_SPIN_WIDTH)
        time_row.addWidget(self.ve_start_time_spin)
        time_row.addWidget(QLabel(t("ve_end_time_label")))
        self.ve_end_time_spin = FocusDoubleSpinBox()
        self.ve_end_time_spin.setRange(0.0, 36000.0)
        self.ve_end_time_spin.setValue(0.0)
        self.ve_end_time_spin.setSpecialValueText(t("ve_to_end"))
        self.ve_end_time_spin.setSuffix(t("ve_suffix_seconds"))
        self.ve_end_time_spin.setFixedWidth(_SPIN_WIDTH)
        time_row.addWidget(self.ve_end_time_spin)
        general_layout.addLayout(time_row)

        # 输出格式 + 质量
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel(t("ve_format_label")))
        self.ve_format_combo = FocusComboBox()
        self.ve_format_combo.addItems(["jpg", "png"])
        self.ve_format_combo.setFixedWidth(70)
        format_row.addWidget(self.ve_format_combo)
        format_row.addWidget(QLabel(t("ve_jpg_quality_label")))
        self.ve_jpg_quality_spin = FocusSpinBox()
        self.ve_jpg_quality_spin.setRange(1, 100)
        self.ve_jpg_quality_spin.setValue(95)
        self.ve_jpg_quality_spin.setFixedWidth(_SPIN_WIDTH)
        format_row.addWidget(self.ve_jpg_quality_spin)
        format_row.addStretch()
        general_layout.addLayout(format_row)

        # 文件名前缀
        prefix_row = QHBoxLayout()
        prefix_row.addWidget(QLabel(t("ve_filename_prefix_label")))
        self.ve_prefix_input = QLineEdit()
        self.ve_prefix_input.setPlaceholderText(t("ve_prefix_placeholder"))
        prefix_row.addWidget(self.ve_prefix_input)
        general_layout.addLayout(prefix_row)

        # 输出目录
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel(t("ve_output_dir_label")))
        self.ve_output_input = QLineEdit()
        self.ve_output_input.setPlaceholderText(t("ve_output_placeholder"))
        output_row.addWidget(self.ve_output_input)
        self.ve_output_browse_btn = QPushButton(t("ve_browse"))
        self.ve_output_browse_btn.setFixedWidth(60)
        output_row.addWidget(self.ve_output_browse_btn)
        general_layout.addLayout(output_row)

        layout.addWidget(general_group)
        layout.addStretch()

        return panel

    # ==================== 槽函数 ====================

    @Slot()
    def _on_ve_mode_changed(self) -> None:
        """抽帧模式切换 → 显示对应参数组"""
        mode_id = self.ve_mode_group.checkedId()
        self.ve_interval_widget.setVisible(mode_id == 0)
        self.ve_time_widget.setVisible(mode_id == 1)
        self.ve_scene_widget.setVisible(mode_id == 2)

    @Slot()
    def _on_ve_add_files(self) -> None:
        """添加视频文件"""
        from utils.constants import VIDEO_EXTENSIONS

        ext_filter = " ".join(f"*{e}" for e in sorted(VIDEO_EXTENSIONS))
        files, _ = QFileDialog.getOpenFileNames(
            self,
            t("ve_select_video_files"),
            "",
            f"{t('ve_video_files_filter')} ({ext_filter});;{t('ve_all_files_filter')} (*)",
        )
        if not files:
            return

        added = 0
        for f in files:
            path = Path(f)
            if self._ve_is_video_in_tree(path):
                continue
            self._ve_add_video_to_tree(path)
            added += 1

        if added > 0:
            self.log_message.emit(t("ve_added_n_videos").format(n=added))
        self._update_video_extract_action_states()

    @Slot()
    def _on_ve_scan_dir(self) -> None:
        """扫描目录中的视频"""
        directory = QFileDialog.getExistingDirectory(self, t("ve_select_video_dir"))
        if not directory:
            return

        video_dir = Path(directory)
        self.log_message.emit(t("ve_scanning").format(path=video_dir))

        self._start_worker(
            lambda: self._handler.scan_videos(video_dir),
            on_finished=lambda result: self._on_ve_scan_dir_finished(
                video_dir, result
            ),
        )

    def _on_ve_scan_dir_finished(
        self, video_dir: Path, stats: dict[str, int]
    ) -> None:
        """扫描完成 → 添加到列表"""
        if not stats:
            self.log_message.emit(t("ve_no_videos_found"))
            return

        total = sum(stats.values())
        self.log_message.emit(t("ve_found_n_videos").format(n=total))

        # 收集所有视频文件并用元数据添加到树
        from utils.constants import VIDEO_EXTENSIONS

        for path in sorted(video_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                if not self._ve_is_video_in_tree(path):
                    self._ve_add_video_to_tree(path)

        self._update_video_extract_action_states()

    @Slot()
    def _on_ve_select_all(self) -> None:
        """全选视频"""
        for i in range(self.ve_video_tree.topLevelItemCount()):
            item = self.ve_video_tree.topLevelItem(i)
            if item:
                item.setCheckState(0, Qt.CheckState.Checked)

    @Slot()
    def _on_ve_clear(self) -> None:
        """清空视频列表"""
        self.ve_video_tree.clear()
        self._update_video_extract_action_states()

    @Slot()
    def _on_ve_browse_output(self) -> None:
        """选择输出目录"""
        directory = QFileDialog.getExistingDirectory(self, t("ve_select_output_dir"))
        if directory:
            self.ve_output_input.setText(directory)

    @Slot()
    def _on_ve_dedup_toggled(self) -> None:
        """去重开关变更"""
        enabled = self.ve_dedup_check.isChecked()
        self.ve_dedup_threshold_spin.setEnabled(enabled)

    @Slot()
    def _on_ve_estimate(self) -> None:
        """预估帧数 (快速计算不实际解码)"""
        video_paths = self._ve_get_checked_videos()
        if not video_paths:
            self.log_message.emit(t("ve_please_add_videos"))
            return

        config = self._ve_collect_config()
        total_estimate = 0

        for vp in video_paths:
            try:
                import cv2

                cap = cv2.VideoCapture(str(vp))
                if not cap.isOpened():
                    continue
                frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                cap.release()

                if config.mode == "interval":
                    est = max(1, frames // config.frame_interval)
                elif config.mode == "time":
                    duration = frames / fps if fps > 0 else 0
                    est = max(1, int(duration / config.time_interval))
                else:
                    est = max(1, frames // 30)  # 场景模式粗略估计

                total_estimate += est
                self.log_message.emit(
                    t("ve_estimate_line").format(
                        name=vp.name, est=est, frames=frames,
                        fps=f"{fps:.1f}", duration=f"{frames / fps:.1f}",
                    )
                )
            except Exception as e:
                self.log_message.emit(
                    t("ve_estimate_failed").format(name=vp.name, error=e)
                )

        self.log_message.emit(t("ve_estimate_total").format(n=total_estimate))

    @Slot()
    def _on_ve_start(self) -> None:
        """开始抽帧"""
        video_paths = self._ve_get_checked_videos()
        if not video_paths:
            self.log_message.emit(t("ve_please_add_videos"))
            return

        config = self._ve_collect_config()
        dedup_status = t("ve_dedup_on") if config.enable_dedup else t("ve_dedup_off")
        self.log_message.emit(
            t("ve_start_extract_log").format(
                n=len(video_paths), mode=config.mode, dedup=dedup_status,
            )
        )

        # 为每个视频单独调用 extract_video_frames，使用第一个视频路径所在目录
        # 也可以传入单个视频路径（Mixin 支持单文件和目录两种输入）
        if len(video_paths) == 1:
            source = video_paths[0]
        else:
            # 多视频: 传第一个视频的目录
            source = video_paths[0].parent

        self._start_worker(
            lambda: self._handler.extract_video_frames(
                source,
                config,
                interrupt_check=lambda: self._worker.is_interrupted()
                if self._worker
                else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_ve_start_finished,
        )

    def _on_ve_start_finished(self, result: VideoExtractResult) -> None:
        """抽帧完成 — 弹窗显示结果"""
        if result.final_count == 0:
            self.log_message.emit(t("ve_extract_done_no_data"))
            return

        summary = t("ve_extract_complete").format(n=result.final_count)
        if result.dedup_removed > 0:
            summary += t("ve_dedup_removed_suffix").format(n=result.dedup_removed)

        self.log_message.emit(summary)

        # 详细信息
        detail_lines = [t("ve_detail_output").format(path=result.output_dir)]
        detail_lines.append(t("ve_detail_raw_extracted").format(n=result.extracted))
        if result.dedup_removed > 0:
            detail_lines.append(t("ve_detail_dedup_removed").format(n=result.dedup_removed))
        detail_lines.append(t("ve_detail_final_kept").format(n=result.final_count))

        for video_name, count in sorted(result.video_stats.items()):
            detail_lines.append(
                t("ve_detail_video_stat").format(name=video_name, count=count)
            )

        StyledMessageBox.information(
            self,
            t("ve_extract_done_title"),
            summary,
            detailed_text="\n".join(detail_lines),
        )

    # ==================== 辅助方法 ====================

    def _ve_collect_config(self) -> VideoExtractConfig:
        """从 UI 控件收集配置"""
        mode_id = self.ve_mode_group.checkedId()
        mode = ["interval", "time", "scene"][mode_id]

        output_dir: Optional[Path] = None
        output_text = self.ve_output_input.text().strip()
        if output_text:
            output_dir = Path(output_text)

        return VideoExtractConfig(
            mode=mode,
            frame_interval=self.ve_frame_interval_spin.value(),
            time_interval=self.ve_time_interval_spin.value(),
            scene_threshold=self.ve_scene_threshold_spin.value(),
            min_scene_gap=self.ve_min_scene_gap_spin.value(),
            enable_dedup=self.ve_dedup_check.isChecked(),
            dedup_threshold=self.ve_dedup_threshold_spin.value(),
            max_frames=self.ve_max_frames_spin.value(),
            start_time=self.ve_start_time_spin.value(),
            end_time=self.ve_end_time_spin.value(),
            output_format=self.ve_format_combo.currentText(),
            jpg_quality=self.ve_jpg_quality_spin.value(),
            name_prefix=self.ve_prefix_input.text().strip(),
            output_dir=output_dir,
        )

    def _ve_get_checked_videos(self) -> list[Path]:
        """获取所有勾选的视频路径"""
        paths: list[Path] = []
        for i in range(self.ve_video_tree.topLevelItemCount()):
            item = self.ve_video_tree.topLevelItem(i)
            if item and item.checkState(0) == Qt.CheckState.Checked:
                path_str = item.data(0, Qt.ItemDataRole.UserRole)
                if path_str:
                    paths.append(Path(path_str))
        return paths

    def _ve_is_video_in_tree(self, path: Path) -> bool:
        """检查路径是否已在树中"""
        path_str = str(path)
        for i in range(self.ve_video_tree.topLevelItemCount()):
            item = self.ve_video_tree.topLevelItem(i)
            if item and item.data(0, Qt.ItemDataRole.UserRole) == path_str:
                return True
        return False

    def _ve_add_video_to_tree(self, path: Path) -> None:
        """将视频添加到树 (尝试读取元信息)"""
        item = QTreeWidgetItem()
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked)
        item.setText(0, path.name)
        item.setData(0, Qt.ItemDataRole.UserRole, str(path))

        # 尝试读取视频元信息
        try:
            import cv2

            cap = cv2.VideoCapture(str(path))
            if cap.isOpened():
                frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
                duration = frames / fps if fps > 0 else 0.0
                size_mb = path.stat().st_size / (1024 * 1024)

                item.setText(1, str(frames))
                item.setText(2, f"{fps:.1f}")
                item.setText(3, f"{duration:.1f}s")
                item.setText(4, f"{size_mb:.1f}MB")
                cap.release()
        except Exception:
            item.setText(1, "?")
            item.setText(2, "?")
            item.setText(3, "?")
            item.setText(4, f"{path.stat().st_size / (1024 * 1024):.1f}MB")

        self.ve_video_tree.addTopLevelItem(item)

    def _update_video_extract_action_states(self) -> None:
        """更新视频抽帧相关按钮的可用状态"""
        has_videos = self.ve_video_tree.topLevelItemCount() > 0
        has_checked = len(self._ve_get_checked_videos()) > 0

        self.ve_estimate_btn.setEnabled(has_checked)
        self.ve_start_btn.setEnabled(has_checked)
        self.ve_select_all_btn.setEnabled(has_videos)
        self.ve_clear_btn.setEnabled(has_videos)
