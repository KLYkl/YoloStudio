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

        self.ve_estimate_btn = QPushButton("📊 预估帧数")
        self.ve_estimate_btn.setToolTip("快速预估各视频的抽取帧数 (不实际解码)")
        self.ve_start_btn = QPushButton("🚀 开始抽帧")
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
        title = QLabel("🎬 视频列表")
        layout.addWidget(title)

        # TreeWidget - 视频文件列表
        self.ve_video_tree = QTreeWidget()
        self.ve_video_tree.setHeaderLabels(["文件名", "帧数", "FPS", "时长", "大小"])
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

        self.ve_add_files_btn = QPushButton("📄 添加文件")
        self.ve_scan_dir_btn = QPushButton("📁 扫描目录")
        self.ve_select_all_btn = QPushButton("全选")
        self.ve_clear_btn = QPushButton("清空")

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
        mode_group = QGroupBox("抽帧模式")
        mode_layout = QVBoxLayout(mode_group)

        self.ve_interval_radio = QRadioButton("⏭️ 等间隔 (每 N 帧)")
        self.ve_time_radio = QRadioButton("⏱️ 按时间 (每 N 秒)")
        self.ve_scene_radio = QRadioButton("🎬 场景变化检测")
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
        iv_layout.addWidget(QLabel("帧间隔:"))
        self.ve_frame_interval_spin = FocusSpinBox()
        self.ve_frame_interval_spin.setRange(1, 10000)
        self.ve_frame_interval_spin.setValue(30)
        self.ve_frame_interval_spin.setSuffix(" 帧")
        self.ve_frame_interval_spin.setFixedWidth(_SPIN_WIDTH)
        self.ve_frame_interval_spin.setToolTip("每隔 N 帧抽取 1 帧")
        iv_layout.addWidget(self.ve_frame_interval_spin)
        iv_layout.addStretch()

        # -- 按时间参数 --
        self.ve_time_widget = QWidget()
        tv_layout = QHBoxLayout(self.ve_time_widget)
        tv_layout.setContentsMargins(0, 0, 0, 0)
        tv_layout.addWidget(QLabel("时间间隔:"))
        self.ve_time_interval_spin = FocusDoubleSpinBox()
        self.ve_time_interval_spin.setRange(0.1, 600.0)
        self.ve_time_interval_spin.setValue(1.0)
        self.ve_time_interval_spin.setSingleStep(0.5)
        self.ve_time_interval_spin.setSuffix(" 秒")
        self.ve_time_interval_spin.setFixedWidth(_SPIN_WIDTH)
        self.ve_time_interval_spin.setToolTip("每隔 N 秒抽取 1 帧")
        tv_layout.addWidget(self.ve_time_interval_spin)
        tv_layout.addStretch()

        # -- 场景变化参数 --
        self.ve_scene_widget = QWidget()
        sv_layout = QVBoxLayout(self.ve_scene_widget)
        sv_layout.setContentsMargins(0, 0, 0, 0)
        sv_layout.setSpacing(4)

        # HSV 阈值
        hsv_row = QHBoxLayout()
        hsv_row.addWidget(QLabel("HSV 阈值:"))
        self.ve_scene_threshold_spin = FocusDoubleSpinBox()
        self.ve_scene_threshold_spin.setRange(0.01, 1.0)
        self.ve_scene_threshold_spin.setValue(0.4)
        self.ve_scene_threshold_spin.setSingleStep(0.05)
        self.ve_scene_threshold_spin.setFixedWidth(_SPIN_WIDTH)
        self.ve_scene_threshold_spin.setToolTip(
            "HSV 直方图差异阈值 (越小越敏感，推荐 0.3~0.5)"
        )
        hsv_row.addWidget(self.ve_scene_threshold_spin)
        hsv_row.addStretch()
        sv_layout.addLayout(hsv_row)

        # 最小帧间隔 (防抖)
        gap_row = QHBoxLayout()
        gap_row.addWidget(QLabel("最小间隔:"))
        self.ve_min_scene_gap_spin = FocusSpinBox()
        self.ve_min_scene_gap_spin.setRange(1, 1000)
        self.ve_min_scene_gap_spin.setValue(15)
        self.ve_min_scene_gap_spin.setSuffix(" 帧")
        self.ve_min_scene_gap_spin.setFixedWidth(_SPIN_WIDTH)
        self.ve_min_scene_gap_spin.setToolTip("防止短时间内重复检测到场景变化")
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
        dedup_group = QGroupBox("全局去重 (pHash)")
        dedup_layout = QVBoxLayout(dedup_group)
        dedup_layout.setSpacing(4)

        self.ve_dedup_check = QCheckBox("启用 pHash 感知哈希去重")
        self.ve_dedup_check.setChecked(True)
        self.ve_dedup_check.setToolTip("抽帧完成后，用 pHash 移除内容高度相似的帧")
        dedup_layout.addWidget(self.ve_dedup_check)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("汉明距离阈值:"))
        self.ve_dedup_threshold_spin = FocusSpinBox()
        self.ve_dedup_threshold_spin.setRange(0, 64)
        self.ve_dedup_threshold_spin.setValue(8)
        self.ve_dedup_threshold_spin.setFixedWidth(_SPIN_WIDTH)
        self.ve_dedup_threshold_spin.setToolTip(
            "越小越严格 (0=完全相同才去重, 推荐 6~12)"
        )
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
        general_group = QGroupBox("通用参数")
        general_layout = QVBoxLayout(general_group)
        general_layout.setSpacing(4)

        # 最大帧数
        max_row = QHBoxLayout()
        max_row.addWidget(QLabel("最大帧数:"))
        self.ve_max_frames_spin = FocusSpinBox()
        self.ve_max_frames_spin.setRange(0, 999999)
        self.ve_max_frames_spin.setValue(0)
        self.ve_max_frames_spin.setSpecialValueText("不限制")
        self.ve_max_frames_spin.setFixedWidth(_SPIN_WIDTH)
        self.ve_max_frames_spin.setToolTip("每个视频最多抽取的帧数 (0=不限)")
        max_row.addWidget(self.ve_max_frames_spin)
        max_row.addStretch()
        general_layout.addLayout(max_row)

        # 时间范围
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("起始:"))
        self.ve_start_time_spin = FocusDoubleSpinBox()
        self.ve_start_time_spin.setRange(0.0, 36000.0)
        self.ve_start_time_spin.setValue(0.0)
        self.ve_start_time_spin.setSuffix(" 秒")
        self.ve_start_time_spin.setFixedWidth(_SPIN_WIDTH)
        time_row.addWidget(self.ve_start_time_spin)
        time_row.addWidget(QLabel("结束:"))
        self.ve_end_time_spin = FocusDoubleSpinBox()
        self.ve_end_time_spin.setRange(0.0, 36000.0)
        self.ve_end_time_spin.setValue(0.0)
        self.ve_end_time_spin.setSpecialValueText("到末尾")
        self.ve_end_time_spin.setSuffix(" 秒")
        self.ve_end_time_spin.setFixedWidth(_SPIN_WIDTH)
        time_row.addWidget(self.ve_end_time_spin)
        general_layout.addLayout(time_row)

        # 输出格式 + 质量
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("格式:"))
        self.ve_format_combo = FocusComboBox()
        self.ve_format_combo.addItems(["jpg", "png"])
        self.ve_format_combo.setFixedWidth(70)
        format_row.addWidget(self.ve_format_combo)
        format_row.addWidget(QLabel("JPG 质量:"))
        self.ve_jpg_quality_spin = FocusSpinBox()
        self.ve_jpg_quality_spin.setRange(1, 100)
        self.ve_jpg_quality_spin.setValue(95)
        self.ve_jpg_quality_spin.setFixedWidth(_SPIN_WIDTH)
        format_row.addWidget(self.ve_jpg_quality_spin)
        format_row.addStretch()
        general_layout.addLayout(format_row)

        # 文件名前缀
        prefix_row = QHBoxLayout()
        prefix_row.addWidget(QLabel("文件名前缀:"))
        self.ve_prefix_input = QLineEdit()
        self.ve_prefix_input.setPlaceholderText("留空则使用视频文件名")
        prefix_row.addWidget(self.ve_prefix_input)
        general_layout.addLayout(prefix_row)

        # 输出目录
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("输出目录:"))
        self.ve_output_input = QLineEdit()
        self.ve_output_input.setPlaceholderText("留空则自动生成")
        output_row.addWidget(self.ve_output_input)
        self.ve_output_browse_btn = QPushButton("浏览")
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
            "选择视频文件",
            "",
            f"视频文件 ({ext_filter});;所有文件 (*)",
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
            self.log_message.emit(f"已添加 {added} 个视频文件")
        self._update_video_extract_action_states()

    @Slot()
    def _on_ve_scan_dir(self) -> None:
        """扫描目录中的视频"""
        directory = QFileDialog.getExistingDirectory(self, "选择视频目录")
        if not directory:
            return

        video_dir = Path(directory)
        self.log_message.emit(f"正在扫描: {video_dir}")

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
            self.log_message.emit("目录中未发现视频文件")
            return

        total = sum(stats.values())
        self.log_message.emit(f"发现 {total} 个视频")

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
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录")
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
            self.log_message.emit("请先添加并勾选视频文件")
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
                    f"  {vp.name}: ~{est} 帧 "
                    f"({frames} 总帧, {fps:.1f} FPS, {frames / fps:.1f}s)"
                )
            except Exception as e:
                self.log_message.emit(f"  {vp.name}: 预估失败 ({e})")

        self.log_message.emit(f"预估总计: ~{total_estimate} 帧")

    @Slot()
    def _on_ve_start(self) -> None:
        """开始抽帧"""
        video_paths = self._ve_get_checked_videos()
        if not video_paths:
            self.log_message.emit("请先添加并勾选视频文件")
            return

        config = self._ve_collect_config()
        self.log_message.emit(
            f"开始抽帧: {len(video_paths)} 个视频, "
            f"模式={config.mode}, 去重={'开' if config.enable_dedup else '关'}"
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
            self.log_message.emit("抽帧完成 (无数据)")
            return

        summary = f"抽帧完成: {result.final_count} 张图片"
        if result.dedup_removed > 0:
            summary += f" (去重移除 {result.dedup_removed} 张)"

        self.log_message.emit(summary)

        # 详细信息
        detail_lines = [f"输出: {result.output_dir}"]
        detail_lines.append(f"原始抽取: {result.extracted} 帧")
        if result.dedup_removed > 0:
            detail_lines.append(f"去重移除: {result.dedup_removed} 帧")
        detail_lines.append(f"最终保留: {result.final_count} 帧")

        for video_name, count in sorted(result.video_stats.items()):
            detail_lines.append(f"  🎬 {video_name}: {count} 帧")

        StyledMessageBox.information(
            self,
            "视频抽帧完成",
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
