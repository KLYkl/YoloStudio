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

import random
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from PIL import Image
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

class DataHandler:
    """
    数据处理核心逻辑 (纯 Python，不依赖 Qt GUI)
    
    所有耗时方法接收 interrupt_check 参数，用于响应取消请求。
    """
    
    def __init__(self) -> None:
        """初始化数据处理器"""
        self._class_mapping: dict[int, str] = {}  # TXT 类别 ID -> 名称映射
    
    def load_classes_txt(self, classes_file: Path) -> list[str]:
        """
        加载 classes.txt 文件
        
        Args:
            classes_file: classes.txt 文件路径
        
        Returns:
            类别名称列表 (按行顺序)
        """
        if not classes_file.exists():
            return []
        
        classes = []
        with open(classes_file, "r", encoding="utf-8") as f:
            for line in f:
                name = line.strip()
                if name:
                    classes.append(name)
        
        # 构建映射
        self._class_mapping = {i: name for i, name in enumerate(classes)}
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
        
        # 加载类别映射
        if classes_txt and classes_txt.exists():
            self.load_classes_txt(classes_txt)
            if message_callback:
                message_callback(f"已加载类别文件: {len(self._class_mapping)} 个类别")
        
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
                classes_in_file = self._parse_label(label_path, label_format)
                
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
        label_files: list[Path],
        action: ModifyAction,
        old_value: str,
        new_value: str = "",
        backup: bool = True,
        classes_txt: Optional[Path] = None,
        interrupt_check: Callable[[], bool] = lambda: False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        message_callback: Optional[Callable[[str], None]] = None,
    ) -> int:
        """
        批量修改标签文件
        
        Args:
            label_files: 标签文件路径列表
            action: 修改动作 (REPLACE/REMOVE)
            old_value: 原始类别名/ID
            new_value: 新类别名/ID (仅 REPLACE 时使用)
            backup: 是否备份原文件
            classes_txt: classes.txt 路径 (TXT 标签替换时必需)
            interrupt_check: 中断检查函数
            progress_callback: 进度回调
            message_callback: 消息回调
        
        Returns:
            修改的文件数量
        """
        modified_count = 0
        total = len(label_files)
        
        # 加载类别映射 (TXT 替换需要)
        if classes_txt and classes_txt.exists():
            self.load_classes_txt(classes_txt)
        
        for i, label_path in enumerate(label_files):
            if interrupt_check():
                if message_callback:
                    message_callback("修改已取消")
                break
            
            if not label_path.exists():
                continue
            
            # 备份
            if backup:
                backup_path = label_path.with_suffix(label_path.suffix + ".bak")
                shutil.copy2(label_path, backup_path)
            
            # 根据文件类型处理
            if label_path.suffix.lower() == ".xml":
                modified = self._modify_xml(label_path, action, old_value, new_value)
            else:
                modified = self._modify_txt(label_path, action, old_value, new_value)
            
            if modified:
                modified_count += 1
            
            if progress_callback:
                progress_callback(i + 1, total)
        
        if message_callback:
            message_callback(f"已修改 {modified_count} 个标签文件")
        
        return modified_count
    
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
            yaml_content = {
                "path": str(output_path.parent),
                "train": train_path,
                "val": val_path,
                "names": {i: name for i, name in enumerate(classes)},
            }
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(yaml_content, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            
            if message_callback:
                message_callback(f"YAML 配置已保存: {output_path}")
            
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
        
        if to_xml:
            # TXT → XML
            label_files = list(root.rglob("*.txt"))
            # 过滤非标签文件
            label_files = [f for f in label_files if not f.name.startswith(("classes", "train", "val", "test"))]
            output_dir_name = "converted_labels_xml"
            target_ext = ".xml"
        else:
            # XML → TXT
            label_files = list(root.rglob("*.xml"))
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
                output_path = output_dir / (label_path.stem + target_ext)
                
                if to_xml:
                    # TXT → XML
                    success = self._convert_txt_to_xml(label_path, id_to_class, root, output_path)
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
    
    def _convert_txt_to_xml(self, txt_path: Path, id_to_class: dict, root: Path, output_path: Path) -> bool:
        """将 TXT 标签转换为 XML"""
        # 查找对应的图片
        img_path = self._find_image_for_label(txt_path, root)
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
    
    def _find_image_for_label(self, label_path: Path, root: Path) -> Optional[Path]:
        """根据标签文件查找对应的图片"""
        stem = label_path.stem
        
        # 1. 同目录
        for ext in IMAGE_EXTENSIONS:
            img_path = label_path.with_suffix(ext)
            if img_path.exists():
                return img_path
        
        # 2. 目录映射 (labels → images, Annotations → JPEGImages)
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
    
    def _parse_label(self, label_path: Path, label_format: LabelFormat) -> list[str]:
        """解析标签文件，返回类别列表"""
        classes = []
        
        try:
            if label_format == LabelFormat.TXT:
                with open(label_path, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.strip().split()
                        if parts:
                            class_id = int(parts[0])
                            # 无 classes.txt 时直接使用数字字符串，无前缀
                            class_name = self._class_mapping.get(class_id, str(class_id))
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
    
    def _modify_xml(self, label_path: Path, action: ModifyAction, old_value: str, new_value: str) -> bool:
        """修改 XML 标签文件"""
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
            
            if modified:
                ET.indent(tree, space="    ")
                tree.write(label_path, encoding="utf-8", xml_declaration=True)
            
            return modified
            
        except Exception:
            return False
    
    def _modify_txt(self, label_path: Path, action: ModifyAction, old_value: str, new_value: str) -> bool:
        """修改 TXT 标签文件"""
        try:
            # 将类别名转换为 ID
            old_id = None
            new_id = None
            
            for id_, name in self._class_mapping.items():
                if name == old_value or str(id_) == old_value:
                    old_id = id_
                if name == new_value or str(id_) == new_value:
                    new_id = id_
            
            if old_id is None:
                return False
            
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
                        continue  # 跳过此行
                else:
                    new_lines.append(line)
            
            if modified:
                with open(label_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
            
            return modified
            
        except Exception:
            return False
    
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
        """索引文件模式划分"""
        train_txt = root / "train.txt"
        val_txt = root / "val.txt"
        
        with open(train_txt, "w", encoding="utf-8") as f:
            for img in train_images:
                f.write(str(img.absolute()) + "\n")
        
        with open(val_txt, "w", encoding="utf-8") as f:
            for img in val_images:
                f.write(str(img.absolute()) + "\n")
        
        if message_callback:
            message_callback(f"已生成索引文件: {train_txt.name}, {val_txt.name}")
        
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
        if classes_txt and classes_txt.exists():
            self.load_classes_txt(classes_txt)
            if message_callback:
                message_callback(f"已加载类别文件: {len(self._class_mapping)} 个类别")
        
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
                class_ids = self._parse_label_ids(label_path, label_format)
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
    
    def _parse_label_ids(self, label_path: Path, label_format: LabelFormat) -> list[str]:
        """
        解析标签文件，返回类别标识列表 (字符串形式)
        
        - TXT 格式: 如果有 _class_mapping，返回映射后的名称；否则返回原始数字 ID
        - XML 格式: 直接返回 <name> 标签内容
        """
        ids: list[str] = []
        
        try:
            if label_format == LabelFormat.TXT:
                with open(label_path, "r", encoding="utf-8") as f:
                    for line in f:
                        parts = line.strip().split()
                        if parts:
                            class_id = int(parts[0])
                            # 如果有类别映射，使用名称；否则使用原始数字
                            class_name = self._class_mapping.get(class_id, str(class_id))
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
        finished(object): 任务完成，携带结果
        error(str): 错误信息
    """
    
    progress = Signal(int, int)
    message = Signal(str)
    finished = Signal(object)
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
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
