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

from core.predict_handler._frame_decoder import extract_detections_fast
from core.predict_handler._inference_utils import run_inference, draw_detections

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

        # 控制标志 (受 _state_lock 保护)
        self._running: bool = False
        self._stop_requested: bool = False
        self._state_lock = Lock()

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
        with self._state_lock:
            self._stop_requested = True
        self._pause_event.set()

    def pause(self) -> None:
        """请求暂停推理"""
        should_emit = False
        with self._state_lock:
            if self._running and self._playback_state == PlaybackState.PLAYING:
                self._pause_event.clear()
                self._playback_state = PlaybackState.PAUSED
                should_emit = True
        # 信号发射放在锁外，避免死锁
        if should_emit:
            self.state_changed.emit(PlaybackState.PAUSED.value)
            self._logger.info("推理已暂停")

    def resume(self) -> None:
        """请求恢复推理"""
        should_emit = False
        with self._state_lock:
            if self._running and self._playback_state == PlaybackState.PAUSED:
                self._pause_event.set()
                self._playback_state = PlaybackState.PLAYING
                should_emit = True
        # 信号发射放在锁外，避免死锁
        if should_emit:
            self.state_changed.emit(PlaybackState.PLAYING.value)
            self._logger.info("推理已恢复")

    def seek(self, frame_index: int) -> None:
        """请求跳转到指定帧（仅视频文件有效）"""
        if self._source_type != InputSourceType.VIDEO:
            return

        with self._state_lock:
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
        with self._state_lock:
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

        with self._state_lock:
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
            with self._state_lock:
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

        annotated_frame, detections = run_inference(self._model, frame, conf, iou)
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

        # Bug1-fix: 初始化变量, 防止 seek 分支导致补发逻辑引用未定义变量
        frame: Optional[np.ndarray] = None
        detections: list = []

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
                                annotated_frame = draw_detections(frame, detections)
                                self._logger.debug(f"缓存命中: 帧 {target}")
                            else:
                                with self._params_lock:
                                    conf, iou = self._conf, self._iou
                                annotated_frame, detections = run_inference(self._model, frame, conf, iou)
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
                                    annotated_frame, detections = run_inference(self._model, frame, conf, iou)
                                    self._detection_cache[self._current_frame] = detections
                                    self.frame_ready.emit(annotated_frame, frame, detections)
                                    self.progress_updated.emit(self._current_frame, self._total_frames)
                                self._pause_event.clear()
                                self._playback_state = PlaybackState.PAUSED
                                self.state_changed.emit(PlaybackState.PAUSED.value)
                                self._logger.debug("Seek 完成，恢复暂停状态")
                                continue

                frame_start_time = time.time()
                ret, frame = cap.read()
                if not ret:
                    if is_video_file:
                        break
                    time.sleep(0.1)
                    continue

                self._current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

                with self._params_lock:
                    conf, iou = self._conf, self._iou

                # 推理 (GPU)
                results = self._model(frame, conf=conf, iou=iou, half=True, verbose=False)

                # 向量化提取: 一次性 GPU→CPU 批量传输
                detections = extract_detections_fast(
                    results[0].boxes, self._model.names
                )

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

                # 信号节流: 最多约 60fps 发射一次, 减少跨线程开销
                # 只在需要发射时才画框 (plot 是纯 CPU 操作)
                emit_interval = 0.016  # ~60fps 上限
                if current_time - last_progress_time >= emit_interval:
                    annotated_frame = draw_detections(frame, detections) if detections else frame
                    self.frame_ready.emit(annotated_frame, frame, detections)
                    self.stats_updated.emit({
                        "fps": round(current_fps, 1),
                        "frame_count": frame_count,
                        "object_count": len(detections),
                    })
                    if is_video_file:
                        self.progress_updated.emit(self._current_frame, self._total_frames)
                    last_progress_time = current_time

            # Bug9-fix: 循环退出后补发最终帧, 避免节流跳过最后几帧
            # Bug1-fix: 增加 frame is not None 保护
            if frame_count > 0 and frame is not None:
                annotated_frame = draw_detections(frame, detections) if detections else frame
                self.frame_ready.emit(annotated_frame, frame, detections)
                self.stats_updated.emit({
                    "fps": round(current_fps, 1),
                    "frame_count": frame_count,
                    "object_count": len(detections),
                })
                if is_video_file:
                    self.progress_updated.emit(self._current_frame, self._total_frames)

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

                    annotated_frame, detections = run_inference(self._model, frame, conf, iou)

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


