"""
_tabs_extract.py - ExtractTabMixin: 抽取 Tab UI + 逻辑
============================================

重构版：
    - 两种主模式: 按类别 / 按目录
    - 每个类别/目录独立控制提取方式和数量
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
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
    QSpinBox,
    QDoubleSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.data_handler import ExtractConfig, ExtractResult
from ui.focus_widgets import FocusSpinBox
from ui.styled_message_box import StyledMessageBox


class ExtractTabMixin:
    """抽取 Tab 的 UI 构建 + 槽函数"""

    # ==================== UI 构建 ====================

    def _create_extract_tab(self) -> QWidget:
        """
        创建抽取 Tab

        结构:
            顶部: 模式选择 (2 个 RadioButton)
            中部: 左(目录选择 OR 类别选择) + 右(参数设置)
            底部: 按钮行
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setSpacing(6)

        # ===== 顶部: 模式选择 =====
        mode_group_box = QGroupBox("抽取模式")
        mode_layout = QHBoxLayout(mode_group_box)

        self.ext_category_radio = QRadioButton("🏷️ 按类别抽取")
        self.ext_directory_radio = QRadioButton("📂 按目录抽取")
        self.ext_category_radio.setChecked(True)

        self.ext_mode_group = QButtonGroup(self)
        self.ext_mode_group.addButton(self.ext_category_radio, 0)
        self.ext_mode_group.addButton(self.ext_directory_radio, 1)

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
        self.ext_dir_group = QGroupBox("📁 目录选择")
        dir_group_layout = QVBoxLayout(self.ext_dir_group)
        dir_group_layout.setContentsMargins(4, 4, 4, 4)

        self.ext_dir_tree = QTreeWidget()
        self.ext_dir_tree.setHeaderLabels(["目录", "图片数量", "提取方式", "数量/比例"])
        self.ext_dir_tree.setColumnCount(4)
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

        self.ext_dir_group.setVisible(False)  # 默认隐藏 (默认按类别模式)
        left_layout.addWidget(self.ext_dir_group, 1)

        # --- 类别选择 GroupBox ---
        self.ext_category_group = QGroupBox("🏷️ 类别选择")
        cat_group_layout = QVBoxLayout(self.ext_category_group)
        cat_group_layout.setContentsMargins(4, 4, 4, 4)

        self.ext_category_tree = QTreeWidget()
        self.ext_category_tree.setHeaderLabels(["类别", "可用", "提取方式", "数量/比例"])
        self.ext_category_tree.setColumnCount(4)
        self.ext_category_tree.setAlternatingRowColors(True)
        self.ext_category_tree.setMinimumHeight(120)
        cat_group_layout.addWidget(self.ext_category_tree)

        # 类别操作按钮
        cat_btn_layout = QHBoxLayout()
        self.ext_scan_categories_btn = QPushButton("🔍 扫描类别")
        self.ext_scan_categories_btn.setToolTip(
            "扫描标签目录获取类别列表 (也可在统计 Tab 扫描后自动获取)"
        )
        cat_btn_layout.addWidget(self.ext_scan_categories_btn)

        self.ext_cat_select_all_btn = QPushButton("全选")
        self.ext_cat_select_all_btn.setFixedWidth(50)
        self.ext_cat_deselect_all_btn = QPushButton("全不选")
        self.ext_cat_deselect_all_btn.setFixedWidth(65)
        cat_btn_layout.addWidget(self.ext_cat_select_all_btn)
        cat_btn_layout.addWidget(self.ext_cat_deselect_all_btn)
        cat_btn_layout.addStretch()
        cat_group_layout.addLayout(cat_btn_layout)

        left_layout.addWidget(self.ext_category_group, 1)

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

        # 输出布局选项 (3 个 RadioButton)
        layout_label = QLabel("输出布局:")
        param_layout.addWidget(layout_label)

        self.ext_layout_keep_radio = QRadioButton("保持目录结构")
        self.ext_layout_keep_radio.setChecked(True)
        self.ext_layout_keep_radio.setToolTip(
            "输出保持原始子目录层级"
        )
        self.ext_layout_flat_radio = QRadioButton("扁平化")
        self.ext_layout_flat_radio.setToolTip(
            "所有文件扁平化到 images/labels 目录 (自动加目录前缀去重)"
        )
        self.ext_layout_category_radio = QRadioButton("按类别放置")
        self.ext_layout_category_radio.setToolTip(
            "按类别分子目录存放 (仅按类别抽取模式可用)"
        )

        self.ext_layout_group = QButtonGroup(self)
        self.ext_layout_group.addButton(self.ext_layout_keep_radio, 0)
        self.ext_layout_group.addButton(self.ext_layout_flat_radio, 1)
        self.ext_layout_group.addButton(self.ext_layout_category_radio, 2)

        param_layout.addWidget(self.ext_layout_keep_radio)
        param_layout.addWidget(self.ext_layout_flat_radio)
        param_layout.addWidget(self.ext_layout_category_radio)

        self.ext_copy_labels_check = QCheckBox("同时复制标签")
        self.ext_copy_labels_check.setChecked(True)
        self.ext_copy_labels_check.setToolTip("提取图片时同时复制对应的标签文件")
        param_layout.addWidget(self.ext_copy_labels_check)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        param_layout.addWidget(separator)

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

        param_layout.addStretch()

        right_layout.addWidget(param_group, 1)
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

    # ==================== 行内控件创建 ====================

    def _create_extract_mode_combo(self) -> QComboBox:
        """创建提取方式 ComboBox (全部 / 按数量 / 按比例)"""
        combo = QComboBox()
        combo.addItems(["全部", "按数量", "按比例"])
        combo.setFixedWidth(80)
        return combo

    def _create_extract_count_spin(self) -> QSpinBox:
        """创建数量 SpinBox"""
        spin = QSpinBox()
        spin.setRange(1, 999999)
        spin.setValue(100)
        spin.setFixedWidth(80)
        return spin

    def _create_extract_ratio_spin(self) -> QDoubleSpinBox:
        """创建比例 DoubleSpinBox"""
        spin = QDoubleSpinBox()
        spin.setRange(0.01, 1.00)
        spin.setValue(0.10)
        spin.setSingleStep(0.05)
        spin.setDecimals(2)
        spin.setFixedWidth(80)
        return spin

    def _setup_row_widgets(
        self, tree: QTreeWidget, item: QTreeWidgetItem, available: int
    ) -> None:
        """为 TreeWidget 的一行设置内嵌控件 (ComboBox + SpinBox)"""
        combo = self._create_extract_mode_combo()
        count_spin = self._create_extract_count_spin()
        count_spin.setMaximum(available)
        count_spin.setValue(min(100, available))
        ratio_spin = self._create_extract_ratio_spin()

        # 容器：用 QWidget 包含 count_spin 和 ratio_spin 的堆叠
        value_container = QWidget()
        value_layout = QHBoxLayout(value_container)
        value_layout.setContentsMargins(0, 0, 0, 0)
        value_layout.addWidget(count_spin)
        value_layout.addWidget(ratio_spin)
        ratio_spin.setVisible(False)

        # 默认: 全部模式，隐藏数量控件
        count_spin.setVisible(False)

        def on_mode_changed(idx: int) -> None:
            # 0=全部, 1=按数量, 2=按比例
            count_spin.setVisible(idx == 1)
            ratio_spin.setVisible(idx == 2)

        combo.currentIndexChanged.connect(on_mode_changed)

        tree.setItemWidget(item, 2, combo)
        tree.setItemWidget(item, 3, value_container)

        # 存储控件引用到 item 的 UserRole data
        item.setData(2, Qt.ItemDataRole.UserRole, combo)
        item.setData(3, Qt.ItemDataRole.UserRole, (count_spin, ratio_spin))

    def _read_row_config(
        self, item: QTreeWidgetItem
    ) -> Optional[tuple[str, float]]:
        """读取一行的提取配置: (模式, 值) 或 None (未勾选)"""
        if item.checkState(0) != Qt.CheckState.Checked:
            return None

        combo = item.data(2, Qt.ItemDataRole.UserRole)
        spins = item.data(3, Qt.ItemDataRole.UserRole)
        if not combo or not spins:
            return ("all", 0)

        count_spin, ratio_spin = spins
        idx = combo.currentIndex()

        if idx == 0:  # 全部
            return ("all", 0)
        elif idx == 1:  # 按数量
            return ("count", count_spin.value())
        else:  # 按比例
            return ("ratio", ratio_spin.value())

    # ==================== 状态管理 ====================

    def _update_extract_action_states(self) -> None:
        """根据当前输入状态更新按钮可用性"""
        has_img_dir = bool(self.path_group.get_image_dir())
        has_label_dir = bool(self.path_group.get_label_dir())
        is_category = self.ext_category_radio.isChecked()

        if is_category:
            has_items = self.ext_category_tree.topLevelItemCount() > 0
        else:
            has_items = self.ext_dir_tree.topLevelItemCount() > 0

        self.ext_scan_dirs_btn.setEnabled(has_img_dir)
        self.ext_scan_categories_btn.setEnabled(has_img_dir or has_label_dir)
        self.ext_preview_btn.setEnabled(has_img_dir and has_items)
        self.ext_start_btn.setEnabled(has_img_dir and has_items)

    def _on_extract_mode_changed(self) -> None:
        """抽取模式切换时更新 UI"""
        is_category = self.ext_category_radio.isChecked()

        # 按类别: 显示类别面板, 隐藏目录面板
        self.ext_category_group.setVisible(is_category)
        self.ext_dir_group.setVisible(not is_category)

        # 按类别模式: 默认勾选复制标签
        if is_category:
            self.ext_copy_labels_check.setChecked(True)

        # "按类别放置" radio 仅在按类别抽取模式下可用
        self.ext_layout_category_radio.setEnabled(is_category)
        if not is_category and self.ext_layout_category_radio.isChecked():
            self.ext_layout_keep_radio.setChecked(True)

        self._update_extract_action_states()

    def _refresh_extract_categories(self) -> None:
        """从扫描结果刷新类别列表 (带行内控件)"""
        self.ext_category_tree.clear()

        if not hasattr(self, "detected_classes") or not self.detected_classes:
            return

        # 普通类别行
        for cls_name in self.detected_classes:
            item = QTreeWidgetItem()
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setText(0, str(cls_name))
            item.setText(1, "—")
            self.ext_category_tree.addTopLevelItem(item)
            self._setup_row_widgets(self.ext_category_tree, item, 999999)

        # 特殊类别行 (空标签 / 混合类 / 无标签)
        special_categories = [
            ("_empty", "🔲 空标签"),
            ("_mixed", "🔀 混合类"),
            ("_no_label", "❌ 无标签"),
        ]
        for internal_name, display_name in special_categories:
            item = QTreeWidgetItem()
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setText(0, display_name)
            item.setText(1, "—")
            item.setData(0, Qt.ItemDataRole.UserRole, internal_name)
            self.ext_category_tree.addTopLevelItem(item)
            self._setup_row_widgets(self.ext_category_tree, item, 999999)

        for col in range(self.ext_category_tree.columnCount()):
            self.ext_category_tree.resizeColumnToContents(col)

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

            # 设置行内控件
            self._setup_row_widgets(self.ext_dir_tree, item, count)

            total_images += count

        for col in range(self.ext_dir_tree.columnCount()):
            self.ext_dir_tree.resizeColumnToContents(col)

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
    def _on_ext_cat_select_all(self) -> None:
        """全选类别"""
        for i in range(self.ext_category_tree.topLevelItemCount()):
            self.ext_category_tree.topLevelItem(i).setCheckState(
                0, Qt.CheckState.Checked
            )

    @Slot()
    def _on_ext_cat_deselect_all(self) -> None:
        """全不选类别"""
        for i in range(self.ext_category_tree.topLevelItemCount()):
            self.ext_category_tree.topLevelItem(i).setCheckState(
                0, Qt.CheckState.Unchecked
            )

    @Slot()
    def _on_ext_browse_output(self) -> None:
        """选择输出目录"""
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.ext_output_input.setText(path)

    def _get_output_layout(self) -> str:
        """从 RadioButton 组获取输出布局值"""
        if self.ext_layout_category_radio.isChecked():
            return "by_category"
        elif self.ext_layout_flat_radio.isChecked():
            return "flat"
        return "keep"

    def _build_extract_config(self) -> Optional[ExtractConfig]:
        """从 UI 构建 ExtractConfig"""
        is_category = self.ext_category_radio.isChecked()
        mode = "by_category" if is_category else "by_directory"

        per_item_counts: dict[str, tuple[str, float]] = {}

        if is_category:
            # 收集类别配置 (含普通类别和特殊类别)
            categories: list[str] = []
            for i in range(self.ext_category_tree.topLevelItemCount()):
                item = self.ext_category_tree.topLevelItem(i)
                row_config = self._read_row_config(item)
                if row_config is not None:
                    # 优先取 UserRole 存的内部名称 (特殊类别用)
                    internal_name = item.data(0, Qt.ItemDataRole.UserRole)
                    cls_name = internal_name if internal_name else item.text(0)
                    categories.append(cls_name)
                    per_item_counts[cls_name] = row_config

            if not categories:
                self.log_message.emit("请至少选择一个类别")
                return None

            return ExtractConfig(
                mode=mode,
                per_item_counts=per_item_counts,
                categories=categories,
                selected_dirs=[],  # 按类别模式搜索全部目录
                output_layout=self._get_output_layout(),
                copy_labels=self.ext_copy_labels_check.isChecked(),
                seed=(
                    self.ext_seed_spin.value()
                    if self.ext_seed_check.isChecked()
                    else None
                ),
                output_dir=(
                    Path(self.ext_output_input.text().strip())
                    if self.ext_output_input.text().strip()
                    else None
                ),
            )
        else:
            # 收集目录配置
            selected_dirs: list[Path] = []
            for i in range(self.ext_dir_tree.topLevelItemCount()):
                item = self.ext_dir_tree.topLevelItem(i)
                row_config = self._read_row_config(item)
                if row_config is not None:
                    rel_dir = item.data(0, Qt.ItemDataRole.UserRole)
                    selected_dirs.append(Path(rel_dir))
                    per_item_counts[rel_dir] = row_config

            if not selected_dirs:
                self.log_message.emit("请至少选择一个目录")
                return None

            return ExtractConfig(
                mode=mode,
                per_item_counts=per_item_counts,
                categories=[],
                selected_dirs=selected_dirs,
                output_layout=self._get_output_layout(),
                copy_labels=self.ext_copy_labels_check.isChecked(),
                seed=(
                    self.ext_seed_spin.value()
                    if self.ext_seed_check.isChecked()
                    else None
                ),
                output_dir=(
                    Path(self.ext_output_input.text().strip())
                    if self.ext_output_input.text().strip()
                    else None
                ),
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

        # 检查输出目录是否已存在
        if config.output_dir is not None:
            from ui.output_dir_check import check_output_dir
            checked = check_output_dir(self, config.output_dir)
            if checked is None:
                return
            config.output_dir = checked
            self.ext_output_input.setText(str(checked))

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
