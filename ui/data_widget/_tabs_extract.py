"""
_tabs_extract.py - ExtractTabMixin: 抽取 Tab UI + 逻辑
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
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.data_handler import ExtractConfig, ExtractResult
from ui.focus_widgets import FocusComboBox, FocusDoubleSpinBox, FocusSpinBox
from ui.styled_message_box import StyledMessageBox


class ExtractTabMixin:
    """抽取 Tab 的 UI 构建 + 槽函数"""

    # ==================== UI 构建 ====================

    def _create_extract_tab(self) -> QWidget:
        """
        创建抽取 Tab

        结构:
            顶部: 模式选择 (3 个 RadioButton)
            中部: 左(目录选择/类别选择) + 右(参数设置)
            底部: 预估结果 + 执行按钮
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setSpacing(6)

        # ===== 顶部: 模式选择 =====
        mode_group_box = QGroupBox("抽取模式")
        mode_layout = QHBoxLayout(mode_group_box)

        self.ext_random_radio = QRadioButton("🎲 随机抽取")
        self.ext_category_radio = QRadioButton("🏷️ 按类别抽取")
        self.ext_directory_radio = QRadioButton("📂 按目录抽取")
        self.ext_random_radio.setChecked(True)

        self.ext_mode_group = QButtonGroup(self)
        self.ext_mode_group.addButton(self.ext_random_radio, 0)
        self.ext_mode_group.addButton(self.ext_category_radio, 1)
        self.ext_mode_group.addButton(self.ext_directory_radio, 2)

        mode_layout.addWidget(self.ext_random_radio)
        mode_layout.addWidget(self.ext_category_radio)
        mode_layout.addWidget(self.ext_directory_radio)
        mode_layout.addStretch()
        tab_layout.addWidget(mode_group_box)

        # ===== 中部: 左右分栏 =====
        content_layout = QHBoxLayout()
        content_layout.setSpacing(8)

        # ========== 左侧: 目录/类别选择 ==========
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # --- 目录选择 GroupBox ---
        dir_group = QGroupBox("📁 目录选择")
        dir_group_layout = QVBoxLayout(dir_group)
        dir_group_layout.setContentsMargins(4, 4, 4, 4)

        self.ext_dir_tree = QTreeWidget()
        self.ext_dir_tree.setHeaderLabels(["目录", "图片数量"])
        self.ext_dir_tree.setColumnCount(2)
        self.ext_dir_tree.setAlternatingRowColors(True)
        self.ext_dir_tree.setMinimumHeight(150)
        dir_group_layout.addWidget(self.ext_dir_tree)

        # 目录操作按钮
        dir_btn_layout = QHBoxLayout()
        self.ext_scan_dirs_btn = QPushButton("🔍 扫描目录")
        self.ext_scan_dirs_btn.setToolTip("扫描图片目录，获取子目录及图片数量")
        dir_btn_layout.addWidget(self.ext_scan_dirs_btn)

        self.ext_select_all_btn = QPushButton("全选")
        self.ext_select_all_btn.setFixedWidth(50)
        self.ext_deselect_all_btn = QPushButton("全不选")
        self.ext_deselect_all_btn.setFixedWidth(65)
        dir_btn_layout.addWidget(self.ext_select_all_btn)
        dir_btn_layout.addWidget(self.ext_deselect_all_btn)
        dir_btn_layout.addStretch()
        dir_group_layout.addLayout(dir_btn_layout)

        left_layout.addWidget(dir_group, 1)  # 拉伸因子 = 1，填满左侧

        # --- 类别选择 GroupBox (按类别模式显示) ---
        self.ext_category_group = QGroupBox("🏷️ 类别选择")
        cat_group_layout = QVBoxLayout(self.ext_category_group)
        cat_group_layout.setContentsMargins(4, 4, 4, 4)

        cat_btn_row = QHBoxLayout()
        self.ext_scan_categories_btn = QPushButton("🔍 扫描类别")
        self.ext_scan_categories_btn.setToolTip(
            "扫描标签目录获取类别列表 (也可在统计 Tab 扫描后自动获取)"
        )
        cat_btn_row.addWidget(self.ext_scan_categories_btn)
        cat_btn_row.addStretch()
        cat_group_layout.addLayout(cat_btn_row)

        self.ext_category_list = QListWidget()
        self.ext_category_list.setMinimumHeight(120)
        self.ext_category_list.setToolTip("勾选要提取的类别")
        cat_group_layout.addWidget(self.ext_category_list)

        # 特殊类别勾选
        special_layout = QHBoxLayout()
        self.ext_cat_empty_check = QCheckBox("空标签")
        self.ext_cat_mixed_check = QCheckBox("混合类")
        self.ext_cat_no_label_check = QCheckBox("无标签")
        special_layout.addWidget(self.ext_cat_empty_check)
        special_layout.addWidget(self.ext_cat_mixed_check)
        special_layout.addWidget(self.ext_cat_no_label_check)
        special_layout.addStretch()
        cat_group_layout.addLayout(special_layout)

        self.ext_category_group.setVisible(False)  # 默认隐藏
        left_layout.addWidget(self.ext_category_group)

        left_scroll.setWidget(left_widget)
        content_layout.addWidget(left_scroll, 1)

        # ========== 右侧: 参数设置 ==========
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        param_group = QGroupBox("⚙️ 抽取参数")
        param_layout = QVBoxLayout(param_group)
        param_layout.setSpacing(8)

        # 数量模式
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("模式:"))
        self.ext_count_mode_combo = FocusComboBox()
        self.ext_count_mode_combo.addItems(["按数量", "按比例", "全部"])
        mode_row.addWidget(self.ext_count_mode_combo, 1)
        param_layout.addLayout(mode_row)

        # 数量 (容器)
        self.ext_count_row = QWidget()
        count_row = QHBoxLayout(self.ext_count_row)
        count_row.setContentsMargins(0, 0, 0, 0)
        count_row.addWidget(QLabel("数量:"))
        self.ext_count_spin = FocusSpinBox()
        self.ext_count_spin.setRange(1, 999999)
        self.ext_count_spin.setValue(100)
        count_row.addWidget(self.ext_count_spin, 1)
        param_layout.addWidget(self.ext_count_row)

        # 比例 (容器，默认隐藏)
        self.ext_ratio_row = QWidget()
        ratio_row = QHBoxLayout(self.ext_ratio_row)
        ratio_row.setContentsMargins(0, 0, 0, 0)
        ratio_row.addWidget(QLabel("比例:"))
        self.ext_ratio_spin = FocusDoubleSpinBox()
        self.ext_ratio_spin.setRange(0.01, 1.00)
        self.ext_ratio_spin.setValue(0.10)
        self.ext_ratio_spin.setSingleStep(0.05)
        self.ext_ratio_spin.setDecimals(2)
        ratio_row.addWidget(self.ext_ratio_spin, 1)
        self.ext_ratio_row.setVisible(False)
        param_layout.addWidget(self.ext_ratio_row)

        # 可用图片数标签
        self.ext_available_label = QLabel("可用: -- 张")
        self.ext_available_label.setObjectName("mutedLabel")
        param_layout.addWidget(self.ext_available_label)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        param_layout.addWidget(separator)

        # 选项
        self.ext_keep_structure_check = QCheckBox("保持目录结构")
        self.ext_keep_structure_check.setChecked(True)
        self.ext_keep_structure_check.setToolTip(
            "勾选: 输出保持原始子目录层级\n"
            "取消: 所有文件扁平化到一个目录 (自动加目录前缀)"
        )
        param_layout.addWidget(self.ext_keep_structure_check)

        self.ext_copy_labels_check = QCheckBox("同时复制标签")
        self.ext_copy_labels_check.setChecked(True)
        self.ext_copy_labels_check.setToolTip("提取图片时同时复制对应的标签文件")
        param_layout.addWidget(self.ext_copy_labels_check)

        # 随机种子
        seed_row = QHBoxLayout()
        seed_row.addWidget(QLabel("随机种子:"))
        self.ext_seed_spin = FocusSpinBox()
        self.ext_seed_spin.setRange(0, 99999)
        self.ext_seed_spin.setValue(42)
        self.ext_seed_spin.setFixedWidth(80)
        seed_row.addWidget(self.ext_seed_spin)

        self.ext_seed_check = QCheckBox("启用")
        self.ext_seed_check.setChecked(False)
        self.ext_seed_check.setToolTip("启用后相同种子可复现相同结果")
        seed_row.addWidget(self.ext_seed_check)
        seed_row.addStretch()
        param_layout.addLayout(seed_row)

        # 输出目录
        param_layout.addWidget(QLabel("输出目录:"))
        output_row = QHBoxLayout()
        self.ext_output_input = QLineEdit()
        self.ext_output_input.setPlaceholderText("提取后保存位置")
        output_row.addWidget(self.ext_output_input, 1)
        self.ext_output_browse_btn = QPushButton("浏览")
        self.ext_output_browse_btn.setFixedWidth(60)
        output_row.addWidget(self.ext_output_browse_btn)
        param_layout.addLayout(output_row)

        right_layout.addWidget(param_group, 1)  # 拉伸因子 = 1，填满右侧
        right_scroll.setWidget(right_widget)
        content_layout.addWidget(right_scroll, 1)

        tab_layout.addLayout(content_layout, 1)

        # ===== 底部: 按钮行 =====
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.ext_preview_btn = QPushButton("📊 预估")
        self.ext_preview_btn.setMinimumHeight(28)
        self.ext_preview_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        btn_layout.addWidget(self.ext_preview_btn)

        self.ext_start_btn = QPushButton("🚀 开始抽取")
        self.ext_start_btn.setMinimumHeight(28)
        self.ext_start_btn.setProperty("class", "primary")
        self.ext_start_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        btn_layout.addWidget(self.ext_start_btn)

        tab_layout.addLayout(btn_layout)

        return tab

    # ==================== 状态管理 ====================

    def _update_extract_action_states(self) -> None:
        """根据当前输入状态更新按钮可用性"""
        has_img_dir = bool(self.path_group.get_image_dir())
        has_tree_items = self.ext_dir_tree.topLevelItemCount() > 0

        self.ext_scan_dirs_btn.setEnabled(has_img_dir)
        self.ext_preview_btn.setEnabled(has_img_dir and has_tree_items)
        self.ext_start_btn.setEnabled(has_img_dir and has_tree_items)

    def _on_extract_mode_changed(self) -> None:
        """抽取模式切换时更新 UI"""
        is_category = self.ext_category_radio.isChecked()
        is_directory = self.ext_directory_radio.isChecked()

        # 类别选择面板: 仅按类别模式显示
        self.ext_category_group.setVisible(is_category)

        # 按类别模式: 默认勾选复制标签
        if is_category:
            self.ext_copy_labels_check.setChecked(True)

        # 按目录模式: 隐藏统一数量/比例控件
        if is_directory:
            self.ext_count_row.setVisible(False)
            self.ext_ratio_row.setVisible(False)
        else:
            self._on_count_mode_changed()

        self._update_extract_action_states()

    def _on_count_mode_changed(self) -> None:
        """数量模式切换"""
        idx = self.ext_count_mode_combo.currentIndex()
        is_directory = self.ext_directory_radio.isChecked()

        if is_directory:
            self.ext_count_row.setVisible(False)
            self.ext_ratio_row.setVisible(False)
            return

        # 0=按数量, 1=按比例, 2=全部
        self.ext_count_row.setVisible(idx == 0)
        self.ext_ratio_row.setVisible(idx == 1)

    def _refresh_extract_categories(self) -> None:
        """从扫描结果刷新类别列表"""
        self.ext_category_list.clear()

        if not hasattr(self, "detected_classes") or not self.detected_classes:
            return

        for cls_name in self.detected_classes:
            item = QListWidgetItem(str(cls_name))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.ext_category_list.addItem(item)

    # ==================== 槽函数 ====================

    @Slot()
    def _on_ext_scan_dirs(self) -> None:
        """扫描子目录结构"""
        img_path = self.path_group.get_image_dir()
        if not img_path or not img_path.exists():
            self.log_message.emit("请先选择有效的图片目录")
            return

        self.ext_dir_tree.clear()
        self.log_message.emit("正在扫描目录结构...")

        self._start_worker(
            lambda: self._handler.scan_subdirs(img_path),
            on_finished=self._on_ext_scan_dirs_finished,
        )

    def _on_ext_scan_dirs_finished(self, dir_stats: dict) -> None:
        """扫描目录完成"""
        self.ext_dir_tree.clear()

        if not dir_stats:
            self.log_message.emit("未找到包含图片的目录")
            return

        total_images = 0
        for rel_dir, count in sorted(dir_stats.items()):
            item = QTreeWidgetItem()
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)

            display_name = rel_dir if rel_dir != "." else "(根目录)"
            item.setText(0, display_name)
            item.setText(1, f"{count} 张")
            item.setData(0, Qt.ItemDataRole.UserRole, rel_dir)  # 存储相对路径
            item.setData(1, Qt.ItemDataRole.UserRole, count)    # 存储数量

            self.ext_dir_tree.addTopLevelItem(item)
            total_images += count

        self.ext_dir_tree.resizeColumnToContents(0)
        self.ext_dir_tree.resizeColumnToContents(1)

        self.ext_available_label.setText(f"可用: {total_images} 张")
        self.ext_count_spin.setMaximum(total_images)

        self.log_message.emit(
            f"扫描完成: {len(dir_stats)} 个目录, 共 {total_images} 张图片"
        )
        self._update_extract_action_states()

        # 同步刷新类别列表
        self._refresh_extract_categories()

    @Slot()
    def _on_ext_select_all(self) -> None:
        """全选目录"""
        for i in range(self.ext_dir_tree.topLevelItemCount()):
            self.ext_dir_tree.topLevelItem(i).setCheckState(
                0, Qt.CheckState.Checked
            )

    @Slot()
    def _on_ext_deselect_all(self) -> None:
        """全不选目录"""
        for i in range(self.ext_dir_tree.topLevelItemCount()):
            self.ext_dir_tree.topLevelItem(i).setCheckState(
                0, Qt.CheckState.Unchecked
            )

    @Slot()
    def _on_ext_browse_output(self) -> None:
        """选择输出目录"""
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.ext_output_input.setText(path)

    def _build_extract_config(self) -> Optional[ExtractConfig]:
        """从 UI 构建 ExtractConfig"""
        # 确定模式
        if self.ext_random_radio.isChecked():
            mode = "random"
        elif self.ext_category_radio.isChecked():
            mode = "by_category"
        else:
            mode = "by_directory"

        # 收集选中目录
        selected_dirs = []
        dir_counts: dict[str, int] = {}
        for i in range(self.ext_dir_tree.topLevelItemCount()):
            item = self.ext_dir_tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                rel_dir = item.data(0, Qt.ItemDataRole.UserRole)
                available = item.data(1, Qt.ItemDataRole.UserRole) or 0
                selected_dirs.append(Path(rel_dir))
                dir_counts[rel_dir] = available  # 默认全部

        if not selected_dirs:
            self.log_message.emit("请至少选择一个目录")
            return None

        # 数量模式
        count_mode_idx = self.ext_count_mode_combo.currentIndex()
        count_mode_map = {0: "count", 1: "ratio", 2: "all"}
        count_mode = count_mode_map.get(count_mode_idx, "count")

        # 类别
        categories: list[str] = []
        if mode == "by_category":
            for i in range(self.ext_category_list.count()):
                item = self.ext_category_list.item(i)
                if item.checkState() == Qt.CheckState.Checked:
                    categories.append(item.text())
            if self.ext_cat_empty_check.isChecked():
                categories.append("_empty")
            if self.ext_cat_mixed_check.isChecked():
                categories.append("_mixed")
            if self.ext_cat_no_label_check.isChecked():
                categories.append("_no_label")

            if not categories:
                self.log_message.emit("请至少选择一个类别")
                return None

        # 输出目录
        output_text = self.ext_output_input.text().strip()
        output_dir = Path(output_text) if output_text else None

        # 随机种子
        seed = self.ext_seed_spin.value() if self.ext_seed_check.isChecked() else None

        return ExtractConfig(
            mode=mode,
            count_mode=count_mode,
            count=self.ext_count_spin.value(),
            ratio=self.ext_ratio_spin.value(),
            categories=categories,
            selected_dirs=selected_dirs,
            dir_counts=dir_counts,
            keep_structure=self.ext_keep_structure_check.isChecked(),
            copy_labels=self.ext_copy_labels_check.isChecked(),
            seed=seed,
            output_dir=output_dir,
        )

    @Slot()
    def _on_ext_preview(self) -> None:
        """预估抽取结果"""
        img_path = self.path_group.get_image_dir()
        if not img_path or not img_path.exists():
            self.log_message.emit("请先选择有效的图片目录")
            return

        config = self._build_extract_config()
        if config is None:
            return

        label_path = self.path_group.get_label_dir()
        classes_txt = self.path_group.get_classes_path()

        self.ext_preview_text.clear()
        self.log_message.emit("正在预估...")

        self._start_worker(
            lambda: self._handler.preview_extract(
                img_path,
                label_dir=label_path,
                config=config,
                classes_txt=classes_txt,
                interrupt_check=lambda: self._worker.is_interrupted()
                if self._worker
                else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_ext_preview_finished,
        )

    def _on_ext_preview_finished(self, result: ExtractResult) -> None:
        """预估完成 — 弹窗显示结果"""
        if result.total_available == 0:
            StyledMessageBox.warning(
                self, "预估结果", "未找到符合条件的图片"
            )
            return

        ratio = (
            result.extracted / result.total_available * 100
            if result.total_available > 0
            else 0
        )
        summary = (
            f"预计提取 {result.extracted} / {result.total_available} 张 "
            f"({ratio:.1f}%)"
        )

        detail_lines = []
        for dir_name, count in sorted(result.dir_stats.items()):
            display = dir_name if dir_name != "." else "(根目录)"
            detail_lines.append(f"📂 {display} → {count} 张")

        StyledMessageBox.information(
            self, "预估结果", summary,
            detailed_text="\n".join(detail_lines) if detail_lines else "",
        )
        self.log_message.emit(f"预估完成: {result.extracted} 张")

    @Slot()
    def _on_ext_start(self) -> None:
        """开始抽取"""
        img_path = self.path_group.get_image_dir()
        if not img_path or not img_path.exists():
            self.log_message.emit("请先选择有效的图片目录")
            return

        config = self._build_extract_config()
        if config is None:
            return

        label_path = self.path_group.get_label_dir()
        classes_txt = self.path_group.get_classes_path()

        self.log_message.emit("开始抽取图片...")

        self._start_worker(
            lambda: self._handler.extract_images(
                img_path,
                label_dir=label_path,
                config=config,
                classes_txt=classes_txt,
                interrupt_check=lambda: self._worker.is_interrupted()
                if self._worker
                else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_ext_start_finished,
        )

    def _on_ext_start_finished(self, result: ExtractResult) -> None:
        """抽取完成 — 弹窗显示结果"""
        if result.extracted == 0 and not result.conflicts:
            self.log_message.emit("抽取完成 (无数据)")
            return

        summary = (
            f"提取完成: {result.extracted} 张图片"
            f", {result.labels_copied} 个标签"
        )
        if result.conflicts:
            summary += f"\n⚠️ {len(result.conflicts)} 个文件冲突"

        self.log_message.emit(summary)

        # 详细信息
        detail_lines = [f"输出: {result.output_dir}"]
        for dir_name, count in sorted(result.dir_stats.items()):
            display = dir_name if dir_name != "." else "(根目录)"
            detail_lines.append(f"📂 {display} → {count} 张")

        if result.conflicts:
            detail_lines.append("")
            detail_lines.append(f"⚠️ {len(result.conflicts)} 个文件冲突:")
            for src, dest in result.conflicts[:20]:
                detail_lines.append(f"  {src.name} → {dest}")
            if len(result.conflicts) > 20:
                detail_lines.append(f"  ...还有 {len(result.conflicts) - 20} 个")

        StyledMessageBox.information(
            self, "抽取完成", summary,
            detailed_text="\n".join(detail_lines),
        )

    # ==================== 独立类别扫描 ====================

    @Slot()
    def _on_ext_scan_categories(self) -> None:
        """独立扫描标签目录获取类别列表"""
        img_path = self.path_group.get_image_dir()
        label_path = self.path_group.get_label_dir()
        classes_txt = self.path_group.get_classes_path()

        # 确定搜索目录: 优先 label_dir，其次 img_dir
        search_dir = label_path if (label_path and label_path.exists()) else img_path
        if not search_dir or not search_dir.exists():
            self.log_message.emit("请先选择有效的图片或标签目录")
            return

        self.log_message.emit("正在扫描类别...")

        self._start_worker(
            lambda: self._handler.collect_label_class_options(
                search_dir, classes_txt=classes_txt
            ),
            on_finished=self._on_ext_scan_categories_finished,
        )

    def _on_ext_scan_categories_finished(self, class_list: list) -> None:
        """类别扫描完成"""
        if not class_list:
            self.log_message.emit("未检测到任何类别")
            return

        # 更新共享状态 (同步到编辑 Tab 等)
        self.detected_classes = class_list

        # 刷新类别列表 UI
        self._refresh_extract_categories()

        self.log_message.emit(
            f"扫描到 {len(class_list)} 个类别: {', '.join(str(c) for c in class_list)}"
        )

