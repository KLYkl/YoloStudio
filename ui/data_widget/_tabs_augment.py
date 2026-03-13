"""
_tabs_augment.py - AugmentTabMixin: 增强 Tab UI + 逻辑
============================================

重构版本：
- 左右分栏（QSplitter）：左设置 + 右实时预览
- YOLO 预设方案、按几何/色彩分类、图标 + 效果描述
- 实时预览：参数变化 300ms 防抖后自动刷新
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
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
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.data_handler import AugmentConfig, AugmentResult
from ui.focus_widgets import FocusDoubleSpinBox, FocusSpinBox


# ==================== 常量 ====================

PREVIEW_MAX_SIZE = 800  # 预览缩略图最长边限制


# ==================== 预设方案定义 ====================

PRESETS: dict[str, dict] = {
    "general": {
        "label": "🎯 通用检测",
        "tooltip": "常见目标检测场景：翻转 + 基础光照扰动",
        "config": {
            "hflip": True, "vflip": False,
            "rotate": False, "rotate_deg": 15.0,
            "brightness": True, "brightness_val": 0.20,
            "contrast": True, "contrast_val": 0.20,
            "color": True, "color_val": 0.20,
            "noise": False, "noise_val": 0.08,
            "hue": False, "hue_val": 12.0,
            "sharpness": False, "sharpness_val": 0.40,
            "blur": False, "blur_val": 1.2,
        },
    },
    "lighting": {
        "label": "☀️ 光照鲁棒",
        "tooltip": "室内外光照变化大的场景：强调亮度/对比度/色温变换",
        "config": {
            "hflip": True, "vflip": False,
            "rotate": False, "rotate_deg": 15.0,
            "brightness": True, "brightness_val": 0.40,
            "contrast": True, "contrast_val": 0.30,
            "color": False, "color_val": 0.25,
            "noise": True, "noise_val": 0.10,
            "hue": True, "hue_val": 15.0,
            "sharpness": False, "sharpness_val": 0.40,
            "blur": False, "blur_val": 1.2,
        },
    },
    "small_target": {
        "label": "🔬 小目标增强",
        "tooltip": "远距离小目标：旋转 + 模糊 + 噪点 + 锐度",
        "config": {
            "hflip": True, "vflip": False,
            "rotate": True, "rotate_deg": 10.0,
            "brightness": False, "brightness_val": 0.20,
            "contrast": False, "contrast_val": 0.25,
            "color": False, "color_val": 0.25,
            "noise": True, "noise_val": 0.06,
            "hue": False, "hue_val": 12.0,
            "sharpness": True, "sharpness_val": 0.30,
            "blur": True, "blur_val": 0.8,
        },
    },
    "all_on": {
        "label": "⚡ 全部开启",
        "tooltip": "启用所有增强方法，使用默认推荐值，最大数据多样性",
        "config": {
            "hflip": True, "vflip": True,
            "rotate": True, "rotate_deg": 15.0,
            "brightness": True, "brightness_val": 0.20,
            "contrast": True, "contrast_val": 0.25,
            "color": True, "color_val": 0.25,
            "noise": True, "noise_val": 0.08,
            "hue": True, "hue_val": 12.0,
            "sharpness": True, "sharpness_val": 0.40,
            "blur": True, "blur_val": 1.2,
        },
    },
}


# ==================== 增强项元数据 ====================

AUGMENT_ITEMS = {
    "hflip": {
        "icon": "↔️",
        "name": "水平翻转",
        "desc": "模拟相机左右视角变化，适合非方向敏感目标",
    },
    "vflip": {
        "icon": "↕️",
        "name": "垂直翻转",
        "desc": "模拟俯仰角度变化，适合航拍/俯视场景",
    },
    "rotate": {
        "icon": "🔄",
        "name": "旋转",
        "desc": "模拟目标倾斜或相机旋转，增加角度多样性",
    },
    "brightness": {
        "icon": "☀️",
        "name": "亮度",
        "desc": "模拟不同光照条件（强日光 / 阴天 / 室内昏暗）",
    },
    "contrast": {
        "icon": "🌗",
        "name": "对比度",
        "desc": "增强或减弱目标与背景的区分度",
    },
    "color": {
        "icon": "🎨",
        "name": "饱和度",
        "desc": "模拟颜色鲜艳或褪色场景，增强色彩鲁棒性",
    },
    "hue": {
        "icon": "🌈",
        "name": "色相偏移",
        "desc": "模拟不同色温和白平衡，适合室内/室外混合",
    },
    "noise": {
        "icon": "📡",
        "name": "噪点",
        "desc": "模拟低光/高ISO条件下的传感器噪声",
    },
    "sharpness": {
        "icon": "🔍",
        "name": "锐度",
        "desc": "模拟不同镜头锐利程度，增加清晰度变化",
    },
    "blur": {
        "icon": "💧",
        "name": "高斯模糊",
        "desc": "模拟失焦或运动模糊效果，增强模型鲁棒性",
    },
}


# ==================== 自适应图片 Label ====================

class _ScaledImageLabel(QLabel):
    """A QLabel that scales its pixmap to fit while keeping aspect ratio."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._source_pixmap: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(100, 80)

    def set_pixmap(self, pixmap: Optional[QPixmap]) -> None:
        """Set the source pixmap and trigger a scaled redraw."""
        self._source_pixmap = pixmap
        self._apply_scaled()

    def _apply_scaled(self) -> None:
        if self._source_pixmap is None or self._source_pixmap.isNull():
            self.clear()
            return
        scaled = self._source_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_scaled()


# ==================== Mixin ====================

class AugmentTabMixin:
    """增强 Tab 的 UI 构建 + 槽函数"""

    # ==================== UI 构建 ====================

    def _create_augment_tab(self) -> QWidget:
        """Build the augmentation tab with left-right split layout."""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setSpacing(0)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        # ── 主分栏 ──
        self._augment_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧: 设置面板
        left_panel = self._create_settings_panel()
        self._augment_splitter.addWidget(left_panel)

        # 右侧: 预览面板
        right_panel = self._create_preview_panel()
        self._augment_splitter.addWidget(right_panel)

        # 分栏比例: 左侧固定宽度，右侧占满剩余
        self._augment_splitter.setStretchFactor(0, 0)  # 左侧不拉伸
        self._augment_splitter.setStretchFactor(1, 1)  # 右侧占满
        self._augment_splitter.setSizes([380, 620])

        tab_layout.addWidget(self._augment_splitter, 1)

        # ── 预览防抖定时器 ──
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._refresh_preview)

        # ── 预览状态 ──
        self._preview_source_image: Optional[Image.Image] = None
        self._preview_image_path: Optional[Path] = None
        self._preview_dataset_images: list[Path] = []

        self._update_augment_mode_controls()
        return tab

    # ────────────────── 左侧: 设置面板 ──────────────────

    def _create_settings_panel(self) -> QWidget:
        """Create the left settings panel with all augmentation controls."""
        panel = QWidget()
        panel.setMinimumWidth(350)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(8)
        panel_layout.setContentsMargins(0, 0, 0, 0)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 4, 0, 0)
        content_layout.setSpacing(10)

        content_layout.addWidget(self._create_preset_section())
        content_layout.addWidget(self._create_geometry_section())
        content_layout.addWidget(self._create_photometric_section())
        content_layout.addWidget(self._create_output_section())
        content_layout.addStretch()

        scroll.setWidget(content)
        panel_layout.addWidget(scroll, 1)

        # 固定底栏: 开始增强按钮
        button_row = QHBoxLayout()
        button_row.setContentsMargins(4, 5, 4, 5)
        button_row.addStretch()
        self.augment_btn = QPushButton("🧪 开始增强")
        self.augment_btn.setMinimumHeight(35)
        self.augment_btn.setMinimumWidth(120)
        self.augment_btn.setProperty("class", "primary")
        self.augment_btn.setEnabled(False)
        button_row.addWidget(self.augment_btn)
        panel_layout.addLayout(button_row)

        return panel

    # ────────────────── 右侧: 预览面板 ──────────────────

    def _create_preview_panel(self) -> QWidget:
        """Create the right preview panel with original vs augmented view."""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(8)
        panel_layout.setContentsMargins(4, 4, 0, 4)

        # ── 工具栏 ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        toolbar.addWidget(QLabel("👁️ 增强预览"))

        toolbar.addStretch()

        self.augment_preview_shuffle_btn = QPushButton("🔀 换一张")
        self.augment_preview_shuffle_btn.setToolTip("从数据集随机选取另一张图片预览")
        self.augment_preview_shuffle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.augment_preview_shuffle_btn.setEnabled(False)
        toolbar.addWidget(self.augment_preview_shuffle_btn)

        panel_layout.addLayout(toolbar)

        # ── 图片对比区 ──
        compare_layout = QHBoxLayout()
        compare_layout.setSpacing(8)

        # 原图
        original_container = QVBoxLayout()
        original_container.setSpacing(4)
        original_title = QLabel("📷 原图")
        original_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        original_container.addWidget(original_title)

        self._preview_original_label = _ScaledImageLabel()
        self._preview_original_label.setObjectName("previewImageLabel")
        self._preview_original_label.setText("请先在上方设置图片目录")
        self._preview_original_label.setStyleSheet("""
            QLabel#previewImageLabel {
                background-color: #11111b;
                border: 1px solid #313244;
                border-radius: 6px;
                color: #6c7086;
                padding: 8px;
            }
        """)
        self._preview_original_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        original_container.addWidget(self._preview_original_label, 1)
        compare_layout.addLayout(original_container, 1)

        # 增强效果
        augmented_container = QVBoxLayout()
        augmented_container.setSpacing(4)
        augmented_title = QLabel("🎨 增强效果")
        augmented_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        augmented_container.addWidget(augmented_title)

        self._preview_augmented_label = _ScaledImageLabel()
        self._preview_augmented_label.setObjectName("previewImageLabel")
        self._preview_augmented_label.setText("调整左侧参数后自动预览")
        self._preview_augmented_label.setStyleSheet("""
            QLabel#previewImageLabel {
                background-color: #11111b;
                border: 1px solid #313244;
                border-radius: 6px;
                color: #6c7086;
                padding: 8px;
            }
        """)
        self._preview_augmented_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        augmented_container.addWidget(self._preview_augmented_label, 1)
        compare_layout.addLayout(augmented_container, 1)

        panel_layout.addLayout(compare_layout, 1)

        # ── 已应用增强项说明 ──
        self._preview_ops_label = QLabel("")
        self._preview_ops_label.setWordWrap(True)
        self._preview_ops_label.setObjectName("mutedLabel")
        self._preview_ops_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        panel_layout.addWidget(self._preview_ops_label)

        return panel

    # ────────────────── 预设方案区 ──────────────────

    def _create_preset_section(self) -> QGroupBox:
        """Create the YOLO preset buttons section."""
        group = QGroupBox("🎯 YOLO 预设方案")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        hint = QLabel("一键选择面向 YOLO 训练的常用增强组合，也可手动调整下方参数")
        hint.setWordWrap(True)
        hint.setObjectName("mutedLabel")
        layout.addWidget(hint)

        # 第一行: 3 个场景预设
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        # 第二行: 全部开启 + 全部关闭
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        preset_keys = list(PRESETS.keys())
        self._preset_buttons: dict[str, QPushButton] = {}
        for i, key in enumerate(preset_keys):
            preset = PRESETS[key]
            btn = QPushButton(preset["label"])
            btn.setToolTip(preset["tooltip"])
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            self._preset_buttons[key] = btn
            if i < 3:
                row1.addWidget(btn)
            else:
                row2.addWidget(btn)

        self.augment_clear_btn = QPushButton("🚫 全部关闭")
        self.augment_clear_btn.setToolTip("取消所有增强选项")
        self.augment_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        row2.addWidget(self.augment_clear_btn)

        row1.addStretch()
        row2.addStretch()
        layout.addLayout(row1)
        layout.addLayout(row2)
        return group

    # ────────────────── 几何变换区 ──────────────────

    def _create_geometry_section(self) -> QGroupBox:
        """Create the geometric transforms section."""
        group = QGroupBox("📐 几何变换")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        self.augment_hflip_check = self._make_augment_checkbox("hflip")
        layout.addWidget(self.augment_hflip_check)

        self.augment_vflip_check = self._make_augment_checkbox("vflip")
        layout.addWidget(self.augment_vflip_check)

        # 旋转行: checkbox + 方向 + 角度 (紧凑排列)
        self.augment_rotate_check = self._make_augment_checkbox("rotate")
        layout.addWidget(self.augment_rotate_check)

        rotate_params = QWidget()
        rp_layout = QHBoxLayout(rotate_params)
        rp_layout.setContentsMargins(24, 0, 0, 0)
        rp_layout.setSpacing(6)

        self.augment_rotate_random_radio = QRadioButton("随机")
        self.augment_rotate_clockwise_radio = QRadioButton("顺时针")
        self.augment_rotate_counterclockwise_radio = QRadioButton("逆时针")
        self.augment_rotate_random_radio.setChecked(True)
        self.augment_rotate_mode_group = QButtonGroup(self)
        self.augment_rotate_mode_group.addButton(self.augment_rotate_random_radio)
        self.augment_rotate_mode_group.addButton(self.augment_rotate_clockwise_radio)
        self.augment_rotate_mode_group.addButton(self.augment_rotate_counterclockwise_radio)
        rp_layout.addWidget(self.augment_rotate_random_radio)
        rp_layout.addWidget(self.augment_rotate_clockwise_radio)
        rp_layout.addWidget(self.augment_rotate_counterclockwise_radio)

        self.augment_rotate_degrees_spin = FocusDoubleSpinBox()
        self.augment_rotate_degrees_spin.setRange(0.0, 180.0)
        self.augment_rotate_degrees_spin.setValue(15.0)
        self.augment_rotate_degrees_spin.setSingleStep(1.0)
        self.augment_rotate_degrees_spin.setDecimals(1)
        self.augment_rotate_degrees_spin.setSuffix(" °")
        self.augment_rotate_degrees_spin.setFixedWidth(80)
        rp_layout.addWidget(self.augment_rotate_degrees_spin)

        self.augment_rotate_angle_hint = QLabel("±15.0°")
        self.augment_rotate_angle_hint.setObjectName("mutedLabel")
        rp_layout.addWidget(self.augment_rotate_angle_hint)
        rp_layout.addStretch()

        layout.addWidget(rotate_params)
        self._rotate_params_widget = rotate_params

        return group

    # ────────────────── 色彩与光照区 ──────────────────

    def _create_photometric_section(self) -> QGroupBox:
        """Create the color and lighting section (compact inline layout)."""
        group = QGroupBox("🎨 色彩与光照")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        # (key, check_attr, spin_attr, min, max, default, step, decimals, suffix)
        photometric_items = [
            ("brightness", "augment_brightness_check", "augment_brightness_spin",
             0.0, 1.0, 0.20, 0.05, 2, ""),
            ("contrast", "augment_contrast_check", "augment_contrast_spin",
             0.0, 1.0, 0.25, 0.05, 2, ""),
            ("color", "augment_color_check", "augment_color_spin",
             0.0, 1.0, 0.25, 0.05, 2, ""),
            ("hue", "augment_hue_check", "augment_hue_spin",
             0.0, 45.0, 12.0, 1.0, 1, " °"),
            ("noise", "augment_noise_check", "augment_noise_spin",
             0.0, 0.50, 0.08, 0.01, 2, ""),
            ("sharpness", "augment_sharpness_check", "augment_sharpness_spin",
             0.0, 1.5, 0.40, 0.05, 2, ""),
            ("blur", "augment_blur_check", "augment_blur_spin",
             0.0, 10.0, 1.20, 0.1, 1, " px"),
        ]

        for (key, check_attr, spin_attr,
             min_val, max_val, default, step, decimals, suffix) in photometric_items:

            # 每项一行: [checkbox 短名称] ─── [spin][suffix]
            row = QHBoxLayout()
            row.setSpacing(6)

            checkbox = self._make_augment_checkbox(key)
            setattr(self, check_attr, checkbox)
            row.addWidget(checkbox)

            row.addStretch()

            spin = FocusDoubleSpinBox()
            spin.setRange(min_val, max_val)
            spin.setValue(default)
            spin.setSingleStep(step)
            spin.setDecimals(decimals)
            if suffix:
                spin.setSuffix(suffix)
            spin.setFixedWidth(82)
            setattr(self, spin_attr, spin)
            row.addWidget(spin)

            layout.addLayout(row)

        return group

    # ────────────────── 输出设置区 ──────────────────

    def _create_output_section(self) -> QGroupBox:
        """Create the output settings section."""
        group = QGroupBox("⚙️ 输出设置")
        settings_layout = QVBoxLayout(group)
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
        self.augment_fixed_single_check.setToolTip("每种启用的增强方法单独生成一张图片")
        self.augment_fixed_combo_check = QCheckBox("组合增强")
        self.augment_fixed_combo_check.setChecked(True)
        self.augment_fixed_combo_check.setToolTip("将所有启用的增强方法组合在一起生成一张图片")
        fixed_mode_layout.addWidget(self.augment_fixed_single_check)
        fixed_mode_layout.addWidget(self.augment_fixed_combo_check)
        fixed_mode_layout.addStretch()
        settings_form.addRow("固定模式:", fixed_mode_row)

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

        output_row = QWidget()
        output_row_layout = QHBoxLayout(output_row)
        output_row_layout.setContentsMargins(0, 0, 0, 0)
        output_row_layout.setSpacing(8)
        output_row_layout.addWidget(QLabel("输出目录:"))
        self.augment_output_input = QLineEdit()
        self.augment_output_input.setPlaceholderText("增强结果保存位置（留空则自动生成）")
        output_row_layout.addWidget(self.augment_output_input, 1)
        self.augment_output_browse_btn = QPushButton("浏览")
        self.augment_output_browse_btn.setFixedWidth(68)
        output_row_layout.addWidget(self.augment_output_browse_btn)
        settings_layout.addWidget(output_row)

        self.augment_mode_hint_label = QLabel()
        self.augment_mode_hint_label.setWordWrap(True)
        self.augment_mode_hint_label.setObjectName("mutedLabel")
        settings_layout.addWidget(self.augment_mode_hint_label)

        return group

    # ────────────────── 通用增强项构建器 ──────────────────

    def _make_augment_checkbox(self, key: str) -> QCheckBox:
        """Create a checkbox with short icon+name label, description in tooltip."""
        meta = AUGMENT_ITEMS[key]
        checkbox = QCheckBox(f"{meta['icon']} {meta['name']}")
        checkbox.setToolTip(meta["desc"])
        return checkbox

    # ==================== 预览逻辑 ====================

    def _schedule_preview_update(self) -> None:
        """Schedule a debounced preview refresh (300ms)."""
        if hasattr(self, '_preview_timer') and self._preview_timer is not None:
            self._preview_timer.start()

    def _try_auto_load_preview(self) -> None:
        """Try to auto-load preview image when image directory changes."""
        img_dir = self.path_group.get_image_dir()
        if not img_dir or not img_dir.exists():
            self._preview_source_image = None
            self._preview_image_path = None
            self._preview_dataset_images = []
            self._preview_original_label.set_pixmap(None)
            self._preview_original_label.setText("请先在上方设置图片目录")
            self._preview_augmented_label.set_pixmap(None)
            self._preview_augmented_label.setText("调整左侧参数后自动预览")
            self._preview_ops_label.setText("")
            self.augment_preview_shuffle_btn.setEnabled(False)
            return

        # 扫描图片列表
        self._preview_dataset_images = self._handler._find_images(img_dir)
        if not self._preview_dataset_images:
            self._preview_original_label.set_pixmap(None)
            self._preview_original_label.setText("目录中无图片文件")
            self.augment_preview_shuffle_btn.setEnabled(False)
            return

        self.augment_preview_shuffle_btn.setEnabled(len(self._preview_dataset_images) > 1)

        # 自动加载第一张
        self._load_preview_image(self._preview_dataset_images[0])

    def _load_preview_image(self, path: Path) -> None:
        """Load an image for preview (resized to thumbnail)."""
        try:
            with Image.open(path) as img:
                source = ImageOps.exif_transpose(img)
                source.thumbnail((PREVIEW_MAX_SIZE, PREVIEW_MAX_SIZE), Image.Resampling.LANCZOS)
                self._preview_source_image = source.copy()
                self._preview_image_path = path

            # 显示原图
            self._preview_original_label.set_pixmap(self._pil_to_qpixmap(self._preview_source_image))
            self._schedule_preview_update()
        except Exception as exc:
            self._preview_original_label.set_pixmap(None)
            self._preview_original_label.setText(f"加载失败: {exc}")

    def _shuffle_preview_image(self) -> None:
        """Pick a random different image from the dataset."""
        if len(self._preview_dataset_images) < 2:
            return

        candidates = [p for p in self._preview_dataset_images if p != self._preview_image_path]
        if not candidates:
            return
        chosen = random.choice(candidates)
        self._load_preview_image(chosen)

    @Slot()
    def _refresh_preview(self) -> None:
        """Apply current augmentation settings to preview image and display."""
        if self._preview_source_image is None:
            return

        config = self._resolve_augment_config()
        operations = config.enabled_operations()

        if not operations:
            # 没有启用任何增强，显示原图
            self._preview_augmented_label.set_pixmap(
                self._pil_to_qpixmap(self._preview_source_image)
            )
            self._preview_ops_label.setText("未启用任何增强操作")
            return

        try:
            rng = random.Random(config.seed)
            augmented, _ = self._handler._apply_augmentation_recipe(
                self._preview_source_image,
                tuple(operations),
                config,
                rng,
            )

            self._preview_augmented_label.set_pixmap(self._pil_to_qpixmap(augmented))

            # 构建操作描述
            op_descriptions = []
            for op in operations:
                meta = AUGMENT_ITEMS.get(op.replace("flip_lr", "hflip").replace("flip_ud", "vflip"), {})
                icon = meta.get("icon", "")
                name = meta.get("name", op)
                op_descriptions.append(f"{icon} {name}")

            self._preview_ops_label.setText("已应用: " + "、".join(op_descriptions))

        except Exception as exc:
            self._preview_augmented_label.set_pixmap(None)
            self._preview_augmented_label.setText(f"预览失败: {exc}")
            self._preview_ops_label.setText("")

    @staticmethod
    def _pil_to_qpixmap(pil_image: Image.Image) -> QPixmap:
        """Convert a PIL Image to QPixmap."""
        rgb_image = pil_image.convert("RGB")
        data = rgb_image.tobytes("raw", "RGB")
        q_image = QImage(
            data,
            rgb_image.width,
            rgb_image.height,
            3 * rgb_image.width,
            QImage.Format.Format_RGB888,
        )
        return QPixmap.fromImage(q_image)

    # ==================== 增强状态管理 ====================

    def _update_augment_mode_controls(self) -> None:
        """Refresh mode-specific augmentation controls."""
        is_fixed_mode = self.augment_mode_combo.currentIndex() == 1
        self.augment_fixed_single_check.setEnabled(is_fixed_mode)
        self.augment_fixed_combo_check.setEnabled(is_fixed_mode)
        self.augment_count_hint.setText("份 / 每个方案" if is_fixed_mode else "份 / 每次随机采样")
        self.augment_mode_hint_label.setText(
            "固定生成：按勾选项稳定输出单项图和组合图，适合稀缺类别精确补样。"
            if is_fixed_mode
            else "随机生成：按启用项随机采样组合，更适合快速扩充数据量。"
        )

    def _update_augment_action_states(self) -> None:
        """Refresh button and control states for augmentation."""
        img_path = self.path_group.get_image_dir()
        has_image_dir = bool(img_path and img_path.exists())
        is_busy = bool(self._worker and self._worker.isRunning())
        is_fixed_mode = self.augment_mode_combo.currentIndex() == 1

        self._update_augment_mode_controls()

        rotate_enabled = self.augment_rotate_check.isChecked()
        self.augment_rotate_random_radio.setEnabled(rotate_enabled)
        self.augment_rotate_clockwise_radio.setEnabled(rotate_enabled)
        self.augment_rotate_counterclockwise_radio.setEnabled(rotate_enabled)
        self.augment_rotate_degrees_spin.setEnabled(rotate_enabled)
        self._rotate_params_widget.setEnabled(rotate_enabled)

        if rotate_enabled:
            deg = self.augment_rotate_degrees_spin.value()
            if self.augment_rotate_clockwise_radio.isChecked():
                self.augment_rotate_angle_hint.setText(f"顺时针 {deg:.1f}°")
            elif self.augment_rotate_counterclockwise_radio.isChecked():
                self.augment_rotate_angle_hint.setText(f"逆时针 {deg:.1f}°")
            else:
                self.augment_rotate_angle_hint.setText(f"范围 ±{deg:.1f}°")

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
            param_row = spin.parent()
            if param_row:
                param_row.setEnabled(checkbox.isChecked())

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

        self._update_preset_button_states()

        # 触发预览刷新
        self._schedule_preview_update()

    def _update_preset_button_states(self) -> None:
        """Update preset button checked state based on current selections."""
        current = self._get_current_augment_selections()
        for key, btn in self._preset_buttons.items():
            preset_cfg = PRESETS[key]["config"]
            btn.setChecked(current == preset_cfg)

    def _get_current_augment_selections(self) -> dict:
        """Get current augment checkbox/spin states as a dict."""
        return {
            "hflip": self.augment_hflip_check.isChecked(),
            "vflip": self.augment_vflip_check.isChecked(),
            "rotate": self.augment_rotate_check.isChecked(),
            "rotate_deg": self.augment_rotate_degrees_spin.value(),
            "brightness": self.augment_brightness_check.isChecked(),
            "brightness_val": self.augment_brightness_spin.value(),
            "contrast": self.augment_contrast_check.isChecked(),
            "contrast_val": self.augment_contrast_spin.value(),
            "color": self.augment_color_check.isChecked(),
            "color_val": self.augment_color_spin.value(),
            "noise": self.augment_noise_check.isChecked(),
            "noise_val": self.augment_noise_spin.value(),
            "hue": self.augment_hue_check.isChecked(),
            "hue_val": self.augment_hue_spin.value(),
            "sharpness": self.augment_sharpness_check.isChecked(),
            "sharpness_val": self.augment_sharpness_spin.value(),
            "blur": self.augment_blur_check.isChecked(),
            "blur_val": self.augment_blur_spin.value(),
        }

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

    # ==================== 预设方案 ====================

    def _apply_preset(self, preset_key: str) -> None:
        """Apply a preset configuration to all augmentation controls."""
        config = PRESETS[preset_key]["config"]
        self._apply_augment_selections(config)

    def _clear_all_augments(self) -> None:
        """Uncheck all augmentation checkboxes."""
        self.augment_hflip_check.setChecked(False)
        self.augment_vflip_check.setChecked(False)
        self.augment_rotate_check.setChecked(False)
        self.augment_brightness_check.setChecked(False)
        self.augment_contrast_check.setChecked(False)
        self.augment_color_check.setChecked(False)
        self.augment_noise_check.setChecked(False)
        self.augment_hue_check.setChecked(False)
        self.augment_sharpness_check.setChecked(False)
        self.augment_blur_check.setChecked(False)

    def _apply_augment_selections(self, config: dict) -> None:
        """Apply a config dict to the augment controls."""
        self.augment_hflip_check.setChecked(config.get("hflip", False))
        self.augment_vflip_check.setChecked(config.get("vflip", False))
        self.augment_rotate_check.setChecked(config.get("rotate", False))
        if "rotate_deg" in config:
            self.augment_rotate_degrees_spin.setValue(config["rotate_deg"])
        self.augment_brightness_check.setChecked(config.get("brightness", False))
        if "brightness_val" in config:
            self.augment_brightness_spin.setValue(config["brightness_val"])
        self.augment_contrast_check.setChecked(config.get("contrast", False))
        if "contrast_val" in config:
            self.augment_contrast_spin.setValue(config["contrast_val"])
        self.augment_color_check.setChecked(config.get("color", False))
        if "color_val" in config:
            self.augment_color_spin.setValue(config["color_val"])
        self.augment_noise_check.setChecked(config.get("noise", False))
        if "noise_val" in config:
            self.augment_noise_spin.setValue(config["noise_val"])
        self.augment_hue_check.setChecked(config.get("hue", False))
        if "hue_val" in config:
            self.augment_hue_spin.setValue(config["hue_val"])
        self.augment_sharpness_check.setChecked(config.get("sharpness", False))
        if "sharpness_val" in config:
            self.augment_sharpness_spin.setValue(config["sharpness_val"])
        self.augment_blur_check.setChecked(config.get("blur", False))
        if "blur_val" in config:
            self.augment_blur_spin.setValue(config["blur_val"])

    # ==================== 槽函数 ====================

    @Slot(int)
    def _on_augment_mode_changed(self, index: int) -> None:
        """React to random/fixed mode changes."""
        self._update_augment_action_states()

    @Slot()
    def _on_browse_augment_output_dir(self) -> None:
        """选择增强输出目录"""
        path = QFileDialog.getExistingDirectory(self, "选择增强输出目录")
        if path:
            self.augment_output_input.setText(path)

    @Slot()
    def _on_augment(self) -> None:
        """启动数据增强后台任务"""
        img_path = self.path_group.get_image_dir()
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

        label_path = self.path_group.get_label_dir()
        classes_txt = self.path_group.get_classes_path()
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
