"""
_models.py - 数据类型定义
============================================

包含所有枚举、数据类（dataclass）类型定义。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from utils.constants import IMAGE_EXTENSIONS, LABEL_EXTENSIONS  # noqa: F401
from utils.file_utils import get_unique_dir as _get_unique_dir  # noqa: F401




# ============================================================
# 数据类型定义
# ============================================================

class LabelFormat(Enum):
    """标签格式枚举"""
    TXT = auto()   # YOLO TXT 格式
    XML = auto()   # Pascal VOC XML 格式


class SplitMode(Enum):
    """数据集划分模式"""
    MOVE = auto()      # 物理移动文件 (剪切)
    COPY = auto()      # 物理复制文件 (推荐，更安全)
    INDEX = auto()     # 生成索引文件 (txt)


class ModifyAction(Enum):
    """标签修改动作"""
    REPLACE = auto()   # 替换类别
    REMOVE = auto()    # 删除类别


@dataclass
class ScanResult:
    """
    数据集扫描结果

    Attributes:
        total_images: 图片总数
        labeled_images: 有标签的图片数
        missing_labels: 缺失标签的图片路径列表
        empty_labels: 空标签文件数
        class_stats: 类别统计 {类别名: 数量}
        classes: 检测到的类别列表 (有序)
        label_format: 检测到的标签格式
    """
    total_images: int = 0
    labeled_images: int = 0
    missing_labels: list[Path] = field(default_factory=list)
    empty_labels: int = 0
    class_stats: dict[str, int] = field(default_factory=dict)
    classes: list[str] = field(default_factory=list)
    label_format: Optional[LabelFormat] = None


@dataclass
class SplitResult:
    """
    数据集划分结果

    Attributes:
        train_path: 训练集路径 (文件夹或 txt 索引)
        val_path: 验证集路径 (文件夹或 txt 索引)
        train_count: 训练集数量
        val_count: 验证集数量
    """
    train_path: str = ""
    val_path: str = ""
    train_count: int = 0
    val_count: int = 0


@dataclass
class AugmentConfig:
    """Offline dataset augmentation settings."""

    copies_per_image: int = 1
    include_original: bool = True
    seed: int = 42
    mode: str = "random"
    fixed_include_individual: bool = True
    fixed_include_combo: bool = True
    enable_horizontal_flip: bool = False
    enable_vertical_flip: bool = False
    enable_rotate: bool = False
    rotate_mode: str = "random"
    rotate_degrees: float = 15.0
    enable_brightness: bool = False
    brightness_strength: float = 0.2
    enable_contrast: bool = False
    contrast_strength: float = 0.25
    enable_color: bool = False
    color_strength: float = 0.25
    enable_noise: bool = False
    noise_strength: float = 0.08
    enable_hue: bool = False
    hue_degrees: float = 12.0
    enable_sharpness: bool = False
    sharpness_strength: float = 0.4
    enable_blur: bool = False
    blur_radius: float = 1.2

    def geometric_candidates(self) -> list[str]:
        ops: list[str] = []
        if self.enable_horizontal_flip:
            ops.append("flip_lr")
        if self.enable_vertical_flip:
            ops.append("flip_ud")
        if self.enable_rotate and self.rotate_degrees > 0:
            ops.append("rotate")
        return ops

    def photometric_candidates(self) -> list[str]:
        ops: list[str] = []
        if self.enable_brightness and self.brightness_strength > 0:
            ops.append("brightness")
        if self.enable_contrast and self.contrast_strength > 0:
            ops.append("contrast")
        if self.enable_color and self.color_strength > 0:
            ops.append("color")
        if self.enable_noise and self.noise_strength > 0:
            ops.append("noise")
        if self.enable_hue and self.hue_degrees > 0:
            ops.append("hue")
        if self.enable_sharpness and self.sharpness_strength > 0:
            ops.append("sharpness")
        if self.enable_blur and self.blur_radius > 0:
            ops.append("blur")
        return ops

    def enabled_operations(self) -> list[str]:
        return self.geometric_candidates() + self.photometric_candidates()

    def has_any_operation(self) -> bool:
        return bool(self.enabled_operations())

    def build_fixed_recipes(self) -> list["AugmentRecipe"]:
        operations = self.enabled_operations()
        recipes: list[AugmentRecipe] = []
        seen: set[tuple[str, ...]] = set()

        if self.fixed_include_individual:
            for operation in operations:
                recipe_ops = (operation,)
                if recipe_ops in seen:
                    continue
                recipes.append(AugmentRecipe(self.operation_slug(operation), recipe_ops))
                seen.add(recipe_ops)

        if self.fixed_include_combo and operations:
            recipe_ops = tuple(operations)
            if recipe_ops not in seen:
                recipe_name = "combo" if len(recipe_ops) > 1 else self.operation_slug(recipe_ops[0])
                recipes.append(AugmentRecipe(recipe_name, recipe_ops))
                seen.add(recipe_ops)

        return recipes

    @staticmethod
    def operation_slug(operation: str) -> str:
        mapping = {
            "flip_lr": "hflip",
            "flip_ud": "vflip",
            "rotate": "rotate",
            "brightness": "brightness",
            "contrast": "contrast",
            "color": "saturation",
            "noise": "noise",
            "hue": "hue",
            "sharpness": "sharpness",
            "blur": "blur",
        }
        return mapping.get(operation, operation)


@dataclass(frozen=True)
class AugmentRecipe:
    """A deterministic augmentation recipe used by fixed mode."""

    name: str
    operations: tuple[str, ...]


@dataclass(frozen=True)
class AppliedGeometryOp:
    """A concrete geometric transform applied to one augmented sample."""

    kind: str
    value: float = 0.0


@dataclass
class AugmentResult:
    """数据增强结果"""

    output_dir: str = ""
    source_images: int = 0
    copied_originals: int = 0
    augmented_images: int = 0
    label_files_written: int = 0
    skipped_images: int = 0


@dataclass
class ValidateResult:
    """
    标签校验结果

    Attributes:
        total_labels: 扫描的标签文件总数
        coord_errors: 坐标越界的文件列表 [(文件路径, 行号/对象名, 原因)]
        class_errors: 类别无效的文件列表 [(文件路径, 行号/对象名, 原因)]
        format_errors: 格式错误的文件列表 [(文件路径, 原因)]
        orphan_labels: 孤立标签文件列表 (无对应图片)
    """
    total_labels: int = 0
    coord_errors: list[tuple[Path, str, str]] = field(default_factory=list)
    class_errors: list[tuple[Path, str, str]] = field(default_factory=list)
    format_errors: list[tuple[Path, str]] = field(default_factory=list)
    orphan_labels: list[Path] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """是否存在任何问题"""
        return bool(self.coord_errors or self.class_errors
                    or self.format_errors or self.orphan_labels)

    @property
    def issue_count(self) -> int:
        """问题总数"""
        return (len(self.coord_errors) + len(self.class_errors)
                + len(self.format_errors) + len(self.orphan_labels))
