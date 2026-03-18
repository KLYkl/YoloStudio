"""
_widget.py - DataWidget 主类 (组合所有 Tab Mixin)
============================================
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.data_handler import DataHandler, DataWorker, ScanResult
from ui.collapsible_box import CollapsibleGroupBox
from ui.path_input_group import PathInputGroup
from ui.styled_message_box import StyledProgressDialog

from ui.data_widget._tabs_stats import StatsTabMixin
from ui.data_widget._tabs_edit import EditTabMixin
from ui.data_widget._tabs_augment import AugmentTabMixin
from ui.data_widget._tabs_split import SplitTabMixin
from ui.data_widget._tabs_extract import ExtractTabMixin
from ui.data_widget._tabs_image_check import ImageCheckTabMixin


class DataWidget(
    StatsTabMixin,
    ExtractTabMixin,
    EditTabMixin,
    AugmentTabMixin,
    SplitTabMixin,
    ImageCheckTabMixin,
    QWidget,
):
    """
    数据准备模块主控件

    通过 Mixin 模式组合以下 Tab:
        - StatsTabMixin: 统计 Tab
        - EditTabMixin: 编辑 Tab + 预检查
        - AugmentTabMixin: 增强 Tab
        - SplitTabMixin: 划分 + YAML Tab

    Signals:
        log_message(str): 日志消息，发送到主窗口控制台
    """

    # 日志信号 -> 主窗口控制台
    log_message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # 核心逻辑
        self._handler = DataHandler()
        self._worker: Optional[DataWorker] = None
        self._edit_precheck_cache: Optional[dict] = None
        self._edit_precheck_cache_ttl = 120.0
        self._precheck_dialog: Optional[StyledProgressDialog] = None
        self._precheck_dialog_text = ""
        self._precheck_cancelled = False
        self._pending_precheck_result = None
        self._pending_precheck_handler: Optional[Callable[[object], None]] = None
        self._pending_precheck_cache_key = None
        self._pending_precheck_error: Optional[str] = None
        self._pending_precheck_title = ""

        # Tab 间共享状态
        self.detected_classes: list[str] = []  # Stats -> YAML panel
        self.split_paths: dict = {}             # Split -> YAML panel
        self._stats_overview_labels: dict[str, QLabel] = {}

        # 当前扫描结果
        self._scan_result: Optional[ScanResult] = None

        # 图像检查结果缓存
        self._ic_last_health_result: Optional[dict] = None

        # 应用 QSS 样式
        self._apply_styles()

        # 构建 UI
        self._setup_ui()
        self._connect_signals()

    def _apply_styles(self) -> None:
        """应用语义化样式 (颜色由全局 QSS 主题控制)"""
        pass

    # ============================================================
    # UI 构建
    # ============================================================

    def _setup_ui(self) -> None:
        """构建整体布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # ===== 共享路径面板 (可折叠) =====
        self._path_box = CollapsibleGroupBox("数据源", collapsed=False)
        self.path_group = PathInputGroup(
            show_image_dir=True,
            show_label_dir=True,
            show_classes=True,
            group_title="",  # 标题由 CollapsibleGroupBox 提供
        )
        self._path_box.add_widget(self.path_group)
        main_layout.addWidget(self._path_box)

        # Tab 内容区
        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("subTabWidget")
        self.tab_widget.addTab(self._create_stats_tab(), "📊 统计")
        self.tab_widget.addTab(self._create_extract_tab(), "🎯 抽取")
        self.tab_widget.addTab(self._create_edit_tab(), "✏️ 编辑")
        self.tab_widget.addTab(self._create_augment_tab(), "🧪 增强")
        self.tab_widget.addTab(self._create_split_tab(), "📂 划分")
        self.tab_widget.addTab(self._create_image_check_tab(), "🖼️ 图像检查")
        main_layout.addWidget(self.tab_widget, 1)  # 拉伸因子 = 1

        # 进度条区
        main_layout.addWidget(self._create_progress_zone())

    def _create_progress_zone(self) -> QWidget:
        """创建进度条区域 (进度条 + 状态 + 取消)"""
        zone = QWidget()
        layout = QHBoxLayout(zone)
        layout.setContentsMargins(0, 5, 0, 0)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setValue(0)

        # 状态文本
        self.status_label = QLabel("就绪")
        self.status_label.setFixedWidth(100)
        self.status_label.setObjectName("mutedLabel")

        # 取消按钮
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFixedSize(70, 28)
        self.cancel_btn.setToolTip("取消当前操作")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setProperty("class", "danger")

        layout.addWidget(self.progress_bar, 1)
        layout.addWidget(self.status_label)
        layout.addWidget(self.cancel_btn)

        return zone

    # ============================================================
    # 信号连接
    # ============================================================

    def _connect_signals(self) -> None:
        """连接所有信号与槽"""
        # 共享路径组 → 统一回调
        self.path_group.paths_changed.connect(self._on_paths_changed)
        self.tab_widget.currentChanged.connect(self._on_sub_tab_changed)

        # Tab 1 - 统计
        self.scan_btn.clicked.connect(self._on_scan)

        # Tab 2 - 抽取
        self.ext_mode_group.buttonClicked.connect(lambda: self._on_extract_mode_changed())
        self.ext_scan_dirs_btn.clicked.connect(self._on_ext_scan_dirs)
        self.ext_select_all_btn.clicked.connect(self._on_ext_select_all)
        self.ext_deselect_all_btn.clicked.connect(self._on_ext_deselect_all)
        self.ext_output_browse_btn.clicked.connect(self._on_ext_browse_output)
        self.ext_preview_btn.clicked.connect(self._on_ext_preview)
        self.ext_start_btn.clicked.connect(self._on_ext_start)
        self.ext_scan_categories_btn.clicked.connect(self._on_ext_scan_categories)
        self.ext_cat_select_all_btn.clicked.connect(self._on_ext_cat_select_all)
        self.ext_cat_deselect_all_btn.clicked.connect(self._on_ext_cat_deselect_all)

        # Tab 2 - 编辑
        self.gen_empty_btn.clicked.connect(self._on_generate_empty)
        self.modify_btn.clicked.connect(self._on_modify_labels)
        self.remove_radio.toggled.connect(self._on_action_changed)
        self.convert_btn.clicked.connect(self._on_convert_format)
        self.validate_btn.clicked.connect(self._on_validate_labels)
        self.empty_txt_radio.toggled.connect(self._invalidate_edit_precheck_cache)
        self.empty_xml_radio.toggled.connect(self._invalidate_edit_precheck_cache)
        self.txt_to_xml_radio.toggled.connect(self._invalidate_edit_precheck_cache)
        self.xml_to_txt_radio.toggled.connect(self._invalidate_edit_precheck_cache)
        self.old_name_input.currentTextChanged.connect(self._invalidate_edit_precheck_cache)
        self.new_name_input.currentTextChanged.connect(self._invalidate_edit_precheck_cache)
        self.backup_check.toggled.connect(self._invalidate_edit_precheck_cache)

        # Tab 3 - 增强
        self.augment_output_browse_btn.clicked.connect(self._on_browse_augment_output_dir)
        self.augment_btn.clicked.connect(self._on_augment)
        self.augment_mode_combo.currentIndexChanged.connect(self._on_augment_mode_changed)
        self.augment_fixed_single_check.toggled.connect(self._update_augment_action_states)
        self.augment_fixed_combo_check.toggled.connect(self._update_augment_action_states)
        # 预设方案按钮
        for key, btn in self._preset_buttons.items():
            btn.clicked.connect(lambda _, k=key: self._apply_preset(k))
        self.augment_clear_btn.clicked.connect(self._clear_all_augments)
        # 预览按钮
        self.augment_preview_shuffle_btn.clicked.connect(self._shuffle_preview_image)
        # 增强项 checkbox / spin
        self.augment_hflip_check.toggled.connect(self._update_augment_action_states)
        self.augment_vflip_check.toggled.connect(self._update_augment_action_states)
        self.augment_rotate_check.toggled.connect(self._update_augment_action_states)
        self.augment_rotate_random_radio.toggled.connect(self._update_augment_action_states)
        self.augment_rotate_clockwise_radio.toggled.connect(self._update_augment_action_states)
        self.augment_rotate_counterclockwise_radio.toggled.connect(self._update_augment_action_states)
        self.augment_rotate_degrees_spin.valueChanged.connect(self._update_augment_action_states)
        self.augment_brightness_check.toggled.connect(self._update_augment_action_states)
        self.augment_brightness_spin.valueChanged.connect(self._update_augment_action_states)
        self.augment_contrast_check.toggled.connect(self._update_augment_action_states)
        self.augment_contrast_spin.valueChanged.connect(self._update_augment_action_states)
        self.augment_color_check.toggled.connect(self._update_augment_action_states)
        self.augment_color_spin.valueChanged.connect(self._update_augment_action_states)
        self.augment_noise_check.toggled.connect(self._update_augment_action_states)
        self.augment_noise_spin.valueChanged.connect(self._update_augment_action_states)
        self.augment_hue_check.toggled.connect(self._update_augment_action_states)
        self.augment_hue_spin.valueChanged.connect(self._update_augment_action_states)
        self.augment_sharpness_check.toggled.connect(self._update_augment_action_states)
        self.augment_sharpness_spin.valueChanged.connect(self._update_augment_action_states)
        self.augment_blur_check.toggled.connect(self._update_augment_action_states)
        self.augment_blur_spin.valueChanged.connect(self._update_augment_action_states)

        # Tab 4 - 划分
        self.ratio_slider.valueChanged.connect(self._on_ratio_changed)
        self.output_browse_btn.clicked.connect(self._on_browse_output_dir)
        self.split_btn.clicked.connect(self._on_split)

        # YAML panel browse actions
        self.train_browse_btn.clicked.connect(self._on_browse_train)
        self.val_browse_btn.clicked.connect(self._on_browse_val)
        self.yaml_browse_btn.clicked.connect(self._on_browse_yaml)
        self.save_yaml_btn.clicked.connect(self._on_save_yaml)

        # Tab 6 - 图像检查
        self._connect_image_check_signals()

        # 取消按钮
        self.cancel_btn.clicked.connect(self._on_cancel)

        self._refresh_edit_class_options()
        self._update_edit_action_states()
        self._update_augment_action_states()
        self._update_extract_action_states()
        self._update_image_check_action_states()

    # ============================================================
    # 路径变更回调
    # ============================================================

    def _on_paths_changed(self) -> None:
        """共享路径组变更回调 (替代原 4 个 _sync_paths_from_* 函数)"""
        self._invalidate_edit_precheck_cache()
        self._refresh_edit_class_options()
        self._update_edit_action_states()
        self._update_extract_action_states()
        self._update_augment_action_states()
        self._update_image_check_action_states()
        self._update_path_summary()

        image_dir = self.path_group.get_all_paths().get("image_dir", "")
        self._update_default_output_paths(image_dir)

        # 增强预览: 路径变更时自动加载预览图
        self._try_auto_load_preview()

    def _update_path_summary(self) -> None:
        """更新折叠态的路径摘要文本"""
        paths = self.path_group.get_all_paths()
        img = paths.get("image_dir", "")
        lbl = paths.get("label_dir", "")
        cls = paths.get("classes", "")

        parts = []
        tooltip_parts = []

        if img:
            name = Path(img).name
            parts.append(f"📁 {name}")
            tooltip_parts.append(f"图片目录: {img}")
        else:
            parts.append("📁 未设置")

        if lbl:
            name = Path(lbl).name
            parts.append(f"🏷️ {name}")
            tooltip_parts.append(f"标签目录: {lbl}")
        else:
            parts.append("🏷️ 自动检测")

        if cls:
            name = Path(cls).name
            parts.append(f"📋 {name}")
            tooltip_parts.append(f"类别文件: {cls}")

        self._path_box.set_summary(
            "  ".join(parts),
            "\n".join(tooltip_parts) if tooltip_parts else "",
        )

    def _update_default_output_paths(self, image_dir: str) -> None:
        """根据图片目录推断默认输出路径"""
        if not image_dir:
            return

        img_path = Path(image_dir)
        if not img_path.exists():
            return

        self.output_dir_input.setText(str(img_path.parent / f"{img_path.name}_split"))
        self.augment_output_input.setText(str(img_path.parent / f"{img_path.name}_augmented"))

    def _resolve_dataset_root(
        self,
        image_dir: Path,
        label_dir: Optional[Path] = None,
    ) -> Path:
        """根据图片目录和标签目录推断数据集根目录"""
        if label_dir and label_dir.exists():
            return Path(os.path.commonpath([str(image_dir), str(label_dir)]))

        if image_dir.name.lower() in {"images", "jpegimages", "imgs", "img"}:
            return image_dir.parent

        return image_dir

    # ============================================================
    # Worker 管理 / 进度 / 取消
    # ============================================================

    @Slot(int)
    def _on_sub_tab_changed(self, index: int) -> None:
        """子 Tab 切换时刷新按钮状态"""
        self._update_edit_action_states()
        self._update_augment_action_states()
        self._update_extract_action_states()
        self._update_image_check_action_states()

    @Slot()
    def _on_cancel(self) -> None:
        """取消当前操作"""
        if self._worker and self._worker.isRunning():
            if self._precheck_dialog:
                self._precheck_cancelled = True
            self._worker.request_interrupt()
            self.log_message.emit("正在取消操作...")

    def _start_worker(self, task, on_finished=None) -> None:
        """启动后台工作线程"""
        if self._worker and self._worker.isRunning():
            self.log_message.emit("已有任务在运行中")
            return

        self._worker = DataWorker(self)
        self._worker.set_task(task)

        # 连接信号
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.message.connect(self._emit_message)
        self._worker.error.connect(lambda e: self.log_message.emit(f"错误: {e}"))

        if on_finished:
            self._worker.result_ready.connect(on_finished)

        self._worker.finished.connect(self._on_worker_finished)

        # UI 状态
        self._set_ui_busy(True)

        self._worker.start()

    @Slot(int, int)
    def _on_worker_progress(self, current: int, total: int) -> None:
        """更新进度条"""
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))
            self.status_label.setText(f"{current}/{total}")

    def _emit_progress(self, current: int, total: int) -> None:
        """发射进度信号 (需在主线程中调用)"""
        worker = self._worker
        if worker is not None:
            worker.progress.emit(current, total)

    def _emit_message(self, message: str) -> None:
        """发射消息信号到全局日志面板"""
        self.log_message.emit(message)

    @Slot()
    def _on_worker_finished(self) -> None:
        """工作线程完成"""
        self._set_ui_busy(False)
        worker = self._worker
        self._worker = None
        if worker:
            # 显式断开信号连接，防止 deleteLater 延迟析构期间的信号残留
            try:
                worker.progress.disconnect()
                worker.message.disconnect()
                worker.error.disconnect()
                worker.result_ready.disconnect()
                worker.finished.disconnect()
            except RuntimeError:
                pass  # 已断开则忽略
            worker.deleteLater()

    def _set_ui_busy(self, busy: bool, *, enable_cancel: bool = True) -> None:
        """设置 UI 忙碌状态"""
        self.cancel_btn.setEnabled(busy and enable_cancel)
        self.scan_btn.setEnabled(not busy)
        self.split_btn.setEnabled(not busy)
        self.save_yaml_btn.setEnabled(not busy)

        if busy:
            self.gen_empty_btn.setEnabled(False)
            self.convert_btn.setEnabled(False)
            self.modify_btn.setEnabled(False)
            self.validate_btn.setEnabled(False)
            self.augment_btn.setEnabled(False)
            self.ext_preview_btn.setEnabled(False)
            self.ext_start_btn.setEnabled(False)
            self.ext_scan_dirs_btn.setEnabled(False)
            self.ext_scan_categories_btn.setEnabled(False)
            self.ic_integrity_btn.setEnabled(False)
            self.ic_convert_btn.setEnabled(False)
            self.ic_analyze_btn.setEnabled(False)
            self.ic_duplicate_btn.setEnabled(False)
            self.ic_health_btn.setEnabled(False)
        else:
            self._update_edit_action_states()
            self._update_augment_action_states()
            self._update_extract_action_states()
            self._update_image_check_action_states()

        if not busy:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.status_label.setText("就绪")
