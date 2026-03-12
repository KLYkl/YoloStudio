"""
_video_batch.py - VideoBatchProcessor: 视频批量处理器
============================================
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import cv2

from PySide6.QtCore import QObject, Signal

from utils.logger import get_logger


class VideoBatchProcessor(QObject):
    """
    视频批量处理器

    专门用于批量处理多个视频文件，支持：
    - 批量加载视频文件夹或多选视频
    - 逐个处理每个视频
    - 每个视频独立输出目录
    - 生成汇总报告

    Signals:
        video_started(str, int, int): (视频路径, 当前索引, 总数)
        video_finished(str, dict): (视频路径, 统计数据)
        frame_progress(int, int): (当前帧, 总帧数)
        batch_progress(int, int): (已完成视频数, 总视频数)
        batch_finished(): 全部处理完成
        error_occurred(str): 错误消息
    """

    # 信号定义
    video_started = Signal(str, int, int)
    video_finished = Signal(str, dict)
    frame_progress = Signal(int, int)
    batch_progress = Signal(int, int)
    batch_finished = Signal()
    error_occurred = Signal(str)

    # 支持的视频格式
    VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"}

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self._model: Any = None
        self._conf: float = 0.5
        self._iou: float = 0.45

        # 视频列表
        self._video_list: list[Path] = []

        # 已处理的视频统计 {video_path: stats_dict}
        self._video_stats: dict[Path, dict] = {}

        # 当前处理索引
        self._current_index: int = -1

        # 控制标志
        self._stop_requested: bool = False
        self._pause_requested: bool = False
        self._is_paused: bool = False
        self._is_running: bool = False

        # 输出配置
        self._output_dir: Optional[Path] = None
        self._save_video: bool = False
        self._save_keyframes_annotated: bool = True
        self._save_keyframes_raw: bool = False
        self._save_report: bool = True
        self._high_conf_only: bool = False
        self._high_conf_threshold: float = 0.7

        self._logger = get_logger()

    def set_model(self, model: Any) -> None:
        """设置 YOLO 模型实例（共享，避免重复加载）"""
        self._model = model

    def update_params(
        self,
        conf: float,
        iou: float,
        high_conf_threshold: float = 0.7
    ) -> None:
        """更新推理参数"""
        self._conf = conf
        self._iou = iou
        self._high_conf_threshold = high_conf_threshold

    def set_output_options(
        self,
        output_dir: str | Path,
        save_video: bool = False,
        save_keyframes_annotated: bool = True,
        save_keyframes_raw: bool = False,
        save_report: bool = True,
        high_conf_only: bool = False
    ) -> None:
        """设置输出选项"""
        self._output_dir = Path(output_dir) if output_dir else None
        self._save_video = save_video
        self._save_keyframes_annotated = save_keyframes_annotated
        self._save_keyframes_raw = save_keyframes_raw
        self._save_report = save_report
        self._high_conf_only = high_conf_only

    def load_videos(self, source: str | Path | list[str] | list[Path]) -> int:
        """加载视频列表"""
        self._video_list.clear()
        self._video_stats.clear()
        self._current_index = -1

        if isinstance(source, (str, Path)):
            source_path = Path(source)
            if source_path.is_dir():
                for ext in self.VIDEO_EXTENSIONS:
                    self._video_list.extend(source_path.glob(f"*{ext}"))
                seen = set()
                unique_list = []
                for p in self._video_list:
                    key = p.resolve()
                    if key not in seen:
                        seen.add(key)
                        unique_list.append(p)
                unique_list.sort(key=lambda p: p.name.lower())
                self._video_list = unique_list
            elif source_path.is_file() and source_path.suffix.lower() in self.VIDEO_EXTENSIONS:
                self._video_list.append(source_path)
        elif isinstance(source, list):
            for p in source:
                path = Path(p)
                if path.is_file() and path.suffix.lower() in self.VIDEO_EXTENSIONS:
                    self._video_list.append(path)

        self._logger.info(f"视频加载完成: {len(self._video_list)} 个")
        return len(self._video_list)

    @property
    def video_count(self) -> int:
        """视频总数"""
        return len(self._video_list)

    @property
    def processed_count(self) -> int:
        """已处理数量"""
        return len(self._video_stats)

    @property
    def current_index(self) -> int:
        """当前处理索引"""
        return self._current_index

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._is_running

    @property
    def is_paused(self) -> bool:
        """是否暂停"""
        return self._is_paused

    def process_all(self) -> None:
        """批量处理所有视频 (应在 QThread 中调用)"""
        if self._model is None:
            self.error_occurred.emit("模型未加载")
            return

        if not self._video_list:
            self.error_occurred.emit("视频列表为空")
            return

        self._is_running = True
        self._stop_requested = False
        self._video_stats.clear()

        total = len(self._video_list)

        for i, video_path in enumerate(self._video_list):
            if self._stop_requested:
                self._logger.info("批量处理被用户中止")
                break

            self._current_index = i
            self.video_started.emit(str(video_path), i, total)
            self._logger.info(f"开始处理视频 [{i+1}/{total}]: {video_path.name}")

            stats = self._process_single_video(video_path)

            if stats:
                self._video_stats[video_path] = stats
                self.video_finished.emit(str(video_path), stats)

            self.batch_progress.emit(i + 1, total)

        self._is_running = False
        self.batch_finished.emit()
        self._logger.info(f"批量处理完成: {len(self._video_stats)}/{total} 个视频")

    def _process_single_video(self, video_path: Path) -> dict | None:
        """处理单个视频"""
        cap = cv2.VideoCapture(str(video_path))

        if not cap.isOpened():
            self.error_occurred.emit(f"无法打开视频: {video_path}")
            return None

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # 创建视频专用输出目录
        video_output_dir = None
        video_writer = None
        keyframe_dir = None
        raw_keyframe_dir = None
        raw_labels_dir = None
        raw_labels_voc_dir = None

        if self._output_dir:
            video_output_dir = self._output_dir / video_path.stem
            if video_output_dir.exists():
                from datetime import datetime as _dt
                ts = _dt.now().strftime("%Y%m%d_%H%M%S")
                video_output_dir = self._output_dir / f"{video_path.stem}_{ts}"
            video_output_dir.mkdir(parents=True, exist_ok=True)

            if self._save_video:
                output_video_path = video_output_dir / f"{video_path.stem}_result.mp4"
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                video_writer = cv2.VideoWriter(
                    str(output_video_path), fourcc, fps, (width, height)
                )

            if self._save_keyframes_annotated:
                keyframe_dir = video_output_dir / "keyframes" / "annotated"
                keyframe_dir.mkdir(parents=True, exist_ok=True)

            if self._save_keyframes_raw:
                raw_keyframe_dir = video_output_dir / "keyframes" / "raw" / "images"
                raw_labels_dir = video_output_dir / "keyframes" / "raw" / "labels_yolo"
                raw_labels_voc_dir = video_output_dir / "keyframes" / "raw" / "labels_voc"
                raw_keyframe_dir.mkdir(parents=True, exist_ok=True)
                raw_labels_dir.mkdir(parents=True, exist_ok=True)
                raw_labels_voc_dir.mkdir(parents=True, exist_ok=True)

        stats = {
            "video_name/视频名称": video_path.name,
            "total_frames/总帧数": total_frames,
            "processed_frames/已处理帧数": 0,
            "detection_count/检测数量": 0,
            "keyframes_saved/已保存关键帧": 0,
            "fps/帧率": fps,
            "resolution/分辨率": f"{width}x{height}",
        }

        frame_idx = 0
        keyframe_count = 0

        try:
            while not self._stop_requested:
                while self._pause_requested:
                    self._is_paused = True
                    time.sleep(0.1)
                    if self._stop_requested:
                        break
                self._is_paused = False

                ret, frame = cap.read()
                if not ret:
                    break

                results = self._model(frame, conf=self._conf, iou=self._iou, verbose=False)
                annotated_frame = results[0].plot()

                boxes = results[0].boxes
                detections = []

                if boxes is not None and len(boxes) > 0:
                    for j in range(len(boxes)):
                        xyxy = boxes.xyxy[j].cpu().numpy()
                        class_id = int(boxes.cls[j].cpu().numpy())
                        confidence = float(boxes.conf[j].cpu().numpy())
                        class_name = self._model.names.get(class_id, str(class_id))

                        detections.append({
                            "class_id": class_id,
                            "class_name": class_name,
                            "confidence": confidence,
                            "xyxy": [float(x) for x in xyxy],
                        })

                    stats["detection_count/检测数量"] += len(detections)

                if video_writer:
                    video_writer.write(annotated_frame)

                if (keyframe_dir or raw_keyframe_dir) and detections:
                    should_save = True
                    if self._high_conf_only:
                        should_save = any(
                            d["confidence"] >= self._high_conf_threshold
                            for d in detections
                        )

                    if should_save:
                        if keyframe_dir:
                            keyframe_path = keyframe_dir / f"frame_{frame_idx:06d}.jpg"
                            cv2.imwrite(str(keyframe_path), annotated_frame)

                        if raw_keyframe_dir:
                            frame_name = f"frame_{frame_idx:06d}"
                            raw_path = raw_keyframe_dir / f"{frame_name}.jpg"
                            cv2.imwrite(str(raw_path), frame)

                            h_frame, w_frame = frame.shape[:2]

                            # YOLO TXT
                            label_path = raw_labels_dir / f"{frame_name}.txt"
                            with open(label_path, "w", encoding="utf-8") as f:
                                for d in detections:
                                    cid = d["class_id"]
                                    x1, y1, x2, y2 = d["xyxy"]
                                    xc = (x1 + x2) / 2 / w_frame
                                    yc = (y1 + y2) / 2 / h_frame
                                    bw = (x2 - x1) / w_frame
                                    bh = (y2 - y1) / h_frame
                                    f.write(f"{cid} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")

                            # VOC XML
                            if raw_labels_voc_dir:
                                self._write_voc_xml(
                                    raw_labels_voc_dir / f"{frame_name}.xml",
                                    frame_name, w_frame, h_frame, detections
                                )

                        keyframe_count += 1

                frame_idx += 1
                stats["processed_frames/已处理帧数"] = frame_idx

                if frame_idx % 10 == 0 or frame_idx == total_frames:
                    self.frame_progress.emit(frame_idx, total_frames)

        finally:
            cap.release()
            if video_writer:
                video_writer.release()

        stats["keyframes_saved/已保存关键帧"] = keyframe_count

        if self._save_report and video_output_dir:
            report_path = video_output_dir / "report.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)

        return stats

    def stop(self) -> None:
        """停止批量处理"""
        self._stop_requested = True
        self._pause_requested = False

    def pause(self) -> None:
        """暂停批量处理"""
        self._pause_requested = True

    def resume(self) -> None:
        """继续批量处理"""
        self._pause_requested = False

    def get_video_list(self) -> list[Path]:
        """获取视频列表"""
        return self._video_list.copy()

    def get_all_stats(self) -> dict[str, dict]:
        """获取所有视频的统计数据"""
        return {str(k): v for k, v in self._video_stats.items()}

    def _write_voc_xml(
        self, xml_path: Path, image_name: str,
        width: int, height: int, detections: list[dict]
    ) -> None:
        """写入 VOC XML 格式标签"""
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<annotation>',
            f'    <filename>{image_name}.jpg</filename>',
            '    <size>',
            f'        <width>{width}</width>',
            f'        <height>{height}</height>',
            '        <depth>3</depth>',
            '    </size>',
        ]
        for det in detections:
            name = det.get("class_name", "unknown")
            xyxy = det.get("xyxy", [0, 0, 0, 0])
            x1, y1, x2, y2 = [int(v) for v in xyxy]
            xml_lines.extend([
                '    <object>',
                f'        <name>{name}</name>',
                '        <pose>Unspecified</pose>',
                '        <truncated>0</truncated>',
                '        <difficult>0</difficult>',
                '        <bndbox>',
                f'            <xmin>{x1}</xmin>',
                f'            <ymin>{y1}</ymin>',
                f'            <xmax>{x2}</xmax>',
                f'            <ymax>{y2}</ymax>',
                '        </bndbox>',
                '    </object>',
            ])
        xml_lines.append('</annotation>')
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write("\n".join(xml_lines))

    def generate_batch_report(self) -> Path | None:
        """生成批量处理汇总报告"""
        if not self._output_dir or not self._video_stats:
            return None

        report = {
            "generated_at/生成时间": datetime.now().isoformat(),
            "total_videos/视频总数": len(self._video_list),
            "processed_videos/已处理视频数": len(self._video_stats),
            "total_frames/总帧数": sum(s["processed_frames/已处理帧数"] for s in self._video_stats.values()),
            "total_detections/总检测数": sum(s["detection_count/检测数量"] for s in self._video_stats.values()),
            "total_keyframes/总关键帧数": sum(s["keyframes_saved/已保存关键帧"] for s in self._video_stats.values()),
            "videos/视频列表": [
                {
                    "name/名称": stats["video_name/视频名称"],
                    "frames/帧数": stats["processed_frames/已处理帧数"],
                    "detections/检测数": stats["detection_count/检测数量"],
                    "keyframes/关键帧数": stats["keyframes_saved/已保存关键帧"],
                }
                for stats in self._video_stats.values()
            ],
        }

        report_path = self._output_dir / "batch_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        self._logger.info(f"批量报告已生成: {report_path}")
        return report_path
