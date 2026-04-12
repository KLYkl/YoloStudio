"""
_tabs_stats.py - StatsTabMixin: 统计 Tab UI + 逻辑
============================================
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.data_handler import ScanResult


class StatsTabMixin:
    """统计 Tab 的 UI 构建 + 槽函数"""

    def _create_stats_tab(self) -> QWidget:
        """创建统计 Tab"""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        # 用 QStackedWidget 切换空状态提示 / 结果视图
        self._stats_stack = QStackedWidget()

        # ===== Page 0: 空状态引导 =====
        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setContentsMargins(40, 0, 40, 0)
        empty_layout.addStretch(2)

        hint_title = QLabel("尚未扫描数据集")
        hint_title.setObjectName("emptyStateTitle")
        hint_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(hint_title)

        empty_layout.addSpacing(8)

        hint_desc = QLabel(
            "在上方设置图片目录，然后点击下方「扫描数据集」\n"
            "即可查看类别分布、标签覆盖率等统计信息"
        )
        hint_desc.setObjectName("emptyStateDesc")
        hint_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_desc.setWordWrap(True)
        empty_layout.addWidget(hint_desc)

        empty_layout.addStretch(3)

        self._stats_stack.addWidget(empty_page)

        # ===== Page 1: 结果视图 =====
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 顶部: 数据概览 (横排卡片)
        overview_grid = QGridLayout()
        overview_grid.setHorizontalSpacing(6)
        overview_grid.setVerticalSpacing(6)

        overview_items = [
            ("total_images", "图片总数", "blue"),
            ("labeled_images", "有标签图片", "green"),
            ("missing_labels", "缺失标签", "orange"),
            ("empty_labels", "空标签", "yellow"),
            ("class_count", "类别数", "purple"),
            ("total_objects", "目标总数", "blue"),
            ("missing_ratio", "缺失占比", "red"),
            ("empty_ratio", "空标签占比", "yellow"),
        ]

        for index, (key, title, accent_key) in enumerate(overview_items):
            card = self._create_stats_overview_card(title, key, accent_key)
            overview_grid.addWidget(card, index // 4, index % 4)

        layout.addLayout(overview_grid)

        # 下方: 类别统计表 (全宽)
        stats_group = QGroupBox("类别统计")
        stats_group_layout = QVBoxLayout(stats_group)
        stats_group_layout.setContentsMargins(4, 4, 4, 4)

        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(3)
        self.stats_table.setHorizontalHeaderLabels(["类别名称", "数量", "占比"])
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.stats_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setShowGrid(False)
        stats_group_layout.addWidget(self.stats_table)

        layout.addWidget(stats_group, 1)

        scroll_area.setWidget(scroll_content)
        self._stats_stack.addWidget(scroll_area)

        # 默认显示空状态
        self._stats_stack.setCurrentIndex(0)
        tab_layout.addWidget(self._stats_stack, 1)

        # 按钮区域 (底部) — 始终可见
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(4, 6, 10, 4)
        btn_layout.setSpacing(10)

        btn_layout.addStretch()

        self.scan_btn = QPushButton("🔍 扫描数据集")
        self.scan_btn.setMinimumHeight(28)
        self.scan_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn_layout.addWidget(self.scan_btn)

        tab_layout.addLayout(btn_layout)

        return tab

    def _create_stats_overview_card(self, title: str, key: str, accent_key: str = "blue") -> QFrame:
        """创建带彩色指示条的统计概览卡片

        Args:
            title: 卡片标题文本
            key: 用于后续更新值的唯一键
            accent_key: 颜色键 (blue/green/orange/yellow/purple/red)，
                         对应全局 QSS 中 [accent="xxx"] 选择器
        """
        card = QFrame()
        card.setObjectName("statsOverviewCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card.setMinimumHeight(56)

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 12, 0)
        card_layout.setSpacing(0)

        # 左侧彩色指示条 — 颜色由全局 QSS [accent="xxx"] 控制
        accent_bar = QFrame()
        accent_bar.setObjectName("statsAccentBar")
        accent_bar.setFixedWidth(4)
        accent_bar.setProperty("accent", accent_key)
        card_layout.addWidget(accent_bar)

        # 右侧内容区
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(8, 6, 0, 6)
        text_layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("statsCardTitle")

        value_label = QLabel("--")
        value_label.setObjectName("statsCardValue")
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setProperty("accent", accent_key)

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

    # ==================== 槽函数 ====================

    @Slot()
    def _on_scan(self) -> None:
        """开始扫描数据集"""
        img_path = self.path_group.get_image_dir()
        if not img_path:
            self.log_message.emit("请先选择图片目录")
            return

        if not img_path.exists():
            self.log_message.emit(f"图片目录不存在: {img_path}")
            return

        label_path = self.path_group.get_label_dir()
        classes_txt = self.path_group.get_classes_path()

        self._scan_result = None
        self.stats_table.setRowCount(0)
        self._reset_stats_overview()

        self._start_worker(
            lambda: self._handler.scan_dataset(
                img_path,
                label_dir=label_path,
                classes_txt=classes_txt,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_scan_finished,
        )

    def _on_scan_finished(self, result: ScanResult) -> None:
        """扫描完成回调"""
        self._scan_result = result
        self._stats_stack.setCurrentIndex(1)
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

        # Shared state -> YAML panel
        self.detected_classes = result.classes
        self.classes_edit.setPlainText("\n".join(result.classes))
        self._refresh_edit_class_options()
        self._update_edit_action_states()

        summary = (
            f"图片总数: {result.total_images} | "
            f"有标签: {result.labeled_images} | "
            f"缺失标签: {len(result.missing_labels)} | "
            f"空标签: {result.empty_labels}"
        )
        self.log_message.emit(f"扫描完成: {summary}")

