"""
data_handler.py - 数据处理核心逻辑
============================================

职责:
    - 数据集扫描与统计
    - 空标签生成 (TXT/XML)
    - 标签修改/删除
    - 数据集划分
    - YAML 配置生成

架构要点:
    - DataHandler: 纯逻辑类，不依赖 Qt GUI 组件
    - DataWorker: QThread 封装，通过 Signal 通信
    - 所有耗时方法支持中断检查
"""

from __future__ import annotations

import math
import os
import random
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps
from PySide6.QtCore import QThread, Signal


# ============================================================
# 常量定义
# ============================================================

# 支持的图片格式
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# 支持的标签格式
LABEL_EXTENSIONS = {".txt", ".xml"}


# ============================================================
# 辅助函数
# ============================================================

def _get_unique_dir(base_path: Path) -> Path:
    """
    获取唯一的目录路径，如果目录已存在则添加数字后缀
    
    例如:
        - my_dir -> my_dir (如果不存在)
        - my_dir -> my_dir(1) (如果 my_dir 已存在)
        - my_dir -> my_dir(2) (如果 my_dir 和 my_dir(1) 都已存在)
    
    Args:
        base_path: 基础目录路径
    
    Returns:
        唯一的目录路径
    """
    if not base_path.exists():
        return base_path
    
    # 目录已存在，添加数字后缀
    parent = base_path.parent
    name = base_path.name
    
    counter = 1
    while True:
        new_path = parent / f"{name}({counter})"
        if not new_path.exists():
            return new_path
        counter += 1


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


# ============================================================
# 核心逻辑类
# ============================================================

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
    """??????????"""

    output_dir: str = ""
    source_images: int = 0
    copied_originals: int = 0
    augmented_images: int = 0
    label_files_written: int = 0
    skipped_images: int = 0


class DataHandler:
    """
    数据处理核心逻辑 (纯 Python，不依赖 Qt GUI)
    
    所有耗时方法接收 interrupt_check 参数，用于响应取消请求。
    """
    
    def __init__(self) -> None:
        """初始化数据处理器"""
        self._class_mapping: dict[int, str] = {}  # TXT 类别 ID -> 名称映射
    
    def _read_classes_txt(self, classes_file: Path) -> tuple[list[str], dict[int, str]]:
        """?? classes.txt????????? ID??????"""
        if not classes_file.exists():
            return [], {}

        classes = []
        with open(classes_file, "r", encoding="utf-8") as f:
            for line in f:
                name = line.strip()
                if name:
                    classes.append(name)

        return classes, {i: name for i, name in enumerate(classes)}

    def load_classes_txt(self, classes_file: Path) -> list[str]:
        """
        ?? classes.txt ??
        
        Args:
            classes_file: classes.txt ????
        
        Returns:
            ?????? (????)
        """
        classes, class_mapping = self._read_classes_txt(classes_file)
        self._class_mapping = class_mapping
        return classes
    
    def scan_dataset(
        self,
        img_dir: Path,
        label_dir: Optional[Path] = None,
        classes_txt: Optional[Path] = None,
        interrupt_check: Callable[[], bool] = lambda: False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        message_callback: Optional[Callable[[str], None]] = None,
    ) -> ScanResult:
        """
        扫描数据集，统计图片和标签信息
        
        Args:
            img_dir: 图片目录
            label_dir: 标签目录 (可选，留空则自动检测)
            classes_txt: classes.txt 路径 (可选，用于 TXT 标签类别映射)
            interrupt_check: 中断检查函数
            progress_callback: 进度回调 (current, total)
            message_callback: 消息回调
        
        Returns:
            ScanResult: 扫描结果
        """
        result = ScanResult()
        class_mapping: dict[int, str] = {}
        
        # 加载类别映射
        if classes_txt and classes_txt.exists():
            _, class_mapping = self._read_classes_txt(classes_txt)
            if message_callback:
                message_callback(f"已加载类别文件: {len(class_mapping)} 个类别")
        
        # 收集所有图片文件
        images = self._find_images(img_dir)
        result.total_images = len(images)
        
        if message_callback:
            msg = f"发现 {result.total_images} 张图片"
            if label_dir:
                msg += f"，标签目录: {label_dir.name}"
            else:
                msg += "，自动搜索标签..."
            message_callback(msg)
        
        # 扫描每张图片的标签
        for i, img_path in enumerate(images):
            if interrupt_check():
                if message_callback:
                    message_callback("扫描已取消")
                break
            
            # 查找标签: 优先使用指定目录
            if label_dir and label_dir.exists():
                label_path, label_format = self._find_label_in_dir(img_path, label_dir)
            else:
                label_path, label_format = self._find_label(img_path, img_dir.parent)
            
            if label_path is None:
                result.missing_labels.append(img_path)
            else:
                result.labeled_images += 1
                result.label_format = label_format
                
                # 解析标签内容
                classes_in_file = self._parse_label(label_path, label_format, class_mapping=class_mapping)
                
                if not classes_in_file:
                    result.empty_labels += 1
                else:
                    for cls in classes_in_file:
                        result.class_stats[cls] = result.class_stats.get(cls, 0) + 1
            
            if progress_callback:
                progress_callback(i + 1, result.total_images)
        
        # 提取有序类别列表
        result.classes = sorted(result.class_stats.keys())
        
        return result
    def generate_missing_labels(
        self,
        img_dir: Path,
        label_format: LabelFormat,
        label_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        interrupt_check: Callable[[], bool] = lambda: False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        message_callback: Optional[Callable[[str], None]] = None,
    ) -> int:
        """
        扫描缺失标签图片并生成空标签文件
        
        Args:
            img_dir: 图片目录
            label_format: 标签格式 (TXT/XML)
            label_dir: 标签目录 (可选)
            output_dir: 输出目录 (可选)
            interrupt_check: 中断检查函数
            progress_callback: 进度回调
            message_callback: 消息回调
        
        Returns:
            生成的标签文件数量
        """
        scan_result = self.scan_dataset(
            img_dir,
            label_dir=label_dir,
            interrupt_check=interrupt_check,
            progress_callback=progress_callback,
            message_callback=message_callback,
        )
        
        if interrupt_check():
            return 0
        
        if not scan_result.missing_labels:
            if message_callback:
                message_callback("没有需要生成标签的图片")
            return 0
        
        if message_callback:
            message_callback(
                f"找到 {len(scan_result.missing_labels)} 张缺失标签图片，开始生成空标签"
            )
        
        target_output_dir = output_dir
        if target_output_dir is None and label_dir and label_dir.exists():
            target_output_dir = label_dir

        return self.generate_empty_labels(
            scan_result.missing_labels,
            label_format,
            output_dir=target_output_dir,
            interrupt_check=interrupt_check,
            progress_callback=progress_callback,
            message_callback=message_callback,
        )

    def preview_generate_missing_labels(
        self,
        img_dir: Path,
        label_dir: Optional[Path] = None,
        interrupt_check: Callable[[], bool] = lambda: False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> dict[str, int]:
        """预检查缺失标签数量"""
        images = self._find_images(img_dir)
        total_images = len(images)
        missing_labels = 0
        
        for i, img_path in enumerate(images):
            if interrupt_check():
                break
            
            if label_dir and label_dir.exists():
                label_path, _ = self._find_label_in_dir(img_path, label_dir)
            else:
                label_path, _ = self._find_label(img_path, img_dir.parent)
            
            if label_path is None:
                missing_labels += 1
            
            if progress_callback:
                progress_callback(i + 1, total_images)
        
        return {
            "total_images": total_images,
            "missing_labels": missing_labels,
        }
    
    def _find_label_in_dir(self, img_path: Path, label_dir: Path) -> tuple[Optional[Path], Optional[LabelFormat]]:
        """
        在指定目录中查找图片对应的标签文件
        
        Args:
            img_path: 图片路径
            label_dir: 标签目录
        
        Returns:
            (标签路径, 格式) 或 (None, None)
        """
        stem = img_path.stem
        
        # XML 优先
        for ext, fmt in [(".xml", LabelFormat.XML), (".txt", LabelFormat.TXT)]:
            label_path = label_dir / (stem + ext)
            if label_path.exists():
                return label_path, fmt
        
        return None, None
    
    def generate_empty_labels(
        self,
        images: list[Path],
        label_format: LabelFormat,
        output_dir: Optional[Path] = None,
        interrupt_check: Callable[[], bool] = lambda: False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        message_callback: Optional[Callable[[str], None]] = None,
    ) -> int:
        """
        为图片生成空标签文件
        
        标签将保存到与 images 目录同级的 labels 目录中。
        例如: .../my_data/images/1.jpg -> .../my_data/labels/1.txt
        
        Args:
            images: 图片路径列表
            label_format: 标签格式 (TXT/XML)
            output_dir: 输出目录 (None 则自动检测 labels 同级目录)
            interrupt_check: 中断检查函数
            progress_callback: 进度回调
            message_callback: 消息回调
        
        Returns:
            生成的标签文件数量
        """
        count = 0
        total = len(images)
        ext = ".txt" if label_format == LabelFormat.TXT else ".xml"
        
        for i, img_path in enumerate(images):
            if interrupt_check():
                if message_callback:
                    message_callback("生成已取消")
                break
            
            # 确定输出路径
            if output_dir:
                label_path = output_dir / (img_path.stem + ext)
            else:
                # 查找或创建同级 labels 目录
                label_path = self._get_label_output_path(img_path, ext)

            # Another process may create the file after the scan; skip overwrite.
            if label_path.exists():
                if progress_callback:
                    progress_callback(i + 1, total)
                continue
            
            # 确保目录存在
            label_path.parent.mkdir(parents=True, exist_ok=True)
            
            if label_format == LabelFormat.TXT:
                # TXT: 空文件
                label_path.touch()
            else:
                # XML: 需要图片尺寸
                self._create_empty_xml(img_path, label_path)
            
            count += 1
            
            if progress_callback:
                progress_callback(i + 1, total)
        
        if message_callback:
            message_callback(f"已生成 {count} 个空标签文件")
        
        return count
    
    def _get_label_output_path(self, img_path: Path, ext: str) -> Path:
        """
        计算标签文件的输出路径 (智能路径选择)
        
        规则:
            - XML: 使用 Annotations/ (Pascal VOC 风格)
            - TXT: 使用 labels/ (YOLO 风格)
        
        Args:
            img_path: 图片路径
            ext: 标签文件扩展名 (.txt 或 .xml)
        
        Returns:
            标签文件路径
        """
        # 根据格式确定目标目录名
        if ext.lower() == ".xml":
            target_dir_name = "Annotations"
            source_dir_names = ["jpegimages", "images", "imgs"]
        else:
            target_dir_name = "labels"
            source_dir_names = ["images", "jpegimages", "imgs"]
        
        parts = list(img_path.parts)
        
        # 查找并替换源目录名
        found_idx = None
        for i, part in enumerate(parts):
            if part.lower() in source_dir_names:
                found_idx = i
                break
        
        if found_idx is not None:
            # 找到源目录，替换为目标目录
            parts[found_idx] = target_dir_name
            label_path = Path(*parts).with_suffix(ext)
        else:
            # 没有找到，在图片目录的同级创建目标目录
            parent = img_path.parent.parent
            target_dir = parent / target_dir_name
            label_path = target_dir / (img_path.stem + ext)
        
        return label_path
    
    def modify_labels(
        self,
        search_dir: Path,
        action: ModifyAction,
        old_value: str,
        new_value: str = "",
        backup: bool = True,
        classes_txt: Optional[Path] = None,
        image_dir: Optional[Path] = None,
        label_dir: Optional[Path] = None,
        interrupt_check: Callable[[], bool] = lambda: False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        message_callback: Optional[Callable[[str], None]] = None,
    ) -> int:
        """
        批量修改标签文件
        
        Args:
            search_dir: 标签搜索目录
            action: 修改动作 (REPLACE/REMOVE)
            old_value: 原始类别名/ID
            new_value: 新类别名/ID (仅 REPLACE 时使用)
            backup: 是否备份原文件
            classes_txt: classes.txt 路径 (可选，提供后可使用类别名称)
            interrupt_check: 中断检查函数
            progress_callback: 进度回调
            message_callback: 消息回调
        
        Returns:
            修改的文件数量
        """
        label_files = self._collect_modify_label_files(search_dir, image_dir=image_dir, label_dir=label_dir)
        modified_count = 0
        total = len(label_files)
        backup_count = 0
        
        if total == 0:
            if message_callback:
                message_callback("未找到可修改的标签文件")
            return 0
        
        # 加载类别映射 (TXT 替换需要)
        class_mapping: dict[int, str] = {}
        if classes_txt and classes_txt.exists():
            _, class_mapping = self._read_classes_txt(classes_txt)
        
        for i, label_path in enumerate(label_files):
            if interrupt_check():
                if message_callback:
                    message_callback("修改已取消")
                break
            
            if not label_path.exists():
                continue
            
            # 根据文件类型处理
            if label_path.suffix.lower() == ".xml":
                modified, tree = self._prepare_modified_xml(label_path, action, old_value, new_value)
                if modified and tree is not None:
                    if backup:
                        backup_path = self._get_unique_backup_path(label_path)
                        shutil.copy2(label_path, backup_path)
                        backup_count += 1
                    ET.indent(tree, space="    ")
                    self._write_xml_tree_atomic(label_path, tree)
            else:
                modified, new_lines = self._prepare_modified_txt(
                    label_path,
                    action,
                    old_value,
                    new_value,
                    class_mapping=class_mapping,
                )
                if modified and new_lines is not None:
                    if backup:
                        backup_path = self._get_unique_backup_path(label_path)
                        shutil.copy2(label_path, backup_path)
                        backup_count += 1
                    self._write_lines_atomic(label_path, new_lines)
            
            if modified:
                modified_count += 1
            
            if progress_callback:
                progress_callback(i + 1, total)
        
        if message_callback:
            message_callback(f"已修改 {modified_count} 个标签文件")
        
        if backup and message_callback and backup_count > 0:
                message_callback(
                    f"提示: 已创建 {backup_count} 个 .bak 备份文件，可手动清理"
                )
        
        return modified_count
    def preview_modify_labels(
        self,
        search_dir: Path,
        action: ModifyAction,
        old_value: str,
        new_value: str = "",
        classes_txt: Optional[Path] = None,
        image_dir: Optional[Path] = None,
        label_dir: Optional[Path] = None,
        interrupt_check: Callable[[], bool] = lambda: False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> dict[str, int]:
        """预检查标签修改影响范围"""
        label_files = self._collect_modify_label_files(search_dir, image_dir=image_dir, label_dir=label_dir)
        total = len(label_files)
        txt_files = 0
        xml_files = 0
        matched_files = 0
        matched_annotations = 0
        
        class_mapping: dict[int, str] = {}
        if classes_txt and classes_txt.exists():
            _, class_mapping = self._read_classes_txt(classes_txt)
        
        for i, label_path in enumerate(label_files):
            if interrupt_check():
                break
            
            if label_path.suffix.lower() == ".xml":
                xml_files += 1
                affected = self._count_xml_matches(label_path, old_value)
            else:
                txt_files += 1
                affected = self._count_txt_matches(label_path, old_value, class_mapping=class_mapping)
            
            if affected > 0:
                matched_files += 1
                matched_annotations += affected
            
            if progress_callback:
                progress_callback(i + 1, total)
        
        return {
            "total_label_files": total,
            "txt_files": txt_files,
            "xml_files": xml_files,
            "matched_files": matched_files,
            "matched_annotations": matched_annotations,
            "replace_mode": int(action == ModifyAction.REPLACE),
            "has_classes_txt": int(bool(classes_txt and classes_txt.exists())),
        }
    
    def split_dataset(
        self,
        img_dir: Path,
        label_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        ratio: float = 0.8,
        seed: int = 42,
        mode: SplitMode = SplitMode.COPY,
        ignore_orphans: bool = False,
        clear_output: bool = False,
        interrupt_check: Callable[[], bool] = lambda: False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        message_callback: Optional[Callable[[str], None]] = None,
    ) -> SplitResult:
        """
        划分数据集为训练集和验证集
        
        Args:
            img_dir: 图片目录
            label_dir: 标签目录 (可选，留空则自动检测)
            output_dir: 输出目录 (可选，默认为 img_dir 同级的 _split 目录)
            ratio: 训练集比例 (0.0-1.0)
            seed: 随机种子
            mode: 划分模式 (MOVE/COPY/INDEX)
            ignore_orphans: 是否忽略无标签图片
            clear_output: 是否清空目标目录
            interrupt_check: 中断检查函数
            progress_callback: 进度回调
            message_callback: 消息回调
        
        Returns:
            SplitResult: 划分结果
        """
        result = SplitResult()
        
        # 默认输出目录 (如果已存在则添加数字后缀)
        if output_dir is None:
            output_dir = _get_unique_dir(img_dir.parent / f"{img_dir.name}_split")
        
        # 收集所有图片
        images = self._find_images(img_dir)
        
        # 如果忽略无标签图片，过滤掉孤立图片
        if ignore_orphans:
            labeled_images = []
            for img in images:
                if label_dir and label_dir.exists():
                    label_path, _ = self._find_label_in_dir(img, label_dir)
                else:
                    label_path, _ = self._find_label(img, img_dir.parent)
                if label_path is not None:
                    labeled_images.append(img)
            if message_callback:
                skipped = len(images) - len(labeled_images)
                message_callback(f"忽略 {skipped} 张无标签图片")
            images = labeled_images
        
        total = len(images)
        
        if total == 0:
            if message_callback:
                message_callback("未找到符合条件的图片文件")
            return result
        
        # 随机打乱
        random.seed(seed)
        random.shuffle(images)
        
        # 划分
        split_idx = int(total * ratio)
        train_images = images[:split_idx]
        val_images = images[split_idx:]
        
        result.train_count = len(train_images)
        result.val_count = len(val_images)
        
        if message_callback:
            message_callback(f"划分比例: 训练集 {result.train_count}, 验证集 {result.val_count}")
            message_callback(f"输出目录: {output_dir}")
        
        if mode in (SplitMode.MOVE, SplitMode.COPY):
            result.train_path, result.val_path = self._split_files(
                img_dir, train_images, val_images,
                label_dir=label_dir,
                output_dir=output_dir,
                use_copy=(mode == SplitMode.COPY),
                clear_output=clear_output,
                interrupt_check=interrupt_check, 
                progress_callback=progress_callback, 
                message_callback=message_callback
            )
        else:
            result.train_path, result.val_path = self._split_index(
                output_dir, train_images, val_images, message_callback
            )
        
        return result
    
    def generate_yaml(
        self,
        train_path: str,
        val_path: str,
        classes: list[str],
        output_path: Path,
        message_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        生成 YOLO 训练 YAML 配置文件
        
        path 字段智能推断：
            - 两个绝对路径 → 取公共父目录，train/val 转为相对路径
            - 其他情况 → 使用 YAML 所在目录
        
        Args:
            train_path: 训练集路径 (文件夹或 txt 索引)
            val_path: 验证集路径 (文件夹或 txt 索引)
            classes: 类别名称列表
            output_path: YAML 输出路径
            message_callback: 消息回调
        
        Returns:
            是否成功
        """
        try:
            train_p = Path(train_path)
            val_p = Path(val_path)
            
            if train_p.is_absolute() and val_p.is_absolute():
                dataset_root = Path(os.path.commonpath([train_p, val_p]))
                train_path = str(train_p.relative_to(dataset_root))
                val_path = str(val_p.relative_to(dataset_root))
            else:
                dataset_root = output_path.parent
            
            yaml_content = {
                "path": str(dataset_root),
                "train": train_path,
                "val": val_path,
                "names": {i: name for i, name in enumerate(classes)},
            }
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(yaml_content, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            
            if message_callback:
                message_callback(f"YAML 配置已保存: {output_path}")
                message_callback(f"数据集根目录 (path): {dataset_root}")
            
            return True
            
        except Exception as e:
            if message_callback:
                message_callback(f"YAML 生成失败: {e}")
            return False
    
    def convert_format(
        self,
        root: Path,
        to_xml: bool = True,
        classes: Optional[list[str]] = None,
        label_dir: Optional[Path] = None,
        image_dir: Optional[Path] = None,
        interrupt_check: Callable[[], bool] = lambda: False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        message_callback: Optional[Callable[[str], None]] = None,
    ) -> int:
        """
        转换标签格式 (TXT ↔ XML)，输出到独立目录
        
        Args:
            root: 数据集根目录
            to_xml: True=TXT→XML, False=XML→TXT
            classes: 类别列表
            interrupt_check: 中断检查
            progress_callback: 进度回调
            message_callback: 消息回调
        
        Returns:
            转换成功的文件数量
        """
        converted = 0
        search_dir = label_dir if label_dir and label_dir.exists() else root
        
        if to_xml:
            # TXT → XML
            label_files = self.collect_label_files(search_dir, suffixes={".txt"})
            output_dir_name = "converted_labels_xml"
            target_ext = ".xml"
        else:
            # XML → TXT
            label_files = self.collect_label_files(search_dir, suffixes={".xml"})
            output_dir_name = "converted_labels_txt"
            target_ext = ".txt"
        
        total = len(label_files)
        if total == 0:
            if message_callback:
                message_callback("未找到可转换的标签文件")
            return 0
        
        # 创建输出目录 (如果已存在则添加数字后缀)
        output_dir = _get_unique_dir(root / output_dir_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if message_callback:
            direction = "TXT → XML" if to_xml else "XML → TXT"
            message_callback(f"开始转换 ({direction}): {total} 个文件")
            message_callback(f"输出目录: {output_dir}")
        
        # 构建类别映射
        class_to_id = {}
        id_to_class = {}
        if classes:
            for i, name in enumerate(classes):
                class_to_id[name] = i
                id_to_class[i] = name
        
        # 如果没有提供类别且要转为 TXT，先扫描所有 XML 获取类别
        if not to_xml and not classes:
            unique_names = set()
            for xml_file in label_files:
                try:
                    tree = ET.parse(xml_file)
                    for obj in tree.getroot().findall(".//object/name"):
                        if obj.text:
                            unique_names.add(obj.text.strip())
                except Exception:
                    pass
            sorted_names = sorted(unique_names)
            class_to_id = {name: i for i, name in enumerate(sorted_names)}
            if message_callback:
                message_callback(f"自动检测到 {len(sorted_names)} 个类别: {', '.join(sorted_names)}")
        
        failed_files: list[tuple[Path, str]] = []  # 收集失败的文件
        
        for i, label_path in enumerate(label_files):
            if interrupt_check():
                if message_callback:
                    message_callback("转换已取消")
                break
            
            try:
                # 计算输出路径
                try:
                    relative_path = label_path.relative_to(search_dir)
                except ValueError:
                    relative_path = Path(label_path.name)
                
                output_path = output_dir / relative_path.with_suffix(target_ext)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                if to_xml:
                    # TXT → XML
                    success = self._convert_txt_to_xml(
                        label_path,
                        id_to_class,
                        root,
                        output_path,
                        image_dir=image_dir,
                        label_dir=label_dir,
                    )
                else:
                    # XML → TXT
                    success = self._convert_xml_to_txt(label_path, class_to_id, output_path)
                
                if success:
                    converted += 1
                else:
                    failed_files.append((label_path, "转换失败"))
            except Exception as e:
                failed_files.append((label_path, str(e)))
            
            if progress_callback:
                progress_callback(i + 1, total)
        
        if message_callback:
            message_callback(f"转换完成: 成功 {converted}/{total}")
            if failed_files:
                message_callback(f"失败 {len(failed_files)} 个文件")
            message_callback(f"文件已保存到: {output_dir}")
        
        return converted

    def preview_convert_format(
        self,
        root: Path,
        to_xml: bool = True,
        label_dir: Optional[Path] = None,
        interrupt_check: Callable[[], bool] = lambda: False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> dict[str, str | int]:
        """预检查格式互转范围"""
        search_dir = label_dir if label_dir and label_dir.exists() else root
        source_suffix = ".txt" if to_xml else ".xml"
        candidates = [
            path for path in search_dir.rglob("*")
            if path.is_file() and path.suffix.lower() == source_suffix
        ]
        total_candidates = len(candidates)
        label_files: list[Path] = []
        
        for i, path in enumerate(candidates):
            if interrupt_check():
                break
            
            is_valid = (
                self._is_txt_label_file(path)
                if source_suffix == ".txt"
                else self._is_xml_label_file(path)
            )
            if is_valid:
                label_files.append(path)
            
            if progress_callback:
                progress_callback(i + 1, total_candidates)
        
        return {
            "total_labels": len(label_files),
            "txt_files": sum(1 for path in label_files if path.suffix.lower() == ".txt"),
            "xml_files": sum(1 for path in label_files if path.suffix.lower() == ".xml"),
            "source_type": "TXT" if to_xml else "XML",
            "target_type": "XML" if to_xml else "TXT",
            "output_dir_name": "converted_labels_xml" if to_xml else "converted_labels_txt",
        }

    def collect_label_class_options(
        self,
        search_dir: Path,
        classes_txt: Optional[Path] = None,
    ) -> list[str]:
        """收集标签中的类别选项，用于下拉框"""
        if classes_txt and classes_txt.exists():
            classes, _ = self._read_classes_txt(classes_txt)
            return classes
        
        class_values: set[str] = set()
        for label_path in self.collect_label_files(search_dir):
            label_format = LabelFormat.XML if label_path.suffix.lower() == ".xml" else LabelFormat.TXT
            class_values.update(self._parse_label_ids(label_path, label_format, class_mapping={}))
        
        numeric_values = sorted(
            (value for value in class_values if value.isdigit()),
            key=lambda value: int(value),
        )
        text_values = sorted(value for value in class_values if not value.isdigit())
        return numeric_values + text_values
    def collect_label_files(
        self,
        root: Path,
        suffixes: Optional[set[str]] = None,
    ) -> list[Path]:
        """递归收集有效标签文件"""
        if not root.exists():
            return []
        
        allowed_suffixes = {suffix.lower() for suffix in (suffixes or LABEL_EXTENSIONS)}
        label_files: list[Path] = []
        
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            
            suffix = path.suffix.lower()
            if suffix not in allowed_suffixes:
                continue
            
            if suffix == ".txt" and self._is_txt_label_file(path):
                label_files.append(path)
            elif suffix == ".xml" and self._is_xml_label_file(path):
                label_files.append(path)
        
        return sorted(label_files)

    def _collect_modify_label_files(
        self,
        search_dir: Path,
        image_dir: Optional[Path] = None,
        label_dir: Optional[Path] = None,
    ) -> list[Path]:
        """Collect the label files that should be modified for the current scope."""
        if image_dir and image_dir.exists() and not (label_dir and label_dir.exists()):
            return self.collect_image_label_files(image_dir)

        return self.collect_label_files(search_dir)

    def collect_image_label_files(
        self,
        img_dir: Path,
        label_dir: Optional[Path] = None,
    ) -> list[Path]:
        """Collect label files matched to images to avoid touching derived directories."""
        if not img_dir.exists():
            return []

        label_files: list[Path] = []
        seen: set[Path] = set()
        for img_path in self._find_images(img_dir):
            if label_dir and label_dir.exists():
                label_path, _ = self._find_label_in_dir(img_path, label_dir)
            else:
                label_path, _ = self._find_label(img_path, img_dir.parent)

            if label_path and label_path.exists() and label_path not in seen:
                seen.add(label_path)
                label_files.append(label_path)

        return sorted(label_files)
    
    def _convert_txt_to_xml(
        self,
        txt_path: Path,
        id_to_class: dict,
        root: Path,
        output_path: Path,
        image_dir: Optional[Path] = None,
        label_dir: Optional[Path] = None,
    ) -> bool:
        """将 TXT 标签转换为 XML"""
        # 查找对应的图片
        img_path = self._find_image_for_label(
            txt_path,
            root,
            image_dir=image_dir,
            label_dir=label_dir,
        )
        if not img_path or not img_path.exists():
            return False
        
        # 读取图片尺寸
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                depth = len(img.getbands())
        except Exception:
            return False
        
        # 解析 TXT
        objects = []
        with open(txt_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 5:
                    class_id = int(parts[0])
                    x_c, y_c, w, h = map(float, parts[1:5])
                    
                    # 归一化 → 绝对坐标
                    xmin = int((x_c - w / 2) * width)
                    ymin = int((y_c - h / 2) * height)
                    xmax = int((x_c + w / 2) * width)
                    ymax = int((y_c + h / 2) * height)
                    
                    # 获取类别名称
                    name = id_to_class.get(class_id, str(class_id))
                    
                    objects.append({
                        "name": name,
                        "xmin": max(0, xmin),
                        "ymin": max(0, ymin),
                        "xmax": min(width, xmax),
                        "ymax": min(height, ymax),
                    })
        
        # 生成 XML
        annotation = ET.Element("annotation")
        ET.SubElement(annotation, "folder").text = img_path.parent.name
        ET.SubElement(annotation, "filename").text = img_path.name
        
        size = ET.SubElement(annotation, "size")
        ET.SubElement(size, "width").text = str(width)
        ET.SubElement(size, "height").text = str(height)
        ET.SubElement(size, "depth").text = str(depth)
        
        for obj_data in objects:
            obj = ET.SubElement(annotation, "object")
            ET.SubElement(obj, "name").text = obj_data["name"]
            ET.SubElement(obj, "difficult").text = "0"
            
            bndbox = ET.SubElement(obj, "bndbox")
            ET.SubElement(bndbox, "xmin").text = str(obj_data["xmin"])
            ET.SubElement(bndbox, "ymin").text = str(obj_data["ymin"])
            ET.SubElement(bndbox, "xmax").text = str(obj_data["xmax"])
            ET.SubElement(bndbox, "ymax").text = str(obj_data["ymax"])
        
        # 格式化 XML (添加换行和缩进)
        from xml.dom import minidom
        xml_str = ET.tostring(annotation, encoding="unicode")
        pretty_xml = minidom.parseString(xml_str).toprettyxml(indent="    ")
        # 移除多余空行
        pretty_xml = "\n".join(line for line in pretty_xml.split("\n") if line.strip())
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(pretty_xml)
        
        return True
    
    def _convert_xml_to_txt(self, xml_path: Path, class_to_id: dict, output_path: Path) -> bool:
        """将 XML 标签转换为 TXT"""
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
        except Exception:
            return False
        
        # 读取尺寸
        size = root.find("size")
        if size is None:
            return False
        
        width = int(size.findtext("width", "0"))
        height = int(size.findtext("height", "0"))
        
        if width == 0 or height == 0:
            return False
        
        # 解析对象
        lines = []
        for obj in root.findall(".//object"):
            name_elem = obj.find("name")
            bndbox = obj.find("bndbox")
            
            if name_elem is None or bndbox is None:
                continue
            
            name = name_elem.text.strip() if name_elem.text else ""
            
            xmin = int(float(bndbox.findtext("xmin", "0")))
            ymin = int(float(bndbox.findtext("ymin", "0")))
            xmax = int(float(bndbox.findtext("xmax", "0")))
            ymax = int(float(bndbox.findtext("ymax", "0")))
            
            # 绝对坐标 → 归一化
            x_c = (xmin + xmax) / 2 / width
            y_c = (ymin + ymax) / 2 / height
            w = (xmax - xmin) / width
            h = (ymax - ymin) / height
            
            # 获取类别 ID
            class_id = class_to_id.get(name, len(class_to_id))
            if name not in class_to_id:
                class_to_id[name] = class_id
            
            lines.append(f"{class_id} {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}")
        
        # 写入 TXT
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        return True
    
    def _find_image_for_label(
        self,
        label_path: Path,
        root: Path,
        image_dir: Optional[Path] = None,
        label_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        """根据标签文件查找对应的图片"""
        stem = label_path.stem
        
        # 1. 同目录
        for ext in IMAGE_EXTENSIONS:
            img_path = label_path.with_suffix(ext)
            if img_path.exists():
                return img_path
        
        # 2. 目录映射 (labels → images, Annotations → JPEGImages)
        # 2. ?????? (????????????)
        if image_dir and label_dir:
            try:
                rel_path = label_path.relative_to(label_dir)
                img_parent = image_dir / rel_path.parent
                for ext in IMAGE_EXTENSIONS:
                    img_path = img_parent / (stem + ext)
                    if img_path.exists():
                        return img_path
            except ValueError:
                pass

        # 3. Heuristic directory mapping for common dataset layouts.
        dir_mappings = [
            ("labels", "images"),
            ("annotations", "jpegimages"),
            ("label", "img"),
        ]
        
        try:
            rel_path = label_path.relative_to(root)
            parts = list(rel_path.parts)
            
            for lbl_dir, img_dir in dir_mappings:
                for i, part in enumerate(parts):
                    if part.lower() == lbl_dir:
                        new_parts = list(parts)
                        new_parts[i] = img_dir
                        img_base = root / Path(*new_parts[:-1])
                        
                        for ext in IMAGE_EXTENSIONS:
                            img_path = img_base / (stem + ext)
                            if img_path.exists():
                                return img_path
                        break
        except ValueError:
            pass
        
        return None
    
    # ==================== 私有辅助方法 ====================
    
    def _find_images(self, root: Path) -> list[Path]:
        """递归查找所有图片文件"""
        images = []
        for ext in IMAGE_EXTENSIONS:
            images.extend(root.rglob(f"*{ext}"))
            images.extend(root.rglob(f"*{ext.upper()}"))
        return sorted(set(images))
    
    def _find_label(self, img_path: Path, root: Path) -> tuple[Optional[Path], Optional[LabelFormat]]:
        """
        查找图片对应的标签文件
        
        查找顺序:
            1. 同目录下的 .xml / .txt
            2. YOLO 目录结构: images/ -> labels/
            3. Pascal VOC 目录结构: JPEGImages/ -> Annotations/
        """
        stem = img_path.stem
        
        # 1. 同目录 (XML 优先)
        for ext, fmt in [(".xml", LabelFormat.XML), (".txt", LabelFormat.TXT)]:
            label_path = img_path.with_suffix(ext)
            if label_path.exists():
                return label_path, fmt
        
        # 2. 目录映射: 支持 YOLO 和 Pascal VOC
        # 映射规则: (图片目录名 -> 标签目录名)
        dir_mappings = [
            ("images", "labels"),           # YOLO 标准
            ("jpegimages", "annotations"),  # Pascal VOC 标准
            ("imgs", "labels"),             # 常见变体
            ("img", "label"),               # 常见变体
        ]
        
        try:
            rel_path = img_path.relative_to(root)
            parts = list(rel_path.parts)
            
            # 尝试每种映射
            for img_dir, lbl_dir in dir_mappings:
                for i, part in enumerate(parts):
                    if part.lower() == img_dir:
                        # 创建替换后的路径
                        new_parts = list(parts)
                        new_parts[i] = lbl_dir
                        label_dir = root / Path(*new_parts[:-1])
                        
                        for ext, fmt in [(".xml", LabelFormat.XML), (".txt", LabelFormat.TXT)]:
                            label_path = label_dir / (stem + ext)
                            if label_path.exists():
                                return label_path, fmt
                        break
        except ValueError:
            pass
        
        return None, None
    
    def _parse_label(
        self,
        label_path: Path,
        label_format: LabelFormat,
        class_mapping: Optional[dict[int, str]] = None,
    ) -> list[str]:
        """?????????????"""
        classes = []
        mapping = class_mapping or {}
        
        try:
            if label_format == LabelFormat.TXT:
                with open(label_path, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.strip().split()
                        if parts:
                            class_id = int(parts[0])
                            # ? classes.txt ??????????????
                            class_name = mapping.get(class_id, str(class_id))
                            classes.append(class_name)
            else:
                tree = ET.parse(label_path)
                root = tree.getroot()
                for obj in root.findall(".//object/name"):
                    if obj.text:
                        classes.append(obj.text)
        except Exception:
            pass
        
        return classes
    
    def _create_empty_xml(self, img_path: Path, label_path: Path) -> None:
        """创建空的 VOC XML 标签文件"""
        try:
            with Image.open(img_path) as img:
                width, height = img.size
                depth = len(img.getbands())
        except Exception:
            width, height, depth = 0, 0, 3
        
        root = ET.Element("annotation")
        
        # 文件夹名
        ET.SubElement(root, "folder").text = img_path.parent.name
        
        # 文件名
        ET.SubElement(root, "filename").text = img_path.name
        
        # 尺寸
        size = ET.SubElement(root, "size")
        ET.SubElement(size, "width").text = str(width)
        ET.SubElement(size, "height").text = str(height)
        ET.SubElement(size, "depth").text = str(depth)
        
        # 无 object 节点
        
        tree = ET.ElementTree(root)
        ET.indent(tree, space="    ")
        tree.write(label_path, encoding="utf-8", xml_declaration=True)
    
    def _prepare_modified_xml(
        self,
        label_path: Path,
        action: ModifyAction,
        old_value: str,
        new_value: str,
    ) -> tuple[bool, Optional[ET.ElementTree]]:
        """构建修改后的 XML 标签树"""
        try:
            tree = ET.parse(label_path)
            root = tree.getroot()
            modified = False
            
            if action == ModifyAction.REPLACE:
                for name_elem in root.findall(".//object/name"):
                    if name_elem.text == old_value:
                        name_elem.text = new_value
                        modified = True
            else:  # REMOVE
                for obj in root.findall(".//object"):
                    name_elem = obj.find("name")
                    if name_elem is not None and name_elem.text == old_value:
                        root.remove(obj)
                        modified = True
            
            return modified, tree if modified else None
            
        except Exception:
            return False, None
    
    def _prepare_modified_txt(
        self,
        label_path: Path,
        action: ModifyAction,
        old_value: str,
        new_value: str,
        class_mapping: Optional[dict[int, str]] = None,
    ) -> tuple[bool, Optional[list[str]]]:
        """?????? TXT ????"""
        try:
            # ??????? ID
            old_id = self._resolve_class_id(old_value, class_mapping=class_mapping)
            new_id = self._resolve_class_id(new_value, class_mapping=class_mapping) if action == ModifyAction.REPLACE else None
            
            if old_id is None:
                return False, None
            
            with open(label_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            new_lines = []
            modified = False
            
            for line in lines:
                parts = line.strip().split()
                if not parts:
                    continue
                
                class_id = int(parts[0])
                
                if class_id == old_id:
                    if action == ModifyAction.REPLACE and new_id is not None:
                        parts[0] = str(new_id)
                        new_lines.append(" ".join(parts) + "\n")
                        modified = True
                    elif action == ModifyAction.REMOVE:
                        modified = True
                        continue  # ????
                else:
                    new_lines.append(line)
            
            return modified, new_lines if modified else None
            
        except Exception:
            return False, None
    
    def _resolve_class_id(self, value: str, class_mapping: Optional[dict[int, str]] = None) -> Optional[int]:
        """????????? ID ???? ID"""
        normalized = value.strip()
        if not normalized:
            return None
        
        if normalized.isdigit():
            return int(normalized)
        
        for id_, name in (class_mapping or {}).items():
            if name == normalized:
                return id_
        
        return None
    
    def _count_txt_matches(
        self,
        path: Path,
        old_value: str,
        class_mapping: Optional[dict[int, str]] = None,
    ) -> int:
        """?? TXT ??????????"""
        old_id = self._resolve_class_id(old_value, class_mapping=class_mapping)
        if old_id is None:
            return 0
        
        matches = 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if parts and int(parts[0]) == old_id:
                        matches += 1
        except Exception:
            return 0
        
        return matches
    
    def _get_unique_backup_path(self, label_path: Path) -> Path:
        """Return a non-conflicting backup path for the given label file."""
        backup_path = label_path.with_suffix(label_path.suffix + ".bak")
        if not backup_path.exists():
            return backup_path

        counter = 1
        while True:
            candidate = label_path.with_suffix(label_path.suffix + f".bak.{counter}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _write_lines_atomic(self, label_path: Path, lines: list[str]) -> None:
        """Write label text atomically to avoid partial file corruption."""
        fd, temp_name = tempfile.mkstemp(
            prefix=f"{label_path.name}.",
            suffix=".tmp",
            dir=str(label_path.parent),
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.writelines(lines)
            os.replace(str(temp_path), str(label_path))
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def _write_xml_tree_atomic(self, label_path: Path, tree: ET.ElementTree) -> None:
        """Write XML labels atomically to avoid partial file corruption."""
        fd, temp_name = tempfile.mkstemp(
            prefix=f"{label_path.name}.",
            suffix=".tmp",
            dir=str(label_path.parent),
        )
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            tree.write(temp_path, encoding="utf-8", xml_declaration=True)
            os.replace(str(temp_path), str(label_path))
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def _count_xml_matches(self, path: Path, old_value: str) -> int:
        """统计 XML 标签中命中的标注数量"""
        try:
            tree = ET.parse(path)
            return sum(
                1
                for name_elem in tree.getroot().findall(".//object/name")
                if name_elem.text == old_value
            )
        except Exception:
            return 0

    def _is_txt_label_file(self, path: Path) -> bool:
        """判断 TXT 文件是否为有效检测标签"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    
                    parts = stripped.split()
                    if len(parts) < 5:
                        return False
                    
                    int(parts[0])
                    for value in parts[1:5]:
                        float(value)
            
            return True
            
        except Exception:
            return False

    def _is_xml_label_file(self, path: Path) -> bool:
        """判断 XML 文件是否为 VOC 标签"""
        try:
            root = ET.parse(path).getroot()
        except Exception:
            return False
        
        return root.tag.lower() == "annotation"
    
    def _split_files(
        self,
        img_dir: Path,
        train_images: list[Path],
        val_images: list[Path],
        label_dir: Optional[Path],
        output_dir: Path,
        use_copy: bool,
        clear_output: bool,
        interrupt_check: Callable[[], bool],
        progress_callback: Optional[Callable[[int, int], None]],
        message_callback: Optional[Callable[[str], None]],
    ) -> tuple[str, str]:
        """
        物理文件划分 (移动或复制, YOLO 标准目录结构)
        
        创建结构:
            output_dir/
            ├── images/
            │   ├── train/
            │   └── val/
            └── labels/
                ├── train/
                └── val/
        """
        # YOLO 标准目录结构
        train_img_dir = output_dir / "images" / "train"
        train_lbl_dir = output_dir / "labels" / "train"
        val_img_dir = output_dir / "images" / "val"
        val_lbl_dir = output_dir / "labels" / "val"
        
        for d in [train_img_dir, train_lbl_dir, val_img_dir, val_lbl_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        # 清空目标目录
        if clear_output:
            for d in [train_img_dir, train_lbl_dir, val_img_dir, val_lbl_dir]:
                if d.exists():
                    shutil.rmtree(d)
                d.mkdir(parents=True, exist_ok=True)
            if message_callback:
                message_callback("已清空目标目录")
        
        mode_str = "复制" if use_copy else "移动"
        if message_callback:
            message_callback(f"使用 {mode_str} 模式，创建 YOLO 标准目录结构")
        
        total = len(train_images) + len(val_images)
        current = 0
        
        # 处理训练集
        for img_path in train_images:
            if interrupt_check():
                break
            
            log_msg = self._transfer_with_label(img_path, train_img_dir, train_lbl_dir, img_dir.parent, label_dir, use_copy)
            if log_msg and message_callback:
                message_callback(log_msg)
            current += 1
            if progress_callback:
                progress_callback(current, total)
        
        # 处理验证集
        for img_path in val_images:
            if interrupt_check():
                break
            
            log_msg = self._transfer_with_label(img_path, val_img_dir, val_lbl_dir, img_dir.parent, label_dir, use_copy)
            if log_msg and message_callback:
                message_callback(log_msg)
            current += 1
            if progress_callback:
                progress_callback(current, total)
        
        # 返回相对路径用于 YAML
        return "images/train", "images/val"
    
    def _split_index(
        self,
        root: Path,
        train_images: list[Path],
        val_images: list[Path],
        message_callback: Optional[Callable[[str], None]],
    ) -> tuple[str, str]:
        """索引文件模式划分（使用相对路径，便于数据集迁移）"""
        root.mkdir(parents=True, exist_ok=True)
        train_txt = root / "train.txt"
        val_txt = root / "val.txt"
        
        with open(train_txt, "w", encoding="utf-8") as f:
            for img in train_images:
                try:
                    rel = img.relative_to(root)
                except ValueError:
                    rel = img.absolute()
                f.write(str(rel) + "\n")
        
        with open(val_txt, "w", encoding="utf-8") as f:
            for img in val_images:
                try:
                    rel = img.relative_to(root)
                except ValueError:
                    rel = img.absolute()
                f.write(str(rel) + "\n")
        
        if message_callback:
            message_callback(f"已生成索引文件: {train_txt.name}, {val_txt.name} (相对路径)")
        
        return str(train_txt), str(val_txt)
    
    def _transfer_with_label(
        self, 
        img_path: Path, 
        img_dir: Path, 
        lbl_dir: Path, 
        root: Path,
        label_source_dir: Optional[Path],
        use_copy: bool
    ) -> str:
        """
        移动或复制图片及其对应的标签文件
        
        Returns:
            日志消息字符串
        """
        transfer_func = shutil.copy2 if use_copy else shutil.move
        action = "→" if use_copy else "⇢"
        
        # 传输图片
        dest_img = img_dir / img_path.name
        transfer_func(str(img_path), str(dest_img))
        log_parts = [f"{img_path.name} {action} {img_dir.parent.name}/{img_dir.name}"]
        
        # 查找并传输标签
        if label_source_dir and label_source_dir.exists():
            label_path, _ = self._find_label_in_dir(img_path, label_source_dir)
        else:
            label_path, _ = self._find_label(img_path, root)
        
        if label_path and label_path.exists():
            transfer_func(str(label_path), str(lbl_dir / label_path.name))
            log_parts.append(f"+ {label_path.suffix}")
        
        return " ".join(log_parts)
    
    def categorize_by_class(
        self,
        img_dir: Path,
        label_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        classes_txt: Optional[Path] = None,
        include_no_label: bool = True,
        interrupt_check: Callable[[], bool] = lambda: False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        message_callback: Optional[Callable[[str], None]] = None,
    ) -> dict[str, int]:
        """
        按类别分类数据集
        
        将图片和标签按类别复制到对应文件夹:
            - 空标签 -> _empty/
            - 单一类别 -> {class_id}/
            - 多类别 -> _mixed/
            - 无标签 -> _no_label/
        
        Args:
            img_dir: 图片目录
            label_dir: 标签目录 (可选，留空则自动检测)
            output_dir: 输出目录 (默认 img_dir.parent / "{img_dir.name}_categorized")
            classes_txt: classes.txt 路径 (可选，用于 TXT 标签类别映射)
            include_no_label: 是否包含无标签图片
            interrupt_check: 中断检查函数
            progress_callback: 进度回调 (current, total)
            message_callback: 消息回调
        
        Returns:
            分类统计 {类别名: 数量}
        """
        # 加载类别映射
        class_mapping: dict[int, str] = {}
        if classes_txt and classes_txt.exists():
            _, class_mapping = self._read_classes_txt(classes_txt)
            if message_callback:
                message_callback(f"已加载类别文件: {len(class_mapping)} 个类别")
        
        # 默认输出目录 (如果已存在则添加数字后缀)
        if output_dir is None:
            output_dir = _get_unique_dir(img_dir.parent / f"{img_dir.name}_categorized")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if message_callback:
            message_callback(f"输出目录: {output_dir}")
        
        # 收集所有图片
        images = self._find_images(img_dir)
        total = len(images)
        
        if total == 0:
            if message_callback:
                message_callback("未找到图片文件")
            return {}
        
        if message_callback:
            message_callback(f"发现 {total} 张图片，开始分类...")
        
        # 统计结果
        stats: dict[str, int] = {}
        # 混合类别报告: {文件名: [类别ID列表]}
        mixed_report: dict[str, list[str]] = {}
        
        for i, img_path in enumerate(images):
            if interrupt_check():
                if message_callback:
                    message_callback("分类已取消")
                break
            
            # 查找标签
            if label_dir and label_dir.exists():
                label_path, label_format = self._find_label_in_dir(img_path, label_dir)
            else:
                label_path, label_format = self._find_label(img_path, img_dir.parent)
            
            # 确定分类目标
            if label_path is None:
                # 无标签
                if not include_no_label:
                    if progress_callback:
                        progress_callback(i + 1, total)
                    continue
                category = "_no_label"
                class_ids: list[str] = []
            else:
                # 解析标签获取类别 ID (使用原始 ID，不映射名称)
                class_ids = self._parse_label_ids(label_path, label_format, class_mapping=class_mapping)
                unique_ids = sorted(set(class_ids))
                
                if len(unique_ids) == 0:
                    category = "_empty"
                elif len(unique_ids) == 1:
                    category = unique_ids[0]
                else:
                    category = "_mixed"
                    mixed_report[img_path.name] = unique_ids
            
            # 创建目标目录
            cat_dir = output_dir / category
            cat_img_dir = cat_dir / "images"
            cat_lbl_dir = cat_dir / "labels"
            cat_img_dir.mkdir(parents=True, exist_ok=True)
            if category != "_no_label":
                cat_lbl_dir.mkdir(parents=True, exist_ok=True)
            
            # 复制图片
            dest_img = cat_img_dir / img_path.name
            shutil.copy2(str(img_path), str(dest_img))
            
            # 复制标签 (如果存在)
            if label_path and label_path.exists() and category != "_no_label":
                dest_lbl = cat_lbl_dir / label_path.name
                shutil.copy2(str(label_path), str(dest_lbl))
            
            # 统计
            stats[category] = stats.get(category, 0) + 1
            
            if progress_callback:
                progress_callback(i + 1, total)
        
        # 生成混合类别报告
        if mixed_report:
            report_path = output_dir / "_mixed_report.txt"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("# 混合类别报告\n")
                f.write("# 格式: 文件名 -> 类别ID列表\n")
                f.write("# ========================================\n\n")
                for filename, ids in sorted(mixed_report.items()):
                    f.write(f"{filename} -> {', '.join(ids)}\n")
            if message_callback:
                message_callback(f"混合类别报告已保存: {report_path.name}")
        
        # 输出统计
        if message_callback:
            message_callback("=" * 40)
            message_callback("分类完成，统计如下:")
            for cat, count in sorted(stats.items()):
                message_callback(f"  {cat}: {count} 张")
            message_callback(f"  合计: {sum(stats.values())} 张")
        
        return stats
    
    def augment_dataset(
        self,
        img_dir: Path,
        config: AugmentConfig,
        label_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        classes_txt: Optional[Path] = None,
        interrupt_check: Callable[[], bool] = lambda: False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        message_callback: Optional[Callable[[str], None]] = None,
    ) -> AugmentResult:
        """Generate an offline augmented dataset with synchronized labels."""
        if config.copies_per_image < 1:
            raise ValueError("??????????? 1")
        if not config.has_any_operation():
            raise ValueError("???????????")
        if config.mode == "fixed" and not config.build_fixed_recipes():
            raise ValueError("?????????????????????")

        if output_dir is None:
            output_dir = _get_unique_dir(img_dir.parent / f"{img_dir.name}_augmented")

        output_dir.mkdir(parents=True, exist_ok=True)
        images = self._find_images(img_dir)
        result = AugmentResult(output_dir=str(output_dir), source_images=len(images))

        if message_callback:
            mode_label = "????" if config.mode == "fixed" else "????"
            message_callback(f"??????: {output_dir}")
            message_callback(f"????: {mode_label}")

        if classes_txt and classes_txt.exists():
            shutil.copy2(str(classes_txt), str(output_dir / classes_txt.name))
            if message_callback:
                message_callback(f"???????: {classes_txt.name}")

        total = len(images)
        if total == 0:
            if message_callback:
                message_callback("???????????")
            return result

        rng = random.Random(config.seed)

        for index, img_path in enumerate(images):
            if interrupt_check():
                if message_callback:
                    message_callback("???????")
                break

            try:
                rel_path = img_path.relative_to(img_dir)
                if label_dir and label_dir.exists():
                    label_path, label_format = self._find_label_in_dir(img_path, label_dir)
                else:
                    label_path, label_format = self._find_label(img_path, img_dir.parent)

                with Image.open(img_path) as source_image:
                    base_image = ImageOps.exif_transpose(source_image)
                    source_image_size = base_image.size

                    if config.include_original:
                        original_output = self._build_augmented_image_output_path(output_dir, rel_path)
                        original_output.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(img_path), str(original_output))
                        result.copied_originals += 1

                        if label_path and label_format:
                            original_label_output = self._build_augmented_label_output_path(
                                output_dir,
                                rel_path,
                                img_path.stem,
                                label_format,
                            )
                            self._write_augmented_label(
                                label_path,
                                label_format,
                                original_label_output,
                                [],
                                original_output,
                                source_image_size,
                            )
                            result.label_files_written += 1

                    recipe_counters: dict[str, int] = {}
                    for recipe, display_index in self._iter_augment_recipes(config, rng):
                        augmented_image, geometry_ops = self._apply_augmentation_recipe(
                            base_image,
                            recipe.operations,
                            config,
                            rng,
                        )
                        recipe_counters[recipe.name] = recipe_counters.get(recipe.name, 0) + 1
                        recipe_suffix = recipe.name if config.mode == "fixed" else "aug"
                        aug_stem = f"{img_path.stem}_{recipe_suffix}_{recipe_counters[recipe.name]:03d}"
                        if config.mode == "random" and recipe.name != "aug":
                            aug_stem = f"{img_path.stem}_{recipe.name}_{display_index:03d}"
                        aug_rel_path = rel_path.with_name(f"{aug_stem}{img_path.suffix.lower()}")
                        aug_output = self._build_augmented_image_output_path(output_dir, aug_rel_path)

                        self._save_augmented_image(augmented_image, aug_output)
                        result.augmented_images += 1

                        if label_path and label_format:
                            aug_label_output = self._build_augmented_label_output_path(
                                output_dir,
                                rel_path,
                                aug_stem,
                                label_format,
                            )
                            self._write_augmented_label(
                                label_path,
                                label_format,
                                aug_label_output,
                                geometry_ops,
                                aug_output,
                                source_image_size,
                            )
                            result.label_files_written += 1
            except Exception as exc:
                result.skipped_images += 1
                if message_callback:
                    message_callback(f"?? {img_path.name}: {exc}")

            if progress_callback:
                progress_callback(index + 1, total)

        if message_callback:
            total_outputs = result.copied_originals + result.augmented_images
            message_callback(
                "??????: "
                f"???? {total_outputs} ?"
                f"(?? {result.copied_originals} / ?? {result.augmented_images})?"
                f"?? {result.label_files_written} ?"
            )
            if result.skipped_images > 0:
                message_callback(f"????: {result.skipped_images} ?")

        return result

    def _build_augmented_image_output_path(self, output_dir: Path, relative_path: Path) -> Path:
        """??????????"""
        return output_dir / "images" / relative_path

    def _build_augmented_label_output_path(
        self,
        output_dir: Path,
        relative_path: Path,
        stem: str,
        label_format: LabelFormat,
    ) -> Path:
        """??????????"""
        label_root = "labels" if label_format == LabelFormat.TXT else "Annotations"
        suffix = ".txt" if label_format == LabelFormat.TXT else ".xml"
        return output_dir / label_root / relative_path.parent / f"{stem}{suffix}"

    def _iter_augment_recipes(
        self,
        config: AugmentConfig,
        rng: random.Random,
    ) -> list[tuple[AugmentRecipe, int]]:
        """Resolve the list of recipes to generate for one source image."""
        if config.mode == "fixed":
            recipes = config.build_fixed_recipes()
            return [
                (recipe, copy_index + 1)
                for copy_index in range(config.copies_per_image)
                for recipe in recipes
            ]

        resolved: list[tuple[AugmentRecipe, int]] = []
        for copy_index in range(config.copies_per_image):
            operations = self._sample_random_operations(config, rng)
            resolved.append((AugmentRecipe("aug", operations), copy_index + 1))
        return resolved

    def _sample_random_operations(
        self,
        config: AugmentConfig,
        rng: random.Random,
    ) -> tuple[str, ...]:
        """Sample one random augmentation recipe."""
        geometry_ops: list[str] = []
        photo_ops: list[str] = []
        geometric_candidates = config.geometric_candidates()
        photometric_candidates = config.photometric_candidates()

        if geometric_candidates and rng.random() < 0.9:
            geometry_ops.append(rng.choice(geometric_candidates))

        for operation in photometric_candidates:
            if rng.random() < 0.5:
                photo_ops.append(operation)

        if not geometry_ops and not photo_ops:
            fallback_ops = geometric_candidates + photometric_candidates
            if fallback_ops:
                chosen = rng.choice(fallback_ops)
                if chosen in geometric_candidates:
                    geometry_ops.append(chosen)
                else:
                    photo_ops.append(chosen)

        return tuple(geometry_ops + photo_ops)

    def _apply_augmentation_recipe(
        self,
        image: Image.Image,
        operations: tuple[str, ...],
        config: AugmentConfig,
        rng: random.Random,
    ) -> tuple[Image.Image, list[AppliedGeometryOp]]:
        """Apply a resolved recipe to an image."""
        augmented = image.copy()
        geometry_ops: list[AppliedGeometryOp] = []

        for operation in operations:
            if operation in {"flip_lr", "flip_ud", "rotate"}:
                augmented, applied_geometry = self._apply_geometric_augmentation(
                    augmented,
                    operation,
                    config,
                    rng,
                )
                geometry_ops.append(applied_geometry)
            else:
                augmented = self._apply_photometric_augmentation(
                    augmented,
                    operation,
                    config,
                    rng,
                )

        return augmented, geometry_ops

    def _apply_geometric_augmentation(
        self,
        image: Image.Image,
        operation: str,
        config: AugmentConfig,
        rng: random.Random,
    ) -> tuple[Image.Image, AppliedGeometryOp]:
        """Apply one geometry transform and return the concrete op."""
        if operation == "flip_lr":
            return ImageOps.mirror(image), AppliedGeometryOp("flip_lr")
        if operation == "flip_ud":
            return ImageOps.flip(image), AppliedGeometryOp("flip_ud")
        if operation == "rotate":
            angle = self._resolve_rotation_angle(config, rng)
            resample = (
                Image.Resampling.NEAREST
                if image.mode in {"1", "P"}
                else Image.Resampling.BICUBIC
            )
            return (
                image.rotate(
                    angle,
                    resample=resample,
                    expand=True,
                    fillcolor=self._get_rotation_fillcolor(image),
                ),
                AppliedGeometryOp("rotate", angle),
            )
        raise ValueError(f"????????: {operation}")

    def _resolve_rotation_angle(
        self,
        config: AugmentConfig,
        rng: random.Random,
    ) -> float:
        """Resolve the actual rotation angle in PIL's sign convention."""
        degrees = max(0.0, float(config.rotate_degrees))
        if config.rotate_mode == "clockwise":
            return -degrees
        if config.rotate_mode == "counterclockwise":
            return degrees
        return rng.uniform(-degrees, degrees)

    def _get_rotation_fillcolor(self, image: Image.Image):
        """Match YOLO-style neutral padding for rotated images."""
        bands = len(image.getbands())
        if image.mode == "RGBA":
            return (114, 114, 114, 0)
        if image.mode in {"RGB", "YCbCr"}:
            return (114, 114, 114)
        if bands == 1:
            return 114
        return tuple(114 for _ in range(bands))

    def _apply_photometric_augmentation(
        self,
        image: Image.Image,
        operation: str,
        config: AugmentConfig,
        rng: random.Random,
    ) -> Image.Image:
        """Apply one color or sharpness transform."""
        if operation == "brightness":
            return ImageEnhance.Brightness(image).enhance(
                self._sample_enhance_factor(config.brightness_strength, rng)
            )
        if operation == "contrast":
            return ImageEnhance.Contrast(image).enhance(
                self._sample_enhance_factor(config.contrast_strength, rng)
            )
        if operation == "color":
            return ImageEnhance.Color(image).enhance(
                self._sample_enhance_factor(config.color_strength, rng)
            )
        if operation == "noise":
            return self._apply_noise(image, config.noise_strength, rng)
        if operation == "hue":
            return self._apply_hue_shift(
                image,
                rng.uniform(-config.hue_degrees, config.hue_degrees),
            )
        if operation == "sharpness":
            return ImageEnhance.Sharpness(image).enhance(
                self._sample_enhance_factor(config.sharpness_strength, rng)
            )
        if operation == "blur":
            return image.filter(
                ImageFilter.GaussianBlur(radius=rng.uniform(0.2, config.blur_radius))
            )
        raise ValueError(f"????????: {operation}")

    def _sample_enhance_factor(
        self,
        strength: float,
        rng: random.Random,
    ) -> float:
        """Sample a PIL enhancement factor centered at 1.0."""
        strength = max(0.0, float(strength))
        return rng.uniform(max(0.0, 1.0 - strength), 1.0 + strength)

    def _apply_noise(
        self,
        image: Image.Image,
        strength: float,
        rng: random.Random,
    ) -> Image.Image:
        """Apply additive Gaussian-style noise without changing labels."""
        strength = max(0.0, float(strength))
        if strength <= 0:
            return image

        sigma = max(1.0, strength * 255.0)
        if image.mode == "RGBA":
            alpha = image.getchannel("A")
            noisy = self._apply_noise(image.convert("RGB"), strength, rng).convert("RGBA")
            noisy.putalpha(alpha)
            return noisy
        if image.mode == "RGB":
            channels = tuple(Image.effect_noise(image.size, sigma) for _ in range(3))
            noise_image = Image.merge("RGB", channels)
            return ImageChops.add(image, noise_image, scale=1.0, offset=-128)
        if image.mode == "L":
            noise_image = Image.effect_noise(image.size, sigma)
            return ImageChops.add(image, noise_image, scale=1.0, offset=-128)
        return image

    def _apply_hue_shift(self, image: Image.Image, degrees: float) -> Image.Image:
        """Shift hue while preserving non-RGB modes when possible."""
        if image.mode not in {"RGB", "RGBA"}:
            return image

        alpha = None
        rgb_image = image
        if image.mode == "RGBA":
            alpha = image.getchannel("A")
            rgb_image = image.convert("RGB")

        hsv_image = rgb_image.convert("HSV")
        hue, sat, val = hsv_image.split()
        offset = int(round((degrees / 360.0) * 255)) % 256
        hue = hue.point(lambda value: (value + offset) % 256)
        shifted = Image.merge("HSV", (hue, sat, val)).convert("RGB")

        if alpha is not None:
            shifted = shifted.convert("RGBA")
            shifted.putalpha(alpha)
        return shifted

    def _save_augmented_image(self, image: Image.Image, output_path: Path) -> None:
        """Persist an augmented image to disk."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_image = image
        if output_path.suffix.lower() in {".jpg", ".jpeg"} and image.mode not in {"RGB", "L"}:
            save_image = image.convert("RGB")
        save_image.save(output_path)

    def _write_augmented_label(
        self,
        label_path: Path,
        label_format: LabelFormat,
        output_path: Path,
        geometry_ops: list[AppliedGeometryOp],
        output_image_path: Path,
        source_image_size: tuple[int, int],
    ) -> None:
        """Write a label file that matches the transformed image."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(output_image_path) as output_image:
            output_image_size = output_image.size
            output_depth = len(output_image.getbands())

        effective_source_size = output_image_size if not geometry_ops else source_image_size

        if label_format == LabelFormat.TXT:
            lines = self._transform_txt_label(
                label_path,
                geometry_ops,
                effective_source_size,
                output_image_size,
            )
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return

        tree = self._transform_xml_label(
            label_path,
            geometry_ops,
            output_image_path,
            effective_source_size,
            output_image_size,
            output_depth,
        )
        ET.indent(tree, space="    ")
        tree.write(output_path, encoding="utf-8", xml_declaration=True)

    def _transform_txt_label(
        self,
        label_path: Path,
        geometry_ops: list[AppliedGeometryOp],
        source_image_size: tuple[int, int],
        output_image_size: tuple[int, int],
    ) -> list[str]:
        """Transform YOLO TXT labels for the generated sample."""
        transformed_lines: list[str] = []
        with open(label_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue

                parts = line.split()
                if len(parts) < 5:
                    transformed_lines.append(line)
                    continue

                try:
                    bbox = tuple(map(float, parts[1:5]))
                except ValueError:
                    transformed_lines.append(line)
                    continue

                absolute_box = self._normalized_box_to_absolute_float(
                    bbox,
                    source_image_size[0],
                    source_image_size[1],
                )
                transformed_box = self._transform_absolute_box(
                    absolute_box,
                    source_image_size,
                    geometry_ops,
                    output_image_size,
                )
                x_c, y_c, width, height = self._absolute_box_to_normalized(
                    transformed_box,
                    output_image_size[0],
                    output_image_size[1],
                )
                extras = f" {' '.join(parts[5:])}" if len(parts) > 5 else ""
                transformed_lines.append(
                    f"{parts[0]} {x_c:.6f} {y_c:.6f} {width:.6f} {height:.6f}{extras}"
                )

        return transformed_lines

    def _transform_xml_label(
        self,
        label_path: Path,
        geometry_ops: list[AppliedGeometryOp],
        output_image_path: Path,
        source_image_size: tuple[int, int],
        output_image_size: tuple[int, int],
        output_depth: int,
    ) -> ET.ElementTree:
        """Transform Pascal VOC XML boxes and metadata."""
        tree = ET.parse(label_path)
        root = tree.getroot()

        folder_elem = root.find("folder")
        if folder_elem is not None:
            folder_elem.text = output_image_path.parent.name

        filename_elem = root.find("filename")
        if filename_elem is not None:
            filename_elem.text = output_image_path.name

        size_elem = root.find("size")
        if size_elem is None:
            size_elem = ET.SubElement(root, "size")

        width_elem = size_elem.find("width")
        if width_elem is None:
            width_elem = ET.SubElement(size_elem, "width")
        height_elem = size_elem.find("height")
        if height_elem is None:
            height_elem = ET.SubElement(size_elem, "height")
        depth_elem = size_elem.find("depth")
        if depth_elem is None:
            depth_elem = ET.SubElement(size_elem, "depth")

        width_elem.text = str(output_image_size[0])
        height_elem.text = str(output_image_size[1])
        depth_elem.text = str(output_depth)

        for obj in root.findall(".//object"):
            bndbox = obj.find("bndbox")
            if bndbox is None:
                continue

            try:
                xmin = float(bndbox.findtext("xmin", "0"))
                ymin = float(bndbox.findtext("ymin", "0"))
                xmax = float(bndbox.findtext("xmax", "0"))
                ymax = float(bndbox.findtext("ymax", "0"))
            except ValueError:
                continue

            transformed_box = self._transform_absolute_box(
                (xmin, ymin, xmax, ymax),
                source_image_size,
                geometry_ops,
                output_image_size,
            )
            abs_box = self._absolute_box_to_ints(transformed_box, output_image_size)

            xmin_elem = bndbox.find("xmin")
            if xmin_elem is None:
                xmin_elem = ET.SubElement(bndbox, "xmin")
            ymin_elem = bndbox.find("ymin")
            if ymin_elem is None:
                ymin_elem = ET.SubElement(bndbox, "ymin")
            xmax_elem = bndbox.find("xmax")
            if xmax_elem is None:
                xmax_elem = ET.SubElement(bndbox, "xmax")
            ymax_elem = bndbox.find("ymax")
            if ymax_elem is None:
                ymax_elem = ET.SubElement(bndbox, "ymax")

            xmin_elem.text = str(abs_box[0])
            ymin_elem.text = str(abs_box[1])
            xmax_elem.text = str(abs_box[2])
            ymax_elem.text = str(abs_box[3])

        return tree

    def _transform_absolute_box(
        self,
        bbox: tuple[float, float, float, float],
        source_image_size: tuple[int, int],
        geometry_ops: list[AppliedGeometryOp],
        output_image_size: tuple[int, int],
    ) -> tuple[float, float, float, float]:
        """Apply geometric transforms to an axis-aligned box."""
        points = [
            (bbox[0], bbox[1]),
            (bbox[2], bbox[1]),
            (bbox[2], bbox[3]),
            (bbox[0], bbox[3]),
        ]
        current_size = source_image_size

        for operation in geometry_ops:
            points, current_size = self._apply_geometry_to_points(
                points,
                current_size,
                operation,
            )

        transformed_box = self._points_to_box(points)
        return self._clamp_absolute_box(transformed_box, output_image_size)

    def _apply_geometry_to_points(
        self,
        points: list[tuple[float, float]],
        current_size: tuple[int, int],
        operation: AppliedGeometryOp,
    ) -> tuple[list[tuple[float, float]], tuple[int, int]]:
        """Transform box corners using the same geometry as the image."""
        current_width, current_height = current_size

        if operation.kind == "flip_lr":
            return ([(current_width - x, y) for x, y in points], current_size)
        if operation.kind == "flip_ud":
            return ([(x, current_height - y) for x, y in points], current_size)
        if operation.kind == "rotate":
            matrix, rotated_size = self._build_rotation_reverse_matrix(
                current_width,
                current_height,
                operation.value,
                expand=True,
            )
            rotated_points = [
                self._invert_reverse_affine_point(x, y, matrix) for x, y in points
            ]
            return rotated_points, rotated_size
        raise ValueError(f"不支持的增强操作: {operation.kind}")

    def _build_rotation_reverse_matrix(
        self,
        width: int,
        height: int,
        angle: float,
        *,
        expand: bool,
    ) -> tuple[list[float], tuple[int, int]]:
        """Mirror Pillow's reverse affine matrix for rotate(expand=...)."""
        angle = angle % 360.0
        center_x = width / 2.0
        center_y = height / 2.0
        angle_radians = -math.radians(angle)
        matrix = [
            round(math.cos(angle_radians), 15),
            round(math.sin(angle_radians), 15),
            0.0,
            round(-math.sin(angle_radians), 15),
            round(math.cos(angle_radians), 15),
            0.0,
        ]

        def transform(x: float, y: float) -> tuple[float, float]:
            a, b, c, d, e, f = matrix
            return a * x + b * y + c, d * x + e * y + f

        matrix[2], matrix[5] = transform(-center_x, -center_y)
        matrix[2] += center_x
        matrix[5] += center_y

        output_width, output_height = width, height
        if expand:
            xs: list[float] = []
            ys: list[float] = []
            for x, y in ((0, 0), (width, 0), (width, height), (0, height)):
                rx, ry = transform(x, y)
                xs.append(rx)
                ys.append(ry)
            output_width = math.ceil(max(xs)) - math.floor(min(xs))
            output_height = math.ceil(max(ys)) - math.floor(min(ys))
            matrix[2], matrix[5] = transform(
                -(output_width - width) / 2.0,
                -(output_height - height) / 2.0,
            )

        return matrix, (int(output_width), int(output_height))

    def _invert_reverse_affine_point(
        self,
        x: float,
        y: float,
        matrix: list[float],
    ) -> tuple[float, float]:
        """Convert a source point through Pillow's reverse affine matrix."""
        a, b, c, d, e, f = matrix
        det = a * e - b * d
        if det == 0:
            return x, y
        return (
            (e * (x - c) - b * (y - f)) / det,
            (-d * (x - c) + a * (y - f)) / det,
        )

    def _points_to_box(
        self,
        points: list[tuple[float, float]],
    ) -> tuple[float, float, float, float]:
        """Convert transformed polygon corners back into an AABB."""
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return min(xs), min(ys), max(xs), max(ys)

    def _clamp_absolute_box(
        self,
        bbox: tuple[float, float, float, float],
        image_size: tuple[int, int],
    ) -> tuple[float, float, float, float]:
        """Clamp a box to image bounds while keeping a non-zero extent."""
        width, height = image_size
        if width <= 0 or height <= 0:
            return 0.0, 0.0, 0.0, 0.0

        xmin, ymin, xmax, ymax = bbox
        max_xmin = max(float(width) - 1.0, 0.0)
        max_ymin = max(float(height) - 1.0, 0.0)

        xmin = min(max(xmin, 0.0), max_xmin)
        ymin = min(max(ymin, 0.0), max_ymin)
        xmax = min(max(xmax, xmin + 1.0), float(width))
        ymax = min(max(ymax, ymin + 1.0), float(height))
        return xmin, ymin, xmax, ymax

    def _normalized_box_to_absolute_float(
        self,
        bbox: tuple[float, float, float, float],
        width: int,
        height: int,
    ) -> tuple[float, float, float, float]:
        """Convert normalized YOLO boxes into continuous image coordinates."""
        x_c, y_c, box_w, box_h = bbox
        xmin = (x_c - box_w / 2.0) * width
        ymin = (y_c - box_h / 2.0) * height
        xmax = (x_c + box_w / 2.0) * width
        ymax = (y_c + box_h / 2.0) * height
        return xmin, ymin, xmax, ymax

    def _absolute_box_to_normalized(
        self,
        bbox: tuple[float, float, float, float],
        width: int,
        height: int,
    ) -> tuple[float, float, float, float]:
        """Convert continuous image coordinates into normalized YOLO boxes."""
        if width <= 0 or height <= 0:
            return 0.0, 0.0, 0.0, 0.0

        xmin, ymin, xmax, ymax = bbox
        x_c = ((xmin + xmax) / 2.0) / width
        y_c = ((ymin + ymax) / 2.0) / height
        box_w = max(0.0, (xmax - xmin) / width)
        box_h = max(0.0, (ymax - ymin) / height)
        return (
            min(max(x_c, 0.0), 1.0),
            min(max(y_c, 0.0), 1.0),
            min(max(box_w, 0.0), 1.0),
            min(max(box_h, 0.0), 1.0),
        )

    def _absolute_box_to_ints(
        self,
        bbox: tuple[float, float, float, float],
        image_size: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        """Round and clamp a float box for VOC XML output."""
        width, height = image_size
        xmin = int(round(bbox[0]))
        ymin = int(round(bbox[1]))
        xmax = int(round(bbox[2]))
        ymax = int(round(bbox[3]))

        xmin = max(0, min(max(width - 1, 0), xmin))
        ymin = max(0, min(max(height - 1, 0), ymin))
        xmax = max(xmin + 1, min(width, xmax)) if width > 0 else 0
        ymax = max(ymin + 1, min(height, ymax)) if height > 0 else 0
        return xmin, ymin, xmax, ymax

    def _parse_label_ids(
        self,
        label_path: Path,
        label_format: LabelFormat,
        class_mapping: Optional[dict[int, str]] = None,
    ) -> list[str]:
        """
        ??????????????? (?????)
        
        - TXT ??: ??? class_mapping?????????????????? ID
        - XML ??: ???? <name> ????
        """
        ids: list[str] = []
        mapping = class_mapping or {}
        
        try:
            if label_format == LabelFormat.TXT:
                with open(label_path, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.strip().split()
                        if parts:
                            class_id = int(parts[0])
                            class_name = mapping.get(class_id, str(class_id))
                            ids.append(class_name)
            else:
                tree = ET.parse(label_path)
                root = tree.getroot()
                for obj in root.findall(".//object/name"):
                    if obj.text:
                        ids.append(obj.text.strip())
        except Exception:
            pass
        
        return ids
    
# ============================================================
# 线程封装
# ============================================================

class DataWorker(QThread):
    """
    数据处理工作线程
    
    Signals:
        progress(int, int): 进度更新 (current, total)
        message(str): 日志消息
        result_ready(object): 任务完成，携带结果
        error(str): 错误信息
    """
    
    progress = Signal(int, int)
    message = Signal(str)
    result_ready = Signal(object)
    error = Signal(str)
    
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._task: Optional[Callable[[], Any]] = None
        self._is_interrupted: bool = False
    
    def set_task(self, task: Callable[[], Any]) -> None:
        """设置要执行的任务"""
        self._task = task
    
    def request_interrupt(self) -> None:
        """请求中断任务"""
        self._is_interrupted = True
    
    def is_interrupted(self) -> bool:
        """检查是否已请求中断"""
        return self._is_interrupted
    
    def run(self) -> None:
        """执行任务"""
        self._is_interrupted = False
        
        if self._task is None:
            self.error.emit("未设置任务")
            return
        
        try:
            result = self._task()
            self.result_ready.emit(result)
        except Exception as e:
            self.error.emit(str(e))
