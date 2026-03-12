"""
data_widget.py - 数据准备模块 UI
============================================

职责:
    - 数据集路径选择
    - 扫描统计展示
    - 标签编辑操作
    - 数据集划分
    - YAML 配置生成

架构要点:
    - 继承 QWidget，使用 QVBoxLayout + QTabWidget 布局
    - 状态变量实现 Tab 间数据流
    - 通过 Signal 与主窗口日志面板通信
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QFrame,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.data_handler import (
    AugmentConfig,
    AugmentResult,
    DataHandler,
    DataWorker,
    LabelFormat,
    ModifyAction,
    ScanResult,
    SplitMode,
    SplitResult,
)
from ui.focus_widgets import FocusDoubleSpinBox, FocusSlider, FocusSpinBox
from ui.path_input_group import PathInputGroup
from ui.styled_message_box import StyledMessageBox, StyledProgressDialog


class DataWidget(QWidget):
    """
    数据准备模块主控件
    
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
        
        # Tab 内容区
        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("subTabWidget")
        self.tab_widget.addTab(self._create_stats_tab(), "📊 统计")
        self.tab_widget.addTab(self._create_edit_tab(), "✏️ 编辑")
        self.tab_widget.addTab(self._create_augment_tab(), "🧪 增强")
        self.tab_widget.addTab(self._create_split_tab(), "📂 划分")
        main_layout.addWidget(self.tab_widget, 1)  # 拉伸因子 = 1
        
        # 进度条区
        main_layout.addWidget(self._create_progress_zone())
    
    def _create_stats_tab(self) -> QWidget:
        """创建统计 Tab (使用 QScrollArea 防止日志面板展开时内容被压缩)"""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)
        
        # 用 QScrollArea 包裹所有内容，防止日志面板展开时被压缩
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setSpacing(10)
        
        # 路径输入组
        self.stats_path_group = PathInputGroup(
            show_image_dir=True,
            show_label_dir=True,
            show_classes=True,
            group_title="数据源路径",
        )
        layout.addWidget(self.stats_path_group)
        
        # 中部内容区: 左侧类别表，右侧概览
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)
        
        # ========== 左侧: 类别统计 GroupBox ==========
        stats_group = QGroupBox("类别统计")
        stats_group_layout = QVBoxLayout(stats_group)
        stats_group_layout.setContentsMargins(8, 8, 8, 8)
        
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(3)
        self.stats_table.setHorizontalHeaderLabels(["类别名称", "数量", "占比"])
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setShowGrid(False)
        stats_group_layout.addWidget(self.stats_table)
        
        content_layout.addWidget(stats_group, 3)
        
        # ========== 右侧: 数据概览 GroupBox ==========
        overview_group = QGroupBox("数据概览")
        overview_group.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        overview_group.setMinimumWidth(310)
        overview_group.setMaximumWidth(350)
        
        overview_outer = QVBoxLayout(overview_group)
        overview_outer.setContentsMargins(8, 8, 8, 8)
        overview_outer.setSpacing(8)
        
        # 卡片网格
        overview_grid = QGridLayout()
        overview_grid.setHorizontalSpacing(8)
        overview_grid.setVerticalSpacing(8)
        
        overview_items = [
            ("total_images", "图片总数", "#89b4fa"),
            ("labeled_images", "有标签图片", "#a6e3a1"),
            ("missing_labels", "缺失标签", "#fab387"),
            ("empty_labels", "空标签", "#f9e2af"),
            ("class_count", "类别数", "#cba6f7"),
            ("total_objects", "目标总数", "#89b4fa"),
            ("missing_ratio", "缺失占比", "#f38ba8"),
            ("empty_ratio", "空标签占比", "#f9e2af"),
        ]
        
        for index, (key, title, color) in enumerate(overview_items):
            card = self._create_stats_overview_card(title, key, color)
            overview_grid.addWidget(card, index // 2, index % 2)
        
        overview_outer.addLayout(overview_grid)
        overview_outer.addStretch()
        
        content_layout.addWidget(overview_group, 1)
        layout.addLayout(content_layout, 1)
        
        # 按钮区域 (底部)
        btn_layout = QHBoxLayout()
        
        # 包含无标签图片复选框 (用于分类功能)
        self.include_no_label_check = QCheckBox("包含无标签图片")
        self.include_no_label_check.setChecked(True)
        self.include_no_label_check.setToolTip("分类时是否将无标签图片复制到 _no_label 文件夹")
        btn_layout.addWidget(self.include_no_label_check)
        
        btn_layout.addStretch()
        
        # 扫描按钮
        self.scan_btn = QPushButton("🔍 扫描数据集")
        self.scan_btn.setMinimumHeight(35)
        self.scan_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn_layout.addWidget(self.scan_btn)
        
        # 按类别分类按钮
        self.categorize_btn = QPushButton("📂 按类别分类")
        self.categorize_btn.setMinimumHeight(35)
        self.categorize_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.categorize_btn.setToolTip(
            "将数据集按标签类别分类到不同文件夹:\n"
            "• 单一类别 → {class_id}/\n"
            "• 多类别 → _mixed/\n"
            "• 空标签 → _empty/\n"
            "• 无标签 → _no_label/"
        )
        self.categorize_btn.setProperty("class", "warning")
        btn_layout.addWidget(self.categorize_btn)
        
        layout.addLayout(btn_layout)
        
        # 将内容装入滚动区域
        scroll_area.setWidget(scroll_content)
        tab_layout.addWidget(scroll_area)
        
        return tab

    def _create_stats_overview_card(self, title: str, key: str, accent_color: str = "#89b4fa") -> QFrame:
        """创建带彩色指示条的统计概览卡片"""
        card = QFrame()
        card.setObjectName("statsOverviewCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card.setMinimumHeight(72)
        
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 12, 0)
        card_layout.setSpacing(0)
        
        # 左侧彩色指示条
        accent_bar = QFrame()
        accent_bar.setFixedWidth(4)
        accent_bar.setStyleSheet(
            f"background-color: {accent_color}; "
            f"border-top-left-radius: 10px; "
            f"border-bottom-left-radius: 10px;"
        )
        card_layout.addWidget(accent_bar)
        
        # 右侧内容区
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(12, 10, 0, 10)
        text_layout.setSpacing(4)
        
        title_label = QLabel(title)
        title_label.setObjectName("mutedLabel")
        title_label.setStyleSheet("font-size: 11px;")
        
        value_label = QLabel("--")
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {accent_color};")
        
        text_layout.addWidget(title_label)
        text_layout.addWidget(value_label)
        card_layout.addLayout(text_layout)
        
        self._stats_overview_labels[key] = value_label
        return card

    def _reset_stats_overview(self) -> None:
        """重置右侧概览显示"""
        for label in self._stats_overview_labels.values():
            label.setText("--")

    def _update_stats_overview(self, result: ScanResult) -> None:
        """更新右侧概览数据"""
        total_images = result.total_images
        labeled_images = result.labeled_images
        missing_labels = len(result.missing_labels)
        empty_labels = result.empty_labels
        class_count = len(result.classes)
        total_objects = sum(result.class_stats.values())
        missing_ratio = f"{missing_labels / total_images * 100:.1f}%" if total_images > 0 else "0.0%"
        empty_ratio = f"{empty_labels / labeled_images * 100:.1f}%" if labeled_images > 0 else "0.0%"
        
        overview_values = {
            "total_images": f"{total_images}",
            "labeled_images": f"{labeled_images}",
            "missing_labels": f"{missing_labels}",
            "empty_labels": f"{empty_labels}",
            "class_count": f"{class_count}",
            "total_objects": f"{total_objects}",
            "missing_ratio": missing_ratio,
            "empty_ratio": empty_ratio,
        }
        
        for key, value in overview_values.items():
            if key in self._stats_overview_labels:
                self._stats_overview_labels[key].setText(value)
    
    def _create_edit_tab(self) -> QWidget:
        """
        创建编辑 Tab (路径区 + 2-Left + 1-Right 布局)
        
        顶部: 路径输入组
        下方:
            左侧: 两个垂直堆叠的 GroupBox
                - 生成空标签
                - 格式互转
            右侧: 修改/删除标签
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)
        
        # 用 QScrollArea 包裹所有内容，防止日志面板展开时被压缩
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)
        
        # 路径输入组
        self.edit_path_group = PathInputGroup(
            show_image_dir=True,
            show_label_dir=True,
            show_classes=True,
            group_title="数据源路径",
        )
        scroll_layout.addWidget(self.edit_path_group)
        
        # 下方内容区 (水平布局)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)
        
        # ========== 左列: 标签工具 GroupBox ==========
        left_group = QGroupBox("标签工具")
        left_group_layout = QVBoxLayout(left_group)
        left_group_layout.setSpacing(10)
        
        # ---- GroupBox 1: 生成空标签 ----
        gen_group = QGroupBox("生成空标签")
        gen_layout = QVBoxLayout(gen_group)
        
        self.empty_txt_radio = QRadioButton("TXT (YOLO)")
        self.empty_xml_radio = QRadioButton("XML (VOC)")
        self.empty_txt_radio.setChecked(True)
        
        self.empty_format_group = QButtonGroup(self)
        self.empty_format_group.addButton(self.empty_txt_radio, 0)
        self.empty_format_group.addButton(self.empty_xml_radio, 1)
        
        gen_layout.addWidget(self.empty_txt_radio)
        gen_layout.addWidget(self.empty_xml_radio)
        
        # 操作按钮 (右对齐)
        gen_btn_layout = QHBoxLayout()
        gen_btn_layout.addStretch()
        self.gen_empty_btn = QPushButton("📝 生成空标签")
        self.gen_empty_btn.setMinimumHeight(35)
        self.gen_empty_btn.setMinimumWidth(120)
        self.gen_empty_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.gen_empty_btn.setEnabled(False)
        gen_btn_layout.addWidget(self.gen_empty_btn)
        gen_layout.addLayout(gen_btn_layout)
        
        left_group_layout.addWidget(gen_group)
        
        # ---- GroupBox 2: 格式互转 ----
        convert_group = QGroupBox("格式互转")
        convert_layout = QVBoxLayout(convert_group)
        
        self.txt_to_xml_radio = QRadioButton("TXT (YOLO) → XML (VOC)")
        self.xml_to_txt_radio = QRadioButton("XML (VOC) → TXT (YOLO)")
        self.txt_to_xml_radio.setChecked(True)
        
        self.convert_group = QButtonGroup(self)
        self.convert_group.addButton(self.txt_to_xml_radio, 0)
        self.convert_group.addButton(self.xml_to_txt_radio, 1)
        
        convert_layout.addWidget(self.txt_to_xml_radio)
        convert_layout.addWidget(self.xml_to_txt_radio)
        
        # 操作按钮 (右对齐)
        convert_btn_layout = QHBoxLayout()
        convert_btn_layout.addStretch()
        self.convert_btn = QPushButton("🔄 执行转换")
        self.convert_btn.setMinimumHeight(35)
        self.convert_btn.setMinimumWidth(120)
        self.convert_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.convert_btn.setProperty("class", "success")
        self.convert_btn.setEnabled(False)
        convert_btn_layout.addWidget(self.convert_btn)
        convert_layout.addLayout(convert_btn_layout)
        
        left_group_layout.addWidget(convert_group)
        left_group_layout.addStretch()  # 将内容推到顶部
        
        content_layout.addWidget(left_group, 1)  # Flex 1
        
        # ========== 右列: 修改/删除标签 ==========
        right_group = QGroupBox("修改/删除标签")
        right_layout = QVBoxLayout(right_group)
        
        # 操作类型
        action_label = QLabel("操作类型:")
        right_layout.addWidget(action_label)
        
        action_row = QHBoxLayout()
        self.replace_radio = QRadioButton("替换类别")
        self.remove_radio = QRadioButton("删除类别")
        self.replace_radio.setChecked(True)
        
        self.action_group = QButtonGroup(self)
        self.action_group.addButton(self.replace_radio, 0)
        self.action_group.addButton(self.remove_radio, 1)
        
        action_row.addWidget(self.replace_radio)
        action_row.addWidget(self.remove_radio)
        action_row.addStretch()
        right_layout.addLayout(action_row)
        
        # 输入字段
        form_layout = QFormLayout()
        self.old_name_input = QComboBox()
        self.old_name_input.setEditable(True)
        self.old_name_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.old_name_input.lineEdit().setPlaceholderText("原类别名称或 ID")
        form_layout.addRow("原类别/ID:", self.old_name_input)
        
        self._new_name_label = QLabel("新类别/ID:")
        self.new_name_input = QComboBox()
        self.new_name_input.setEditable(True)
        self.new_name_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.new_name_input.lineEdit().setPlaceholderText("新类别名称或 ID (留空表示删除)")
        form_layout.addRow(self._new_name_label, self.new_name_input)
        right_layout.addLayout(form_layout)
        
        # 备份选项
        self.backup_check = QCheckBox("修改前备份原文件 (.bak)")
        self.backup_check.setChecked(True)
        right_layout.addWidget(self.backup_check)
        right_layout.addStretch()  # 将按钮推到底部
        
        # 操作按钮 (右对齐)
        btn_layout2 = QHBoxLayout()
        btn_layout2.addStretch()
        self.modify_btn = QPushButton("⚡ 执行修改")
        self.modify_btn.setMinimumHeight(35)
        self.modify_btn.setMinimumWidth(120)
        self.modify_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.modify_btn.setEnabled(False)
        btn_layout2.addWidget(self.modify_btn)
        right_layout.addLayout(btn_layout2)
        
        content_layout.addWidget(right_group, 1)  # Flex 1
        
        scroll_layout.addLayout(content_layout, 1)  # 拉伸填充
        
        # 将内容装入滚动区域
        scroll_area.setWidget(scroll_content)
        tab_layout.addWidget(scroll_area)
        
        return tab
    
    def _create_augment_tab(self) -> QWidget:
        """Build the augmentation tab."""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setSpacing(10)

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

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.augment_btn = QPushButton("🧪 开始增强")
        self.augment_btn.setMinimumHeight(35)
        self.augment_btn.setMinimumWidth(120)
        self.augment_btn.setProperty("class", "primary")
        self.augment_btn.setEnabled(False)
        button_row.addWidget(self.augment_btn)
        content_layout.addLayout(button_row)
        content_layout.addStretch()

        scroll.setWidget(content)
        tab_layout.addWidget(scroll, 1)
        self._update_augment_mode_controls()
        return tab

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
        tab_layout.setSpacing(10)
        
        # 路径输入组 (划分不需要 classes.txt)
        self.split_path_group = PathInputGroup(
            show_image_dir=True,
            show_label_dir=True,
            show_classes=False,
            group_title="数据源路径",
        )
        tab_layout.addWidget(self.split_path_group)
        
        # 下方内容区 (水平布局)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)
        
        # ========== 左侧: 划分工具 (Flex 1) ==========
        # 使用 QScrollArea 防止内容挤压
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        # 外层大 GroupBox
        left_group = QGroupBox("划分工具")
        left_group_layout = QVBoxLayout(left_group)
        left_group_layout.setSpacing(10)
        
        # --- Group 1: 划分参数 ---
        param_group = QGroupBox("划分参数")
        param_layout = QVBoxLayout(param_group)
        
        # 比例滑块
        param_layout.addWidget(QLabel("划分比例:"))
        
        ratio_row = QHBoxLayout()
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
        
        output_layout.addSpacing(5)
        
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
        
        output_layout.addSpacing(10)
        
        # 执行按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.split_btn = QPushButton("🚀 开始划分")
        self.split_btn.setMinimumHeight(35)
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
        main_layout.setSpacing(10)
        
        # ========== 统一 GroupBox ==========
        yaml_group = QGroupBox("YAML 配置")
        yaml_layout = QVBoxLayout(yaml_group)
        
        # ========== 左右分栏布局 ==========
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)
        
        # ========== 左侧: 路径配置 (Flex 3) ==========
        left_group = QGroupBox("路径配置")
        left_layout = QVBoxLayout(left_group)
        
        # 使用 Grid 布局对齐 Label | Input | Button
        from PySide6.QtWidgets import QGridLayout
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
        btn_layout.addStretch()  # 推到右侧
        self.save_yaml_btn = QPushButton("💾 保存 YAML 配置")
        self.save_yaml_btn.setMinimumHeight(40)
        self.save_yaml_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.save_yaml_btn.setProperty("class", "success")
        btn_layout.addWidget(self.save_yaml_btn)
        yaml_layout.addLayout(btn_layout)
        
        main_layout.addWidget(yaml_group, 1)  # 拉伸填充
        
        return tab
    
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
        # Tab 间路径同步 (任一修改同步全部)
        self.stats_path_group.paths_changed.connect(self._sync_paths_from_stats)
        self.edit_path_group.paths_changed.connect(self._sync_paths_from_edit)
        self.augment_path_group.paths_changed.connect(self._sync_paths_from_augment)
        self.split_path_group.paths_changed.connect(self._sync_paths_from_split)
        self.edit_path_group.paths_changed.connect(self._update_edit_action_states)
        self.augment_path_group.paths_changed.connect(self._update_augment_action_states)
        self.tab_widget.currentChanged.connect(self._on_sub_tab_changed)

        # Tab 1 - 统计
        self.scan_btn.clicked.connect(self._on_scan)
        self.categorize_btn.clicked.connect(self._on_categorize)

        # Tab 2 - 编辑
        self.gen_empty_btn.clicked.connect(self._on_generate_empty)
        self.modify_btn.clicked.connect(self._on_modify_labels)
        self.remove_radio.toggled.connect(self._on_action_changed)
        self.convert_btn.clicked.connect(self._on_convert_format)
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
        self.augment_advanced_toggle.toggled.connect(self._toggle_augment_advanced)
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

        # 取消按钮
        self.cancel_btn.clicked.connect(self._on_cancel)

        self._refresh_edit_class_options()
        self._update_edit_action_states()
        self._update_augment_action_states()

    def _sync_paths_from_stats(self) -> None:
        """??? Tab ??????? Tab"""
        paths = self.stats_path_group.get_all_paths()
        self.edit_path_group.set_all_paths(paths, emit_signal=False)
        self.augment_path_group.set_all_paths(paths, emit_signal=False)
        self.split_path_group.set_all_paths(paths, emit_signal=False)
        self._invalidate_edit_precheck_cache()
        self._refresh_edit_class_options()
        self._update_edit_action_states()
        self._update_augment_action_states()
        self._update_default_output_paths(paths.get("image_dir", ""))

    def _sync_paths_from_edit(self) -> None:
        """??? Tab ??????? Tab"""
        paths = self.edit_path_group.get_all_paths()
        self.stats_path_group.set_all_paths(paths, emit_signal=False)
        self.augment_path_group.set_all_paths(paths, emit_signal=False)
        self.split_path_group.set_all_paths(paths, emit_signal=False)
        self._invalidate_edit_precheck_cache()
        self._refresh_edit_class_options()
        self._update_edit_action_states()
        self._update_augment_action_states()
        self._update_default_output_paths(paths.get("image_dir", ""))

    def _sync_paths_from_augment(self) -> None:
        """??? Tab ??????? Tab"""
        paths = self.augment_path_group.get_all_paths()
        self.stats_path_group.set_all_paths(paths, emit_signal=False)
        self.edit_path_group.set_all_paths(paths, emit_signal=False)
        self.split_path_group.set_all_paths(paths, emit_signal=False)
        self._invalidate_edit_precheck_cache()
        self._refresh_edit_class_options()
        self._update_edit_action_states()
        self._update_augment_action_states()
        self._update_default_output_paths(paths.get("image_dir", ""))

    def _sync_paths_from_split(self) -> None:
        """??? Tab ??????? Tab"""
        paths = self.split_path_group.get_all_paths()
        self.stats_path_group.set_all_paths(paths, emit_signal=False)
        self.edit_path_group.set_all_paths(paths, emit_signal=False)
        self.augment_path_group.set_all_paths(paths, emit_signal=False)
        self._invalidate_edit_precheck_cache()
        self._refresh_edit_class_options()
        self._update_edit_action_states()
        self._update_augment_action_states()
        self._update_default_output_paths(paths.get("image_dir", ""))

    def _update_default_output_paths(self, image_dir: str) -> None:
        """??????????/????????"""
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

    def _update_edit_action_states(self) -> None:
        """????????????????????"""
        img_path = self.edit_path_group.get_image_dir()
        has_image_dir = bool(img_path and img_path.exists())
        is_busy = bool(self._worker and self._worker.isRunning())
        enabled = has_image_dir and not is_busy

        self.gen_empty_btn.setEnabled(enabled)
        self.convert_btn.setEnabled(enabled)
        self.modify_btn.setEnabled(enabled)

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

    @Slot(int)
    def _on_augment_mode_changed(self, index: int) -> None:
        """React to random/fixed mode changes."""
        self._update_augment_action_states()

    @Slot(bool)
    def _toggle_augment_advanced(self, checked: bool) -> None:
        """Show or hide advanced augmentation controls."""
        self.augment_advanced_container.setVisible(checked)
        self.augment_advanced_toggle.setText("▲ 收起高级增强" if checked else "▼ 展开高级增强")

    @Slot(int)
    def _on_sub_tab_changed(self, index: int) -> None:
        """???????????"""
        self._update_edit_action_states()
        self._update_augment_action_states()

    def _apply_edit_class_options(self, options: list[str]) -> None:
        """应用修改标签下拉选项并保留当前输入"""
        old_value = self.old_name_input.currentText().strip()
        new_value = self.new_name_input.currentText().strip()
        
        self.old_name_input.blockSignals(True)
        self.new_name_input.blockSignals(True)
        
        self.old_name_input.clear()
        self.new_name_input.clear()
        
        if options:
            self.old_name_input.addItems(options)
            self.new_name_input.addItems(options)
        
        self.old_name_input.setCurrentText(old_value)
        self.new_name_input.setCurrentText(new_value)
        
        self.old_name_input.blockSignals(False)
        self.new_name_input.blockSignals(False)

    def _refresh_edit_class_options(self) -> None:
        """刷新修改标签下拉选项 (轻量模式)"""
        classes_txt = self.edit_path_group.get_classes_path()
        if classes_txt and classes_txt.exists():
            self._apply_edit_class_options(self._handler.load_classes_txt(classes_txt))
        elif self.detected_classes:
            self._apply_edit_class_options(self.detected_classes)
        else:
            self._apply_edit_class_options([])

    def _resolve_modify_action(self) -> ModifyAction:
        """根据当前输入解析修改动作"""
        new_value = self.new_name_input.currentText().strip()
        if self.remove_radio.isChecked() or not new_value:
            return ModifyAction.REMOVE
        return ModifyAction.REPLACE

    def _show_modify_warning(self, message: str) -> None:
        """修改功能警告弹窗"""
        StyledMessageBox.warning(self, "修改标签", message)

    def _show_modify_info(self, title: str, message: str) -> None:
        """修改功能信息弹窗"""
        StyledMessageBox.information(self, title, message)

    def _invalidate_edit_precheck_cache(self, *_args) -> None:
        """清除编辑页最近一次预检查缓存"""
        self._edit_precheck_cache = None

    def _get_edit_precheck_cache(self, cache_key: tuple) -> Optional[object]:
        """获取有效的编辑预检查缓存"""
        if not self._edit_precheck_cache:
            return None
        
        if self._edit_precheck_cache.get("key") != cache_key:
            return None
        
        timestamp = self._edit_precheck_cache.get("timestamp", 0.0)
        if time.monotonic() - timestamp > self._edit_precheck_cache_ttl:
            self._edit_precheck_cache = None
            return None
        
        return self._edit_precheck_cache.get("result")

    def _set_edit_precheck_cache(self, cache_key: tuple, result: object) -> None:
        """保存编辑页最近一次预检查结果"""
        self._edit_precheck_cache = {
            "key": cache_key,
            "timestamp": time.monotonic(),
            "result": result,
        }

    def _confirm_edit_action(self, title: str, message: str) -> bool:
        """显示确认弹窗"""
        return StyledMessageBox.question(self, title, message)

    def _cancel_precheck(self) -> None:
        """取消正在进行的预检查"""
        if not (self._worker and self._worker.isRunning()):
            return
        
        self._precheck_cancelled = True
        self._worker.request_interrupt()
        self.log_message.emit("正在取消预检查...")

    @Slot(int, int)
    def _on_precheck_progress(self, current: int, total: int) -> None:
        """更新预检查进度弹窗"""
        dialog = self._precheck_dialog
        if dialog is None:
            return
        
        maximum = max(total, 1)
        try:
            if dialog.maximum() == 0:
                dialog.setRange(0, maximum)
            dialog.setMaximum(maximum)
            dialog.setValue(min(current, maximum))
            dialog.setLabelText(f"{self._precheck_dialog_text}\n{current}/{maximum}")
        except RuntimeError:
            return

    def _cleanup_precheck_dialog(self) -> None:
        """关闭预检查进度弹窗"""
        dialog = self._precheck_dialog
        self._precheck_dialog = None
        if dialog is None:
            return
        
        try:
            dialog.canceled.disconnect(self._cancel_precheck)
        except (RuntimeError, TypeError):
            pass
        
        dialog.blockSignals(True)
        dialog.close()
        dialog.deleteLater()
        self._precheck_dialog_text = ""

    def _on_precheck_result(self, result: object) -> None:
        """保存预检查结果，等待线程收尾后再确认"""
        if self._precheck_cancelled:
            return
        
        self._pending_precheck_result = result

    def _on_precheck_error(self, error: str) -> None:
        """记录预检查错误"""
        self._pending_precheck_error = error

    @Slot()
    def _on_precheck_finished(self) -> None:
        """预检查线程完成后做清理和确认"""
        self._set_ui_busy(False)
        self._cleanup_precheck_dialog()
        
        worker = self._worker
        self._worker = None
        if worker:
            worker.deleteLater()
        
        if self._precheck_cancelled:
            self._pending_precheck_result = None
            self._pending_precheck_handler = None
            self._pending_precheck_cache_key = None
            self._pending_precheck_error = None
            self._pending_precheck_title = ""
            self.log_message.emit("已取消预检查")
            return
        
        if self._pending_precheck_error:
            StyledMessageBox.warning(self, self._pending_precheck_title or "预检查", self._pending_precheck_error)
            self._pending_precheck_result = None
            self._pending_precheck_handler = None
            self._pending_precheck_cache_key = None
            self._pending_precheck_error = None
            self._pending_precheck_title = ""
            return
        
        result = self._pending_precheck_result
        handler = self._pending_precheck_handler
        cache_key = self._pending_precheck_cache_key
        
        self._pending_precheck_result = None
        self._pending_precheck_handler = None
        self._pending_precheck_cache_key = None
        self._pending_precheck_error = None
        self._pending_precheck_title = ""
        
        if result is not None and handler:
            if cache_key is not None:
                self._set_edit_precheck_cache(cache_key, result)
            handler(result)

    def _start_precheck_worker(
        self,
        *,
        title: str,
        label_text: str,
        cache_key: tuple,
        task,
        on_ready: Callable[[object], None],
    ) -> None:
        """启动后台预检查，并在完成后弹出确认框"""
        cached_result = self._get_edit_precheck_cache(cache_key)
        if cached_result is not None:
            on_ready(cached_result)
            return
        
        if self._worker and self._worker.isRunning():
            self.log_message.emit("已有任务在运行中")
            return
        
        self._precheck_cancelled = False
        self._pending_precheck_result = None
        self._pending_precheck_handler = on_ready
        self._pending_precheck_cache_key = cache_key
        self._pending_precheck_error = None
        self._pending_precheck_title = title
        
        self._precheck_dialog = StyledProgressDialog(self, title, label_text, "取消")
        self._precheck_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._precheck_dialog.setRange(0, 0)
        self._precheck_dialog.setValue(0)
        self._precheck_dialog_text = label_text
        self._precheck_dialog.canceled.connect(self._cancel_precheck)
        
        self._worker = DataWorker(self)
        self._worker.set_task(task)
        self._worker.progress.connect(self._on_precheck_progress)
        self._worker.result_ready.connect(self._on_precheck_result)
        self._worker.error.connect(self._on_precheck_error)
        self._worker.finished.connect(self._on_precheck_finished)
        
        self._set_ui_busy(True, enable_cancel=False)
        self.log_message.emit(label_text)
        self._precheck_dialog.show()
        self._worker.start()

    def _confirm_generate_empty_after_precheck(
        self,
        preview: dict,
        img_path: Path,
        label_path: Optional[Path],
        label_format: LabelFormat,
    ) -> None:
        """根据预检查结果确认是否生成空标签"""
        total_images = preview.get("total_images", 0)
        missing_labels = preview.get("missing_labels", 0)
        format_text = "TXT (YOLO)" if label_format == LabelFormat.TXT else "XML (VOC)"
        
        if total_images == 0:
            StyledMessageBox.information(self, "生成空标签", "未找到可检查的图片文件。")
            return
        
        if missing_labels == 0:
            StyledMessageBox.information(self, "生成空标签", "未发现缺失标签图片，无需生成空标签。")
            return
        
        message = (
            f"将检查 {total_images} 张图片。\n"
            f"预计生成 {missing_labels} 个空标签。\n"
            f"标签格式: {format_text}\n\n"
            "是否继续执行？"
        )
        if not self._confirm_edit_action("生成空标签", message):
            return
        
        self._start_worker(
            lambda: self._handler.generate_missing_labels(
                img_path,
                label_format,
                label_dir=label_path,
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_generate_empty_finished,
        )

    def _confirm_convert_after_precheck(
        self,
        preview: dict,
        img_path: Path,
        label_path: Optional[Path],
        to_xml: bool,
    ) -> None:
        """根据预检查结果确认是否执行格式转换"""
        total_labels = preview.get("total_labels", 0)
        source_type = preview.get("source_type", "TXT")
        target_type = preview.get("target_type", "XML")
        output_dir_name = preview.get("output_dir_name", "")
        
        if total_labels == 0:
            StyledMessageBox.information(self, "格式互转", f"未找到可转换的 {source_type} 标签文件。")
            return
        
        message = (
            f"将转换 {total_labels} 个 {source_type} 标签文件。\n"
            f"输出格式: {target_type}\n"
            f"输出目录: {output_dir_name}\n\n"
            "是否继续执行？"
        )
        if not self._confirm_edit_action("格式互转", message):
            return
        
        classes = None
        classes_txt = self.edit_path_group.get_classes_path()
        if classes_txt and classes_txt.exists():
            classes = self._handler.load_classes_txt(classes_txt)
        elif self.detected_classes:
            classes = self.detected_classes
        
        dataset_root = self._resolve_dataset_root(img_path, label_path)
        self._start_worker(
            lambda: self._handler.convert_format(
                dataset_root,
                to_xml=to_xml,
                classes=classes,
                label_dir=label_path,
                image_dir=img_path,
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_convert_format_finished,
        )

    def _confirm_modify_after_precheck(
        self,
        preview: dict,
        search_dir: Path,
        action: ModifyAction,
        old_value: str,
        new_value: str,
        classes_txt: Optional[Path],
        image_dir: Optional[Path],
        label_dir: Optional[Path],
    ) -> None:
        """根据预检查结果确认是否执行标签修改"""
        total_label_files = preview.get("total_label_files", 0)
        txt_files = preview.get("txt_files", 0)
        xml_files = preview.get("xml_files", 0)
        matched_files = preview.get("matched_files", 0)
        matched_annotations = preview.get("matched_annotations", 0)
        backup_enabled = self.backup_check.isChecked()
        
        if total_label_files == 0:
            self._show_modify_info("修改标签", "未找到可修改的标签文件。")
            return
        
        if matched_annotations == 0:
            self._show_modify_info("修改标签", f"未找到与“{old_value}”匹配的标注。")
            return
        
        action_text = "替换类别" if action == ModifyAction.REPLACE else "删除类别"
        target_text = f"\n新类别/ID: {new_value}" if action == ModifyAction.REPLACE else ""
        backup_text = "开" if backup_enabled else "关"
        message = (
            f"将检查 {total_label_files} 个标签文件 (TXT {txt_files} / XML {xml_files})。\n"
            f"预计影响 {matched_files} 个文件 / {matched_annotations} 条标注。\n"
            f"操作: {action_text}\n"
            f"原类别/ID: {old_value}"
            f"{target_text}\n"
            f"备份: {backup_text}\n\n"
            "是否继续执行？"
        )
        if not self._confirm_edit_action("修改标签", message):
            return
        
        self._start_worker(
            lambda: self._handler.modify_labels(
                search_dir,
                action,
                old_value,
                new_value,
                backup=backup_enabled,
                classes_txt=classes_txt,
                image_dir=image_dir,
                label_dir=label_dir,
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_modify_labels_finished,
        )
    
    # ============================================================
    # 槽函数
    # ============================================================
    
    @Slot()
    def _on_browse_augment_output_dir(self) -> None:
        """????????"""
        path = QFileDialog.getExistingDirectory(self, "选择增强输出目录")
        if path:
            self.augment_output_input.setText(path)

    @Slot()
    def _on_browse_output_dir(self) -> None:
        """选择输出目录"""
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.output_dir_input.setText(path)
    
    @Slot()
    def _on_scan(self) -> None:
        """开始扫描数据集"""
        # 从统计 Tab 的 PathInputGroup 读取路径
        img_path = self.stats_path_group.get_image_dir()
        if not img_path:
            self.log_message.emit("请先选择图片目录")
            return
        
        if not img_path.exists():
            self.log_message.emit(f"图片目录不存在: {img_path}")
            return
        
        # 可选: 标签目录
        label_path = self.stats_path_group.get_label_dir()
        
        # 可选: classes.txt
        classes_txt = self.stats_path_group.get_classes_path()
        
        self._scan_result = None
        self.stats_table.setRowCount(0)
        self._reset_stats_overview()
        
        self._start_worker(
            lambda: self._handler.scan_dataset(
                img_path,
                label_dir=label_path,
                classes_txt=classes_txt,
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_scan_finished,
        )
    
    def _on_scan_finished(self, result: ScanResult) -> None:
        """扫描完成回调"""
        self._scan_result = result
        self._update_stats_overview(result)
        
        # 更新表格
        self.stats_table.setRowCount(0)
        total_objects = sum(result.class_stats.values())
        
        for cls, count in sorted(result.class_stats.items(), key=lambda x: -x[1]):
            row = self.stats_table.rowCount()
            self.stats_table.insertRow(row)
            self.stats_table.setItem(row, 0, QTableWidgetItem(cls))
            self.stats_table.setItem(row, 1, QTableWidgetItem(str(count)))
            percentage = f"{count / total_objects * 100:.1f}%" if total_objects > 0 else "0%"
            self.stats_table.setItem(row, 2, QTableWidgetItem(percentage))
        
        # 更新摘要
        summary = (
            f"图片总数: {result.total_images} | "
            f"有标签: {result.labeled_images} | "
            f"缺失标签: {len(result.missing_labels)} | "
            f"空标签: {result.empty_labels}"
        )
        
        # Shared state -> YAML panel
        self.detected_classes = result.classes
        self.classes_edit.setPlainText("\n".join(result.classes))
        self._refresh_edit_class_options()
        self._update_edit_action_states()
        
        self.log_message.emit(f"扫描完成: {summary}")
    
    @Slot()
    def _on_categorize(self) -> None:
        """按类别分类数据集"""
        # 从统计 Tab 的 PathInputGroup 读取路径
        img_path = self.stats_path_group.get_image_dir()
        if not img_path:
            self.log_message.emit("请先选择图片目录")
            return
        
        if not img_path.exists():
            self.log_message.emit(f"图片目录不存在: {img_path}")
            return
        
        # 可选: 标签目录
        label_path = self.stats_path_group.get_label_dir()
        
        # 可选: classes.txt
        classes_txt = self.stats_path_group.get_classes_path()
        
        # 是否包含无标签图片
        include_no_label = self.include_no_label_check.isChecked()
        
        self.log_message.emit("开始按类别分类数据集...")
        
        self._start_worker(
            lambda: self._handler.categorize_by_class(
                img_path,
                label_dir=label_path,
                output_dir=None,  # 使用默认输出目录
                classes_txt=classes_txt,
                include_no_label=include_no_label,
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_categorize_finished,
        )
    
    def _on_categorize_finished(self, stats: dict) -> None:
        """分类完成回调"""
        if not stats:
            self.log_message.emit("分类完成 (无数据)")
            return
        
        total = sum(stats.values())
        categories = len(stats)
        self.log_message.emit(f"分类完成: 共 {total} 张图片分到 {categories} 个类别")

    @Slot()
    def _on_generate_empty(self) -> None:
        """生成空标签"""
        img_path = self.edit_path_group.get_image_dir()
        if not img_path:
            self.log_message.emit("请先选择图片目录")
            return
        
        if not img_path.exists():
            self.log_message.emit(f"图片目录不存在: {img_path}")
            return
        
        label_path = self.edit_path_group.get_label_dir()
        label_format = LabelFormat.TXT if self.empty_txt_radio.isChecked() else LabelFormat.XML
        cache_key = (
            "generate_empty",
            str(img_path),
            str(label_path) if label_path else "",
            label_format.value,
        )
        
        self._start_precheck_worker(
            title="生成空标签",
            label_text="正在检查缺失标签...",
            cache_key=cache_key,
            task=lambda: self._handler.preview_generate_missing_labels(
                img_path,
                label_dir=label_path,
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
            ),
            on_ready=lambda result: self._confirm_generate_empty_after_precheck(
                result,
                img_path,
                label_path,
                label_format,
            ),
        )
    
    @Slot()
    def _on_convert_format(self) -> None:
        """执行格式转换"""
        # 从编辑 Tab 的 PathInputGroup 读取路径
        img_path = self.edit_path_group.get_image_dir()
        if not img_path:
            self.log_message.emit("请先选择图片目录")
            return
        
        if not img_path.exists():
            self.log_message.emit(f"图片目录不存在: {img_path}")
            return
        
        label_path = self.edit_path_group.get_label_dir()
        dataset_root = self._resolve_dataset_root(img_path, label_path)
        to_xml = self.txt_to_xml_radio.isChecked()
        cache_key = (
            "convert_format",
            str(img_path),
            str(label_path) if label_path else "",
            "to_xml" if to_xml else "to_txt",
        )
        
        self._start_precheck_worker(
            title="格式互转",
            label_text="正在检查可转换的标签文件...",
            cache_key=cache_key,
            task=lambda: self._handler.preview_convert_format(
                dataset_root,
                to_xml=to_xml,
                label_dir=label_path,
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
            ),
            on_ready=lambda result: self._confirm_convert_after_precheck(
                result,
                img_path,
                label_path,
                to_xml,
            ),
        )
    
    @Slot()
    def _on_modify_labels(self) -> None:
        """修改标签"""
        # 从编辑 Tab 的 PathInputGroup 读取路径
        img_path = self.edit_path_group.get_image_dir()
        if not img_path:
            self._show_modify_warning("请先选择图片目录")
            return
        
        if not img_path.exists():
            self._show_modify_warning(f"图片目录不存在:\n{img_path}")
            return
        
        old_value = self.old_name_input.currentText().strip()
        if not old_value:
            self._show_modify_warning("请输入原类别名称或 ID")
            return
        
        new_value = self.new_name_input.currentText().strip()
        action = self._resolve_modify_action()
        
        # 优先使用标签目录，如果未设置则回退到图片目录
        label_path = self.edit_path_group.get_label_dir()
        dataset_root = self._resolve_dataset_root(img_path, label_path)
        has_explicit_label_dir = bool(label_path and label_path.exists())
        search_dir = label_path if has_explicit_label_dir else dataset_root
        image_scope = None if has_explicit_label_dir else img_path
        
        # classes.txt
        classes_txt = self.edit_path_group.get_classes_path()
        cache_key = (
            "modify_labels",
            str(search_dir),
            str(image_scope) if image_scope else "",
            str(classes_txt) if classes_txt else "",
            action.value,
            old_value,
            new_value,
            self.backup_check.isChecked(),
        )
        
        self._start_precheck_worker(
            title="修改标签",
            label_text="正在检查将受影响的标签文件...",
            cache_key=cache_key,
            task=lambda: self._handler.preview_modify_labels(
                search_dir,
                action,
                old_value,
                new_value,
                classes_txt=classes_txt,
                image_dir=image_scope,
                label_dir=label_path,
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
            ),
            on_ready=lambda result: self._confirm_modify_after_precheck(
                result,
                search_dir,
                action,
                old_value,
                new_value,
                classes_txt,
                image_scope,
                label_path,
            ),
        )

    def _on_generate_empty_finished(self, count: int) -> None:
        """生成空标签完成回调"""
        self._invalidate_edit_precheck_cache()
        self.log_message.emit(f"已生成 {count} 个空标签文件")

    def _on_convert_format_finished(self, count: int) -> None:
        """格式转换完成回调"""
        self._invalidate_edit_precheck_cache()
        self.log_message.emit(f"格式转换完成: 成功 {count} 个文件")

    def _on_modify_labels_finished(self, count: int) -> None:
        """修改标签完成回调"""
        self._invalidate_edit_precheck_cache()
        self.log_message.emit(f"已修改 {count} 个标签文件")
        self._show_modify_info("修改完成", f"已修改 {count} 个标签文件。")
    
    @Slot(bool)
    def _on_action_changed(self, checked: bool) -> None:
        """操作类型切换: 删除模式时隐藏新名称输入框和标签"""
        # checked = True 表示删除模式被选中
        self.new_name_input.setVisible(not checked)
        self.new_name_input.setEnabled(not checked)
        self._new_name_label.setVisible(not checked)
        self._invalidate_edit_precheck_cache()
    
    @Slot(int)
    def _on_ratio_changed(self, value: int) -> None:
        """比例滑块变化"""
        self.ratio_label.setText(f"训练: {value}% | 验证: {100 - value}%")
    
    @Slot()
    def _on_augment(self) -> None:
        """???????????"""
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
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_augment_finished,
        )

    @Slot()
    def _on_split(self) -> None:
        """开始划分数据集"""
        # 从划分 Tab 的 PathInputGroup 读取路径
        img_path = self.split_path_group.get_image_dir()
        if not img_path:
            self.log_message.emit("请先选择图片目录")
            return
        
        if not img_path.exists():
            self.log_message.emit(f"图片目录不存在: {img_path}")
            return
        
        # 标签目录 (可选)
        label_path = self.split_path_group.get_label_dir()
        
        # 输出目录 (必填)
        output_dir = self.output_dir_input.text().strip()
        if not output_dir:
            self.log_message.emit("请选择输出目录")
            return
        output_path = Path(output_dir)
        
        ratio = self.ratio_slider.value() / 100.0
        seed = self.seed_spin.value()
        
        # 确定划分模式
        if self.copy_radio.isChecked():
            mode = SplitMode.COPY
        elif self.move_radio.isChecked():
            mode = SplitMode.MOVE
        else:
            mode = SplitMode.INDEX
        
        # 获取新选项
        ignore_orphans = self.ignore_orphans_check.isChecked()
        clear_output = self.clear_output_check.isChecked()
        
        # Keep split feedback concise and suppress per-file details.
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
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
                message_callback=split_message_callback,
            ),
            on_finished=self._on_split_finished,
        )
    
    def _on_augment_finished(self, result: AugmentResult) -> None:
        """????????"""
        self.augment_output_input.setText(result.output_dir)
        total_outputs = result.copied_originals + result.augmented_images
        self.log_message.emit(
            f"数据增强完成: 输出 {total_outputs} 张图片，标签 {result.label_files_written} 个"
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
    
    @Slot()
    def _on_cancel(self) -> None:
        """取消当前操作"""
        if self._worker and self._worker.isRunning():
            if self._precheck_dialog:
                self._precheck_cancelled = True
            self._worker.request_interrupt()
            self.log_message.emit("正在取消操作...")
    
    # ============================================================
    # 辅助方法
    # ============================================================
    
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
        """发射进度信号 (线程安全)"""
        if self._worker:
            self._worker.progress.emit(current, total)
    
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
            worker.deleteLater()
    
    def _set_ui_busy(self, busy: bool, *, enable_cancel: bool = True) -> None:
        """?? UI ????"""
        self.cancel_btn.setEnabled(busy and enable_cancel)
        self.scan_btn.setEnabled(not busy)
        self.categorize_btn.setEnabled(not busy)
        self.augment_btn.setEnabled(not busy)
        self.split_btn.setEnabled(not busy)
        self.save_yaml_btn.setEnabled(not busy)

        if busy:
            self.gen_empty_btn.setEnabled(False)
            self.convert_btn.setEnabled(False)
            self.modify_btn.setEnabled(False)
            self.augment_btn.setEnabled(False)
        else:
            self._update_edit_action_states()
            self._update_augment_action_states()

        if not busy:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.status_label.setText("??")
