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
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot, QMetaObject, Q_ARG
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.data_handler import (
    DataHandler,
    DataWorker,
    LabelFormat,
    ModifyAction,
    ScanResult,
    SplitMode,
    SplitResult,
)
from ui.focus_widgets import FocusSlider, FocusSpinBox
from ui.path_input_group import PathInputGroup


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
        
        # Tab 间共享状态
        self.detected_classes: list[str] = []  # Tab1 -> Tab4
        self.split_paths: dict = {}             # Tab3 -> Tab4
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
        self.tab_widget.addTab(self._create_split_tab(), "📂 划分")
        self.tab_widget.addTab(self._create_yaml_tab(), "📄 YAML")
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
        
        # 统计表格
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(3)
        self.stats_table.setHorizontalHeaderLabels(["类别名称", "数量", "占比"])
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setShowGrid(False)
        content_layout.addWidget(self.stats_table, 3)
        
        # 右侧概览 (无边框面板)
        overview_panel = QFrame()
        overview_panel.setObjectName("statsOverviewPanel")
        overview_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        overview_panel.setMinimumWidth(310)
        overview_panel.setMaximumWidth(350)
        
        overview_outer = QVBoxLayout(overview_panel)
        overview_outer.setContentsMargins(0, 0, 0, 0)
        overview_outer.setSpacing(10)
        
        # 概览标题
        overview_title = QLabel("📊 数据概览")
        overview_title.setObjectName("accentLabel")
        overview_title.setStyleSheet("font-size: 14px; padding: 4px 0;")
        overview_outer.addWidget(overview_title)
        
        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("statsOverviewSep")
        overview_outer.addWidget(sep)
        
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
        
        content_layout.addWidget(overview_panel, 1)
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
            右侧: 修改/删除标签 (高度撑满)
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setSpacing(10)
        
        # 路径输入组
        self.edit_path_group = PathInputGroup(
            show_image_dir=True,
            show_label_dir=True,
            show_classes=True,
            group_title="数据源路径",
        )
        tab_layout.addWidget(self.edit_path_group)
        
        # 下方内容区 (水平布局)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)
        
        # ========== 左列: 两个 GroupBox 垂直堆叠 ==========
        left_column = QVBoxLayout()
        left_column.setSpacing(10)
        
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
        gen_layout.addStretch()
        
        # 生成按钮 (右对齐)
        gen_btn_layout = QHBoxLayout()
        gen_btn_layout.addStretch()
        self.gen_empty_btn = QPushButton("📝 生成空标签")
        self.gen_empty_btn.setMinimumHeight(32)
        self.gen_empty_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.gen_empty_btn.setEnabled(False)
        gen_btn_layout.addWidget(self.gen_empty_btn)
        gen_layout.addLayout(gen_btn_layout)
        
        left_column.addWidget(gen_group)
        
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
        convert_layout.addStretch()
        
        # 转换按钮 (右对齐)
        convert_btn_layout = QHBoxLayout()
        convert_btn_layout.addStretch()
        self.convert_btn = QPushButton("🔄 执行转换")
        self.convert_btn.setMinimumHeight(32)
        self.convert_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.convert_btn.setProperty("class", "success")
        self.convert_btn.setEnabled(False)
        convert_btn_layout.addWidget(self.convert_btn)
        convert_layout.addLayout(convert_btn_layout)
        
        left_column.addWidget(convert_group)
        
        content_layout.addLayout(left_column, 1)  # Flex 1
        
        # ========== 右列: 修改/删除标签 (撑满高度) ==========
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
        self.old_name_input = QLineEdit()
        self.old_name_input.setPlaceholderText("原类别名称或 ID")
        form_layout.addRow("原类别/ID:", self.old_name_input)
        
        self._new_name_label = QLabel("新类别/ID:")
        self.new_name_input = QLineEdit()
        self.new_name_input.setPlaceholderText("新类别名称或 ID (删除时留空)")
        form_layout.addRow(self._new_name_label, self.new_name_input)
        right_layout.addLayout(form_layout)
        
        # 备份选项
        self.backup_check = QCheckBox("修改前备份原文件 (.bak)")
        self.backup_check.setChecked(True)
        right_layout.addWidget(self.backup_check)
        
        right_layout.addStretch()
        
        # 执行按钮 (右对齐)
        btn_layout2 = QHBoxLayout()
        btn_layout2.addStretch()
        self.modify_btn = QPushButton("⚡ 执行修改")
        self.modify_btn.setMinimumHeight(35)
        self.modify_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.modify_btn.setEnabled(False)
        btn_layout2.addWidget(self.modify_btn)
        right_layout.addLayout(btn_layout2)
        
        content_layout.addWidget(right_group, 1)  # Flex 1
        
        tab_layout.addLayout(content_layout, 1)  # 拉伸填充
        
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
        
        # ========== 左侧: 控制区 (Flex 1) ==========
        # 使用 QScrollArea 防止内容挤压
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
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
        
        left_layout.addWidget(param_group)
        
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
        
        left_layout.addWidget(output_group)
        left_layout.addStretch()
        
        left_scroll.setWidget(left_column)
        content_layout.addWidget(left_scroll, 1)  # Flex 1
        
        # ========== 右侧: 执行详情 (Flex 2) ==========
        right_group = QGroupBox("执行详情")
        right_layout = QVBoxLayout(right_group)
        
        self.split_log = QTextEdit()
        self.split_log.setReadOnly(True)
        self.split_log.setObjectName("terminalOutput")
        self.split_log.setPlaceholderText("执行日志将在此显示...")
        right_layout.addWidget(self.split_log)
        
        # 清空日志按钮
        clear_row = QHBoxLayout()
        clear_row.addStretch()
        clear_log_btn = QPushButton("清空")
        clear_log_btn.setFixedWidth(60)
        clear_log_btn.clicked.connect(self.split_log.clear)
        clear_row.addWidget(clear_log_btn)
        right_layout.addLayout(clear_row)
        
        content_layout.addWidget(right_group, 2)  # Flex 2
        
        tab_layout.addLayout(content_layout, 1)  # 拉伸填充
        
        return tab
    
    def _create_yaml_tab(self) -> QWidget:
        """
        创建 YAML 生成 Tab (左右分栏布局)
        
        左侧: 路径配置 (Train/Val/Output)
        右侧: 类别列表 (可编辑)
        """
        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        main_layout.setSpacing(10)
        
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
        # 允许垂直扩展
        self.classes_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_layout.addWidget(self.classes_edit)
        
        content_layout.addWidget(right_group, 2)  # Flex 2
        
        main_layout.addLayout(content_layout, 1)  # 拉伸填充
        
        # ========== 保存按钮 (右对齐) ==========
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()  # 推到右侧
        self.save_yaml_btn = QPushButton("💾 保存 YAML 配置")
        self.save_yaml_btn.setMinimumHeight(40)
        self.save_yaml_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.save_yaml_btn.setProperty("class", "success")
        btn_layout.addWidget(self.save_yaml_btn)
        main_layout.addLayout(btn_layout)
        
        return tab
    
    def _create_progress_zone(self) -> QWidget:
        """创建进度条区域 (仅进度条 + 状态 + 取消)"""
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
        """连接信号与槽"""
        # Tab 间路径同步 (实时同步)
        self.stats_path_group.paths_changed.connect(self._sync_paths_from_stats)
        self.edit_path_group.paths_changed.connect(self._sync_paths_from_edit)
        self.split_path_group.paths_changed.connect(self._sync_paths_from_split)
        self.edit_path_group.paths_changed.connect(self._update_edit_action_states)
        
        # Tab 1 - 统计
        self.scan_btn.clicked.connect(self._on_scan)
        self.categorize_btn.clicked.connect(self._on_categorize)
        
        # Tab 2 - 编辑
        self.gen_empty_btn.clicked.connect(self._on_generate_empty)
        self.modify_btn.clicked.connect(self._on_modify_labels)
        self.remove_radio.toggled.connect(self._on_action_changed)
        self.convert_btn.clicked.connect(self._on_convert_format)
        
        # Tab 3 - 划分
        self.ratio_slider.valueChanged.connect(self._on_ratio_changed)
        self.output_browse_btn.clicked.connect(self._on_browse_output_dir)
        self.split_btn.clicked.connect(self._on_split)
        
        # Tab 4 - YAML (所有浏览按钮)
        self.train_browse_btn.clicked.connect(self._on_browse_train)
        self.val_browse_btn.clicked.connect(self._on_browse_val)
        self.yaml_browse_btn.clicked.connect(self._on_browse_yaml)
        self.save_yaml_btn.clicked.connect(self._on_save_yaml)
        
        # 取消按钮
        self.cancel_btn.clicked.connect(self._on_cancel)
        
        self._update_edit_action_states()
    
    # ============================================================
    # 路径同步
    # ============================================================
    
    def _sync_paths_from_stats(self) -> None:
        """从统计 Tab 同步路径到其他 Tab"""
        paths = self.stats_path_group.get_all_paths()
        self.edit_path_group.set_all_paths(paths, emit_signal=False)
        self.split_path_group.set_all_paths(paths, emit_signal=False)
        self._update_edit_action_states()
        # 自动设置输出目录
        if paths.get("image_dir"):
            img_path = Path(paths["image_dir"])
            if img_path.exists():
                default_output = img_path.parent / f"{img_path.name}_split"
                self.output_dir_input.setText(str(default_output))
    
    def _sync_paths_from_edit(self) -> None:
        """从编辑 Tab 同步路径到其他 Tab"""
        paths = self.edit_path_group.get_all_paths()
        self.stats_path_group.set_all_paths(paths, emit_signal=False)
        self.split_path_group.set_all_paths(paths, emit_signal=False)
        self._update_edit_action_states()
    
    def _sync_paths_from_split(self) -> None:
        """从划分 Tab 同步路径到其他 Tab"""
        paths = self.split_path_group.get_all_paths()
        self.stats_path_group.set_all_paths(paths, emit_signal=False)
        self.edit_path_group.set_all_paths(paths, emit_signal=False)
        self._update_edit_action_states()

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
        """根据当前路径和任务状态更新编辑按钮可用性"""
        img_path = self.edit_path_group.get_image_dir()
        has_image_dir = bool(img_path and img_path.exists())
        is_busy = bool(self._worker and self._worker.isRunning())
        enabled = has_image_dir and not is_busy
        
        self.gen_empty_btn.setEnabled(enabled)
        self.convert_btn.setEnabled(enabled)
        self.modify_btn.setEnabled(enabled)
    
    # ============================================================
    # 槽函数
    # ============================================================
    
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
        
        # 更新共享状态 -> Tab 4
        self.detected_classes = result.classes
        self.classes_edit.setPlainText("\n".join(result.classes))
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
        
        self._start_worker(
            lambda: self._handler.generate_missing_labels(
                img_path,
                label_format,
                label_dir=label_path,
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=lambda count: self.log_message.emit(f"已生成 {count} 个空标签文件"),
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
        
        # 优先使用当前 classes.txt
        classes = None
        classes_txt = self.edit_path_group.get_classes_path()
        if classes_txt and classes_txt.exists():
            classes = self._handler.load_classes_txt(classes_txt)
        elif self.detected_classes:
            classes = self.detected_classes
        
        self._start_worker(
            lambda: self._handler.convert_format(
                dataset_root,
                to_xml=to_xml,
                classes=classes,
                label_dir=label_path,
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=lambda count: self.log_message.emit(f"格式转换完成: 成功 {count} 个文件"),
        )
    
    @Slot()
    def _on_modify_labels(self) -> None:
        """修改标签"""
        # 从编辑 Tab 的 PathInputGroup 读取路径
        img_path = self.edit_path_group.get_image_dir()
        if not img_path:
            self.log_message.emit("请先选择图片目录")
            return
        
        if not img_path.exists():
            self.log_message.emit(f"图片目录不存在: {img_path}")
            return
        
        old_value = self.old_name_input.text().strip()
        if not old_value:
            self.log_message.emit("请输入原类别名称或 ID")
            return
        
        action = ModifyAction.REPLACE if self.replace_radio.isChecked() else ModifyAction.REMOVE
        new_value = self.new_name_input.text().strip()
        
        if action == ModifyAction.REPLACE and not new_value:
            self.log_message.emit("替换模式下必须输入新类别名称或 ID")
            return
        
        # 优先使用标签目录，如果未设置则回退到图片目录
        label_path = self.edit_path_group.get_label_dir()
        dataset_root = self._resolve_dataset_root(img_path, label_path)
        search_dir = label_path if label_path and label_path.exists() else dataset_root
        
        # classes.txt
        classes_txt = self.edit_path_group.get_classes_path()
        
        self._start_worker(
            lambda: self._handler.modify_labels(
                search_dir,
                action,
                old_value,
                new_value,
                backup=self.backup_check.isChecked(),
                classes_txt=classes_txt,
                interrupt_check=self._worker.is_interrupted if self._worker else lambda: False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=lambda count: self.log_message.emit(f"已修改 {count} 个标签文件"),
        )
    
    @Slot(bool)
    def _on_action_changed(self, checked: bool) -> None:
        """操作类型切换: 删除模式时隐藏新名称输入框和标签"""
        # checked = True 表示删除模式被选中
        self.new_name_input.setVisible(not checked)
        self.new_name_input.setEnabled(not checked)
        self._new_name_label.setVisible(not checked)
    
    @Slot(int)
    def _on_ratio_changed(self, value: int) -> None:
        """比例滑块变化"""
        self.ratio_label.setText(f"训练: {value}% | 验证: {100 - value}%")
    
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
        
        # 清空 split_log 准备新的日志
        self.split_log.clear()
        
        # 创建只发送到本地 split_log 的回调 (文件操作日志)
        def split_log_callback(msg: str):
            # 判断是系统消息还是文件操作
            if "→" in msg or "⇢" in msg:
                # 文件操作 -> 只发送到本地面板
                QMetaObject.invokeMethod(
                    self.split_log, "append", Qt.ConnectionType.QueuedConnection, Q_ARG(str, msg)
                )
            else:
                # 系统消息 -> 发送到全局日志 + 本地面板
                self._emit_message(msg)
                QMetaObject.invokeMethod(
                    self.split_log, "append", Qt.ConnectionType.QueuedConnection, Q_ARG(str, f"[系统] {msg}")
                )
        
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
                message_callback=split_log_callback,
            ),
            on_finished=self._on_split_finished,
        )
    
    def _on_split_finished(self, result: SplitResult) -> None:
        """划分完成回调"""
        self.split_paths = {
            "train": result.train_path,
            "val": result.val_path,
        }
        
        # 自动填充 Tab 4
        self.train_path_input.setText(result.train_path)
        self.val_path_input.setText(result.val_path)
        
        # 自动设置 YAML 输出路径 (从划分 Tab 的图片目录读取)
        img_path = self.split_path_group.get_image_dir()
        if img_path:
            self.yaml_output_input.setText(str(img_path / "data.yaml"))
        
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
            self._worker.finished.connect(on_finished)
        
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
    
    def _set_ui_busy(self, busy: bool) -> None:
        """设置 UI 忙碌状态"""
        self.cancel_btn.setEnabled(busy)
        self.scan_btn.setEnabled(not busy)
        self.categorize_btn.setEnabled(not busy)
        self.split_btn.setEnabled(not busy)
        self.save_yaml_btn.setEnabled(not busy)
        
        if busy:
            self.gen_empty_btn.setEnabled(False)
            self.convert_btn.setEnabled(False)
            self.modify_btn.setEnabled(False)
        else:
            self._update_edit_action_states()
        
        if not busy:
            self.progress_bar.setValue(0)
            self.status_label.setText("就绪")
