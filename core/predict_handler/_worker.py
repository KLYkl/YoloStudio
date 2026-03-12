"""
_worker.py - PredictWorker: 推理工作线程
============================================
"""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import Event, Lock
from typing import Any, Optional

import cv2
import numpy as np

try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

from PySide6.QtCore import QObject, Signal, Slot

from core.predict_handler._models import InputSourceType, PlaybackState
from utils.logger import get_logger


class PredictWorker(QObject):
    """
    预测工作线程

    在独立线程中运行推理循环，通过信号发送结果。

    Signals:
        frame_ready(np.ndarray, list): 标注后的帧和检测结果
        stats_updated(dict): 统计数据更新
        error_occurred(str): 错误消息
        finished(): 推理结束
        state_changed(str): 播放状态变化
        progress_updated(int, int): (当前帧, 总帧数)
    """

    # 信号: (标注帧, 原始帧, 检测结果)
    frame_ready = Signal(np.ndarray, np.ndarray, list)
    stats_updated = Signal(dict)
    error_occurred = Signal(str)
    finished = Signal()
    state_changed = Signal(str)
    progress_updated = Signal(int, int)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self._model: Any = None
        self._source: Optional[str | int] = None
        self._source_type: InputSourceType = InputSourceType.VIDEO

        # 推理参数 (可实时更新)
        self._conf: float = 0.5
        self._iou: float = 0.45
        self._params_lock = Lock()

        # 控制标志
        self._running: bool = False
        self._stop_requested: bool = False

        # 暂停控制 (使用 Event 而非 bool，线程安全)
        self._pause_event = Event()
        self._pause_event.set()  # 初始为 "运行" 状态
        self._playback_state: PlaybackState = PlaybackState.IDLE

        # Seek 控制
        self._seek_requested: Optional[int] = None
        self._seek_lock = Lock()
        self._paused_before_seek: bool = False

        # 视频信息
        self._total_frames: int = 0
        self._current_frame: int = 0

        # 检测结果缓存 {frame_index: [detections]}
        self._detection_cache: OrderedDict[int, list] = OrderedDict()
        self._max_cache_frames: int = 1000

        # 屏幕截图区域
        self._screen_region: Optional[dict] = None

        # 日志
        self._logger = get_logger()

    def set_model(self, model: Any) -> None:
        """设置 YOLO 模型实例"""
        self._model = model

    def set_source(
        self,
        source: str | int,
        source_type: InputSourceType,
        screen_region: Optional[dict] = None
    ) -> None:
        """设置输入源"""
        self._source = source
        self._source_type = source_type
        self._screen_region = screen_region

    def update_params(self, conf: float, iou: float) -> None:
        """实时更新推理参数"""
        with self._params_lock:
            self._conf = conf
            self._iou = iou

    def stop(self) -> None:
        """请求停止推理"""
        self._stop_requested = True
        self._pause_event.set()

    def pause(self) -> None:
        """请求暂停推理"""
        if self._running and self._playback_state == PlaybackState.PLAYING:
            self._pause_event.clear()
            self._playback_state = PlaybackState.PAUSED
            self.state_changed.emit(PlaybackState.PAUSED.value)
            self._logger.info("推理已暂停")

    def resume(self) -> None:
        """请求恢复推理"""
        if self._running and self._playback_state == PlaybackState.PAUSED:
            self._pause_event.set()
            self._playback_state = PlaybackState.PLAYING
            self.state_changed.emit(PlaybackState.PLAYING.value)
            self._logger.info("推理已恢复")

    def seek(self, frame_index: int) -> None:
        """请求跳转到指定帧（仅视频文件有效）"""
        if self._source_type != InputSourceType.VIDEO:
            return

        was_paused = self._playback_state == PlaybackState.PAUSED
        self._logger.debug(f"Seek 请求: 帧 {frame_index}, 暂停状态: {was_paused}")

        with self._seek_lock:
            self._seek_requested = frame_index
            self._paused_before_seek = was_paused

        if was_paused:
            self._pause_event.set()

    @property
    def is_paused(self) -> bool:
        """当前是否暂停"""
        return self._playback_state == PlaybackState.PAUSED

    @property
    def total_frames(self) -> int:
        """视频总帧数"""
        return self._total_frames

    @property
    def current_frame(self) -> int:
        """当前帧索引"""
        return self._current_frame

    @Slot()
    def run(self) -> None:
        """执行推理循环"""
        if self._model is None:
            self.error_occurred.emit("模型未加载")
            self.finished.emit()
            return

        self._running = True
        self._stop_requested = False
        self._detection_cache.clear()

        try:
            if self._source_type == InputSourceType.IMAGE:
                self._process_image()
            elif self._source_type == InputSourceType.SCREEN:
                self._process_screen()
            else:
                self._process_video_stream()
        except Exception as e:
            self.error_occurred.emit(f"推理错误: {e}")
        finally:
            self._running = False
            self.finished.emit()

    def _process_image(self) -> None:
        """处理单张图片"""
        if self._source is None:
            return

        frame = cv2.imread(str(self._source))
        if frame is None:
            self.error_occurred.emit(f"无法读取图片: {self._source}")
            return

        with self._params_lock:
            conf, iou = self._conf, self._iou

        annotated_frame, detections = self._run_inference(frame, conf, iou)
        self.frame_ready.emit(annotated_frame, frame, detections)

        self.stats_updated.emit({
            "fps": 0,
            "frame_count": 1,
            "object_count": len(detections),
        })

    def _process_video_stream(self) -> None:
        """处理视频/摄像头/RTSP 流"""
        cap = cv2.VideoCapture(self._source)

        if not cap.isOpened():
            self.error_occurred.emit(f"无法打开视频源: {self._source}")
            return

        is_video_file = self._source_type == InputSourceType.VIDEO
        if is_video_file:
            self._total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        else:
            self._total_frames = 0
            video_fps = 30.0

        self._current_frame = 0
        frame_count = 0
        start_time = time.time()
        fps_update_interval = 0.5
        last_fps_time = start_time
        fps_frame_count = 0
        current_fps = 0.0

        last_progress_time = start_time
        progress_update_interval = 0.1

        self._playback_state = PlaybackState.PLAYING
        self.state_changed.emit(PlaybackState.PLAYING.value)

        try:
            while not self._stop_requested:
                if not self._pause_event.wait(timeout=0.1):
                    if self._stop_requested:
                        break
                    with self._seek_lock:
                        if self._seek_requested is not None:
                            target = self._seek_requested
                            self._seek_requested = None
                        else:
                            continue
                    if is_video_file and target is not None:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                        self._current_frame = target
                        ret, frame = cap.read()
                        if ret:
                            if target in self._detection_cache:
                                detections = self._detection_cache[target]
                                annotated_frame = self._draw_cached_detections(frame, detections)
                                self._logger.debug(f"缓存命中: 帧 {target}")
                            else:
                                with self._params_lock:
                                    conf, iou = self._conf, self._iou
                                annotated_frame, detections = self._run_inference(frame, conf, iou)
                                self._detection_cache[target] = detections
                            self.frame_ready.emit(annotated_frame, frame, detections)
                            self.progress_updated.emit(self._current_frame, self._total_frames)
                        self._pause_event.clear()
                        self.state_changed.emit(PlaybackState.PAUSED.value)
                    continue

                with self._seek_lock:
                    if self._seek_requested is not None:
                        target = self._seek_requested
                        was_paused = self._paused_before_seek
                        self._seek_requested = None
                        self._paused_before_seek = False
                        self._logger.debug(f"处理 Seek: 帧 {target}, 需要保持暂停: {was_paused}")
                        if is_video_file:
                            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                            self._current_frame = target
                            frame_count = target
                            if was_paused:
                                ret, frame = cap.read()
                                if ret:
                                    with self._params_lock:
                                        conf, iou = self._conf, self._iou
                                    annotated_frame, detections = self._run_inference(frame, conf, iou)
                                    self._detection_cache[self._current_frame] = detections
                                    self.frame_ready.emit(annotated_frame, frame, detections)
                                    self.progress_updated.emit(self._current_frame, self._total_frames)
                                self._pause_event.clear()
                                self._playback_state = PlaybackState.PAUSED
                                self.state_changed.emit(PlaybackState.PAUSED.value)
                                self._logger.debug("Seek 完成，恢复暂停状态")
                                continue

                ret, frame = cap.read()
                if not ret:
                    if is_video_file:
                        break
                    time.sleep(0.1)
                    continue

                self._current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

                with self._params_lock:
                    conf, iou = self._conf, self._iou

                annotated_frame, detections = self._run_inference(frame, conf, iou)

                if is_video_file:
                    self._detection_cache[self._current_frame] = detections
                    while len(self._detection_cache) > self._max_cache_frames:
                        self._detection_cache.popitem(last=False)

                frame_count += 1
                fps_frame_count += 1

                current_time = time.time()
                if current_time - last_fps_time >= fps_update_interval:
                    current_fps = fps_frame_count / (current_time - last_fps_time)
                    last_fps_time = current_time
                    fps_frame_count = 0

                self.frame_ready.emit(annotated_frame, frame, detections)
                self.stats_updated.emit({
                    "fps": round(current_fps, 1),
                    "frame_count": frame_count,
                    "object_count": len(detections),
                })

                if is_video_file and current_time - last_progress_time >= progress_update_interval:
                    self.progress_updated.emit(self._current_frame, self._total_frames)
                    last_progress_time = current_time

        finally:
            self._playback_state = PlaybackState.IDLE
            self.state_changed.emit(PlaybackState.IDLE.value)
            cap.release()

    def _process_screen(self) -> None:
        """处理屏幕录制"""
        if not MSS_AVAILABLE:
            self.error_occurred.emit("屏幕录制需要安装 mss 库")
            return

        if self._screen_region is None:
            self.error_occurred.emit("未指定屏幕区域")
            return

        frame_count = 0
        start_time = time.time()
        fps_update_interval = 0.5
        last_fps_time = start_time
        fps_frame_count = 0
        current_fps = 0.0

        self._playback_state = PlaybackState.PLAYING
        self.state_changed.emit(PlaybackState.PLAYING.value)

        try:
            with mss.mss() as sct:
                while not self._stop_requested:
                    if not self._pause_event.wait(timeout=0.1):
                        if self._stop_requested:
                            break
                        continue

                    screenshot = sct.grab(self._screen_region)
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                    with self._params_lock:
                        conf, iou = self._conf, self._iou

                    annotated_frame, detections = self._run_inference(frame, conf, iou)

                    frame_count += 1
                    fps_frame_count += 1

                    current_time = time.time()
                    if current_time - last_fps_time >= fps_update_interval:
                        current_fps = fps_frame_count / (current_time - last_fps_time)
                        last_fps_time = current_time
                        fps_frame_count = 0

                    self.frame_ready.emit(annotated_frame, frame, detections)
                    self.stats_updated.emit({
                        "fps": round(current_fps, 1),
                        "frame_count": frame_count,
                        "object_count": len(detections),
                    })

                    time.sleep(0.033)  # ~30 FPS

        except Exception as e:
            self.error_occurred.emit(f"屏幕录制错误: {e}")
        finally:
            self._playback_state = PlaybackState.IDLE
            self.state_changed.emit(PlaybackState.IDLE.value)

    def _run_inference(
        self,
        frame: np.ndarray,
        conf: float,
        iou: float
    ) -> tuple[np.ndarray, list[dict]]:
        """执行单帧推理"""
        results = self._model(frame, conf=conf, iou=iou, verbose=False)

        annotated_frame = results[0].plot()

        detections = []
        boxes = results[0].boxes

        if boxes is not None and len(boxes) > 0:
            h, w = frame.shape[:2]

            for i in range(len(boxes)):
                xyxy = boxes.xyxy[i].cpu().numpy()
                x1, y1, x2, y2 = xyxy

                x_center = (x1 + x2) / 2 / w
                y_center = (y1 + y2) / 2 / h
                box_w = (x2 - x1) / w
                box_h = (y2 - y1) / h

                class_id = int(boxes.cls[i].cpu().numpy())
                confidence = float(boxes.conf[i].cpu().numpy())
                class_name = self._model.names.get(class_id, str(class_id))

                detections.append({
                    "class_id": class_id,
                    "class_name": class_name,
                    "confidence": confidence,
                    "bbox": [x_center, y_center, box_w, box_h],
                    "xyxy": [x1, y1, x2, y2],
                })

        return annotated_frame, detections

    def _draw_cached_detections(
        self,
        frame: np.ndarray,
        detections: list[dict]
    ) -> np.ndarray:
        """从缓存的检测结果绘制边界框"""
        annotated = frame.copy()

        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["xyxy"]]
            class_name = det["class_name"]
            confidence = det["confidence"]
            class_id = det["class_id"]

            color = self._get_class_color(class_id)

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            label = f"{class_name} {confidence:.2f}"
            (label_w, label_h), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
            )
            cv2.rectangle(
                annotated,
                (x1, y1 - label_h - baseline - 4),
                (x1 + label_w, y1),
                color,
                -1
            )

            cv2.putText(
                annotated,
                label,
                (x1, y1 - baseline - 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1
            )

        return annotated

    def _get_class_color(self, class_id: int) -> tuple[int, int, int]:
        """获取类别对应的颜色"""
        colors = [
            (255, 56, 56), (255, 157, 151), (255, 112, 31), (255, 178, 29),
            (207, 210, 49), (72, 249, 10), (146, 204, 23), (61, 219, 134),
            (26, 147, 52), (0, 212, 187), (44, 153, 168), (0, 194, 255),
            (52, 69, 147), (100, 115, 255), (0, 24, 236), (132, 56, 255),
            (82, 0, 133), (203, 56, 255), (255, 149, 200), (255, 55, 199),
        ]
        return colors[class_id % len(colors)]
