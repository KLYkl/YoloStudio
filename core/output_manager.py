"""
output_manager.py - 输出管理器
============================================

职责:
    - 录制视频 (cv2.VideoWriter)
    - 保存关键帧 (只保存有检测结果的帧)
    - 生成检测报告 (JSON 格式)

架构要点:
    - 所有 I/O 操作在调用者线程执行
    - 文件名自动添加时间戳避免覆盖
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from PySide6.QtCore import QObject, Signal

from utils.file_utils import get_unique_dir
from utils.label_writer import write_voc_xml, write_yolo_txt


class OutputManager(QObject):
    """
    输出管理器
    
    管理预测过程中的视频录制、关键帧保存和报告生成。
    
    Signals:
        file_saved(str): 文件保存完成时发射，参数为文件路径
        error_occurred(str): 发生错误时发射，参数为错误信息
    """
    
    file_saved = Signal(str)
    error_occurred = Signal(str)
    
    def __init__(self, parent: Optional[QObject] = None) -> None:
        """初始化输出管理器"""
        super().__init__(parent)
        
        self._output_dir: Optional[Path] = None
        self._video_writer: Any = None  # Bug10-fix: FFmpegVideoWriter 或 None
        self._video_path: Optional[Path] = None
        
        # 统计数据
        self._frame_count: int = 0
        self._keyframe_count: int = 0
        self._detection_stats: dict[str, int] = {}  # {类别名: 检测次数}
        
        # D14-fix: 关键帧目录创建标记 (惰性初始化)
        self._keyframe_dirs_created: bool = False
    
    def set_output_dir(self, output_dir: str | Path, allow_existing: bool = True) -> bool:
        """
        设置输出目录
        
        Args:
            output_dir: 输出目录路径
            allow_existing: 是否允许使用已存在的目录
                - True (默认): 用户手动指定路径时，直接使用该路径（文件会添加到已有文件夹）
                - False: 程序自动创建时，如果路径已存在则添加数字后缀避免覆盖
            
        Returns:
            是否设置成功
        """
        try:
            path = Path(output_dir)
            # 仅当 allow_existing=False 且目录已存在时，才添加数字后缀
            if not allow_existing:
                path = get_unique_dir(path)
            self._output_dir = path
            self._output_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            self.error_occurred.emit(f"创建输出目录失败: {e}")
            return False
    
    def start_video(
        self,
        filename: Optional[str] = None,
        fps: float = 30.0,
        size: tuple[int, int] = (1920, 1080),
        codec: str = "mp4v"
    ) -> bool:
        """
        开始录制视频 (使用 FFmpegVideoWriter H.264 编码)
        
        Args:
            filename: 视频文件名 (不含扩展名)，默认使用时间戳
            fps: 帧率
            size: 视频尺寸 (width, height)
            codec: 编码器 (保留参数, 实际优先用 FFmpeg H.264)
            
        Returns:
            是否成功开始录制
        """
        if self._output_dir is None:
            self.error_occurred.emit("请先设置输出目录")
            return False
        
        if self._video_writer is not None:
            self.stop_video()
        
        # 生成文件名
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"predict_{timestamp}"
        
        self._video_path = self._output_dir / f"{filename}.mp4"
        
        try:
            # Bug10-fix: 统一使用 FFmpegVideoWriter (H.264 编码, 体积小 5-10 倍)
            # FFmpegVideoWriter 内部已有无 ffmpeg 时自动回退 cv2.VideoWriter 的机制
            from core.predict_handler._ffmpeg_writer import FFmpegVideoWriter
            self._video_writer = FFmpegVideoWriter(
                str(self._video_path), fps=fps, size=size
            )
            self._video_size = size
            
            if not self._video_writer.isOpened():
                self.error_occurred.emit("无法创建视频文件")
                self._video_writer = None
                return False
            
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"创建视频文件失败: {e}")
            return False
    
    def write_frame(self, frame: np.ndarray) -> None:
        """
        写入一帧到视频
        
        Args:
            frame: BGR 格式的帧 (OpenCV 格式)
        """
        if self._video_writer is not None and self._video_writer.isOpened():
            try:
                # 确保帧尺寸与 VideoWriter 匹配
                h, w = frame.shape[:2]
                if hasattr(self, '_video_size') and self._video_size and (w, h) != self._video_size:
                    frame = cv2.resize(frame, self._video_size)
                self._video_writer.write(frame)
                self._frame_count += 1
            except Exception as e:
                self.error_occurred.emit(f"写入视频帧失败: {e}")
    
    def _ensure_keyframe_dirs(self) -> None:
        """D14-fix: 惰性初始化关键帧目录（只创建一次）"""
        if self._keyframe_dirs_created or self._output_dir is None:
            return
        (self._output_dir / "keyframes" / "annotated" / "images").mkdir(parents=True, exist_ok=True)
        (self._output_dir / "keyframes" / "raw" / "images").mkdir(parents=True, exist_ok=True)
        (self._output_dir / "keyframes" / "raw" / "labels_yolo").mkdir(parents=True, exist_ok=True)
        (self._output_dir / "keyframes" / "raw" / "labels_voc").mkdir(parents=True, exist_ok=True)
        self._keyframe_dirs_created = True

    def save_keyframe(
        self,
        annotated_frame: np.ndarray,
        detections: list[dict],
        image_prefix: str = "keyframe",
        save_annotated: bool = True,
        save_raw: bool = False,
        raw_frame: Optional[np.ndarray] = None
    ) -> None:
        """
        保存关键帧 (只在有检测结果时调用)
        
        支持两种保存模式:
            - 带框: keyframes/annotated/images/ (无标签)
            - 原图: keyframes/raw/images/ + keyframes/raw/labels/
        
        Args:
            annotated_frame: 标注后的帧 (BGR)
            detections: 检测结果列表，每项包含 {class_id, class_name, confidence, bbox}
                        bbox 格式: [x_center, y_center, width, height] (归一化)
            image_prefix: 文件名前缀
            save_annotated: 是否保存带框图
            save_raw: 是否保存原图
            raw_frame: 原始帧 (BGR)，save_raw=True 时必须提供
        """
        if self._output_dir is None or not detections:
            return
        
        # D14-fix: 确保目录已创建（首次调用时创建，之后跳过）
        self._ensure_keyframe_dirs()
        
        # D13-fix: 时间戳 + 计数器防文件名碰撞
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        base_name = f"{image_prefix}_{timestamp}_{self._keyframe_count:04d}"
        
        try:
            # 保存带框图 (无标签)
            if save_annotated:
                annotated_dir = self._output_dir / "keyframes" / "annotated" / "images"
                image_path = annotated_dir / f"{base_name}.jpg"
                # D16-fix: 检查 imwrite 返回值
                if not cv2.imwrite(str(image_path), annotated_frame):
                    self.error_occurred.emit(f"保存帧框图失败: {image_path}")
                else:
                    self._keyframe_count += 1
                    self.file_saved.emit(str(image_path))
            
            # 保存原图 (含标签: YOLO TXT + VOC XML)
            if save_raw and raw_frame is not None:
                raw_images_dir = self._output_dir / "keyframes" / "raw" / "images"
                labels_yolo_dir = self._output_dir / "keyframes" / "raw" / "labels_yolo"
                labels_voc_dir = self._output_dir / "keyframes" / "raw" / "labels_voc"
                
                # 保存原图
                raw_path = raw_images_dir / f"{base_name}.jpg"
                if not cv2.imwrite(str(raw_path), raw_frame):
                    self.error_occurred.emit(f"保存原图失败: {raw_path}")
                
                # 获取图片尺寸 (用于 VOC XML)
                h, w = raw_frame.shape[:2]
                
                # 保存 YOLO TXT 格式标签
                yolo_label_path = labels_yolo_dir / f"{base_name}.txt"
                write_yolo_txt(yolo_label_path, detections)
                
                # 保存 VOC XML 格式标签
                voc_label_path = labels_voc_dir / f"{base_name}.xml"
                write_voc_xml(voc_label_path, base_name, w, h, detections)
                
                self.file_saved.emit(str(raw_path))
            
            # 更新类别统计
            for det in detections:
                class_name = det.get("class_name", "unknown")
                self._detection_stats[class_name] = self._detection_stats.get(class_name, 0) + 1
            
        except Exception as e:
            self.error_occurred.emit(f"保存关键帧失败: {e}")
    
    def stop_video(self) -> Optional[Path]:
        """
        停止录制视频
        
        Returns:
            视频文件路径，如果未在录制则返回 None
        """
        if self._video_writer is not None:
            self._video_writer.release()
            self._video_writer = None
            
            if self._video_path and self._video_path.exists():
                self.file_saved.emit(str(self._video_path))
                return self._video_path
        
        return None
    
    def generate_report(self, extra_stats: Optional[dict] = None) -> Optional[Path]:
        """
        生成 JSON 检测报告
        
        Args:
            extra_stats: 额外的统计数据 (可选)
            
        Returns:
            报告文件路径，失败返回 None
        """
        if self._output_dir is None:
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self._output_dir / f"report_{timestamp}.json"
        
        report_data: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_frames": self._frame_count,
                "keyframes_saved": self._keyframe_count,
                "detection_by_class": self._detection_stats,
            }
        }
        
        if extra_stats:
            report_data["extra"] = extra_stats
        
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            
            self.file_saved.emit(str(report_path))
            return report_path
            
        except Exception as e:
            self.error_occurred.emit(f"生成报告失败: {e}")
            return None
    
    def reset_stats(self) -> None:
        """重置统计数据"""
        self._frame_count = 0
        self._keyframe_count = 0
        self._detection_stats.clear()
        self._keyframe_dirs_created = False  # D14-fix: 重置目录标记
    
    def get_stats(self) -> dict:
        """
        获取当前统计数据
        
        Returns:
            统计字典
        """
        return {
            "frame_count": self._frame_count,
            "keyframe_count": self._keyframe_count,
            "detection_stats": self._detection_stats.copy(),
        }
    
    # ==================== 图片模式专用方法 ====================
    
    def setup_image_output_dirs(self) -> bool:
        """
        创建图片模式输出目录结构
        
        创建:
            - images/       结果图片
            - labels_txt/   YOLO TXT 标签
            - labels_xml/   VOC XML 标签
            - originals/    原图副本 (可选)
        
        Returns:
            是否成功
        """
        if self._output_dir is None:
            self.error_occurred.emit("请先设置输出目录")
            return False
        
        try:
            (self._output_dir / "images").mkdir(parents=True, exist_ok=True)
            (self._output_dir / "labels_txt").mkdir(parents=True, exist_ok=True)
            (self._output_dir / "labels_xml").mkdir(parents=True, exist_ok=True)
            (self._output_dir / "originals").mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            self.error_occurred.emit(f"创建输出目录失败: {e}")
            return False
    
    def save_image_result(
        self,
        original: np.ndarray,
        annotated: np.ndarray,
        detections: list[dict],
        image_name: str,
        save_original: bool = False,
        save_annotated: bool = True,
        save_labels: bool = True,
        image_size: tuple[int, int] | None = None
    ) -> bool:
        """
        保存图片推理结果
        
        Args:
            original: 原图 (BGR)
            annotated: 标注后的图片 (BGR)
            detections: 检测结果列表
            image_name: 基础文件名 (不含扩展名)
            save_original: 是否保存原图副本
            save_annotated: 是否保存标注图
            save_labels: 是否生成标签文件
            image_size: 图片尺寸 (width, height)，用于 VOC XML
            
        Returns:
            是否成功
        """
        if self._output_dir is None:
            return False
        
        try:
            # 获取图片尺寸
            if image_size is None:
                h, w = original.shape[:2]
                image_size = (w, h)
            
            # 保存标注后的图片
            if save_annotated:
                annotated_path = self._output_dir / "images" / f"{image_name}.jpg"
                cv2.imwrite(str(annotated_path), annotated)
                self._keyframe_count += 1
            
            # 保存原图副本
            if save_original:
                original_path = self._output_dir / "originals" / f"{image_name}.jpg"
                cv2.imwrite(str(original_path), original)
            
            # 生成标签文件
            if save_labels and detections:
                txt_path = self._output_dir / "labels_txt" / f"{image_name}.txt"
                write_yolo_txt(txt_path, detections)
                xml_path = self._output_dir / "labels_xml" / f"{image_name}.xml"
                write_voc_xml(xml_path, image_name, image_size[0], image_size[1], detections)
            
            # 更新类别统计
            for det in detections:
                class_name = det.get("class_name", "unknown")
                self._detection_stats[class_name] = self._detection_stats.get(class_name, 0) + 1
            
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"保存图片结果失败: {e}")
            return False
    

    
    def save_path_list(
        self,
        detected_paths: list,
        empty_paths: list
    ) -> None:
        """
        保存路径列表文件

        Args:
            detected_paths: 有检测结果的图片列表，
                支持两种格式:
                - list[tuple[Path, float]]: (路径, 最大置信度)
                - list[Path]: 仅路径（向后兼容）
            empty_paths: 无检测结果的图片路径列表
        """
        if self._output_dir is None:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            # 保存有检测结果列表
            detected_path = self._output_dir / "detected.txt"
            with open(detected_path, "w", encoding="utf-8") as f:
                f.write(f"# 有检测结果的图片列表\n")
                f.write(f"# 生成时间: {timestamp}\n")
                f.write(f"# 格式: 文件路径 | 最大置信度\n")
                f.write(f"# 总数: {len(detected_paths)}\n")
                for item in detected_paths:
                    if isinstance(item, tuple):
                        path, conf = item
                        f.write(f"{path} | {conf:.4f}\n")
                    else:
                        f.write(f"{item}\n")
            
            # 保存无检测结果列表
            empty_path = self._output_dir / "empty.txt"
            with open(empty_path, "w", encoding="utf-8") as f:
                f.write(f"# 无检测结果的图片列表\n")
                f.write(f"# 生成时间: {timestamp}\n")
                f.write(f"# 总数: {len(empty_paths)}\n")
                for p in empty_paths:
                    f.write(f"{p}\n")
            
            self.file_saved.emit(str(detected_path))
            self.file_saved.emit(str(empty_path))
        except OSError as e:
            self.error_occurred.emit(f"保存路径列表失败: {e}")
    
    def generate_image_report(
        self,
        total_images: int,
        detected_count: int,
        empty_count: int,
        extra_stats: Optional[dict] = None
    ) -> Optional[Path]:
        """
        生成图片处理报告
        
        Args:
            total_images: 总图片数
            detected_count: 有检测结果数
            empty_count: 无检测结果数
            extra_stats: 额外统计
            
        Returns:
            报告文件路径
        """
        if self._output_dir is None:
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self._output_dir / f"report_{timestamp}.json"
        
        report_data: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "type": "image_batch",
            "summary": {
                "total_images": total_images,
                "detected_count": detected_count,
                "empty_count": empty_count,
                "images_saved": self._keyframe_count,
                "detection_by_class": self._detection_stats,
            }
        }
        
        if extra_stats:
            report_data["extra"] = extra_stats
        
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
            
            self.file_saved.emit(str(report_path))
            return report_path
            
        except Exception as e:
            self.error_occurred.emit(f"生成报告失败: {e}")
            return None
