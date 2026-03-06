"""
predict_handler.py - 预测核心管理器
============================================

职责:
    - 加载 YOLO 模型
    - 在子线程中运行推理循环
    - 发射帧数据和统计信号到 UI
    - 支持实时更新置信度/IOU 参数

架构要点:
    - 使用 QThread 避免阻塞主线程
    - 通过 Signal 与 UI 通信
    - 支持多种输入源 (图片/视频/摄像头/屏幕)
"""

from __future__ import annotations

from collections import OrderedDict

import time
from enum import Enum
from pathlib import Path
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

from PySide6.QtCore import QObject, QThread, Signal, Slot

from utils.logger import get_logger


class InputSourceType(Enum):
    """输入源类型"""
    IMAGE = "image"
    VIDEO = "video"
    CAMERA = "camera"
    SCREEN = "screen"
    RTSP = "rtsp"


class PlaybackState(Enum):
    """播放状态"""
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    SEEKING = "seeking"


class SaveCondition(Enum):
    """图片保存条件"""
    ALL = "all"                    # 保存所有
    WITH_DETECTIONS = "with"       # 只保存有检测结果
    WITHOUT_DETECTIONS = "without" # 只保存无检测结果
    HIGH_CONFIDENCE = "high_conf"  # 只保存高置信度


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
        self._paused_before_seek: bool = False  # 标记 seek 前是否处于暂停状态
        
        # 视频信息
        self._total_frames: int = 0
        self._current_frame: int = 0
        
        # 检测结果缓存 {frame_index: [detections]}
        # 用于 seek 回看时避免重复推理，使用 LRU 策略限制最大缓存帧数
        self._detection_cache: OrderedDict[int, list] = OrderedDict()
        self._max_cache_frames: int = 1000  # 最大缓存 1000 帧
        
        # 屏幕截图区域 (用于屏幕录制)
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
        """
        设置输入源
        
        Args:
            source: 文件路径、摄像头 ID 或 RTSP 地址
            source_type: 输入源类型
            screen_region: 屏幕区域 (仅用于屏幕录制)
        """
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
        # 如果处于暂停状态，恢复以便线程能够退出
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
        """
        请求跳转到指定帧（仅视频文件有效）
        
        Args:
            frame_index: 目标帧索引
        """
        if self._source_type != InputSourceType.VIDEO:
            return
        
        # 记录 seek 前是否处于暂停状态
        was_paused = self._playback_state == PlaybackState.PAUSED
        self._logger.debug(f"Seek 请求: 帧 {frame_index}, 暂停状态: {was_paused}")
        
        with self._seek_lock:
            self._seek_requested = frame_index
            self._paused_before_seek = was_paused
        
        # 如果暂停中，临时恢复以处理 seek
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
        
        # 清空检测缓存
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
        
        # 获取视频信息（仅视频文件有效）
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
        fps_update_interval = 0.5  # 每 0.5 秒更新一次 FPS
        last_fps_time = start_time
        fps_frame_count = 0
        current_fps = 0.0
        
        # 进度更新节流（每 5 帧或 100ms 更新一次）
        last_progress_time = start_time
        progress_update_interval = 0.1
        
        # 设置播放状态
        self._playback_state = PlaybackState.PLAYING
        self.state_changed.emit(PlaybackState.PLAYING.value)
        
        try:
            while not self._stop_requested:
                # 检查暂停（使用 Event.wait 阻塞）
                if not self._pause_event.wait(timeout=0.1):
                    # 暂停中，但仍需检查 stop 和 seek
                    if self._stop_requested:
                        break
                    # 检查 seek 请求
                    with self._seek_lock:
                        if self._seek_requested is not None:
                            target = self._seek_requested
                            self._seek_requested = None
                        else:
                            continue
                    # 执行 seek
                    if is_video_file and target is not None:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                        self._current_frame = target
                        # seek 后读取一帧显示
                        ret, frame = cap.read()
                        if ret:
                            # 检查缓存
                            if target in self._detection_cache:
                                # 缓存命中：从缓存绘制（跳过推理）
                                detections = self._detection_cache[target]
                                annotated_frame = self._draw_cached_detections(frame, detections)
                                self._logger.debug(f"缓存命中: 帧 {target}")
                            else:
                                # 缓存未命中：正常推理并存入缓存
                                with self._params_lock:
                                    conf, iou = self._conf, self._iou
                                annotated_frame, detections = self._run_inference(frame, conf, iou)
                                self._detection_cache[target] = detections
                            self.frame_ready.emit(annotated_frame, frame, detections)
                            self.progress_updated.emit(self._current_frame, self._total_frames)
                        # 保持暂停状态，并重新发射 PAUSED 信号确保 UI 同步
                        self._pause_event.clear()
                        self.state_changed.emit(PlaybackState.PAUSED.value)
                    continue
                
                # 检查 seek 请求（播放状态下）
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
                            # 如果 seek 前是暂停状态，seek 后需要恢复暂停
                            if was_paused:
                                ret, frame = cap.read()
                                if ret:
                                    # 执行推理并显示帧
                                    with self._params_lock:
                                        conf, iou = self._conf, self._iou
                                    annotated_frame, detections = self._run_inference(frame, conf, iou)
                                    self._detection_cache[self._current_frame] = detections
                                    self.frame_ready.emit(annotated_frame, frame, detections)
                                    self.progress_updated.emit(self._current_frame, self._total_frames)
                                # 恢复暂停状态
                                self._pause_event.clear()
                                self._playback_state = PlaybackState.PAUSED
                                self.state_changed.emit(PlaybackState.PAUSED.value)
                                self._logger.debug("Seek 完成，恢复暂停状态")
                                continue
                
                ret, frame = cap.read()
                if not ret:
                    # 视频结束
                    if is_video_file:
                        break
                    # 摄像头/RTSP 可能是暂时性错误，等待重试
                    time.sleep(0.1)
                    continue
                
                self._current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
                
                # 获取当前参数
                with self._params_lock:
                    conf, iou = self._conf, self._iou
                
                # 执行推理
                annotated_frame, detections = self._run_inference(frame, conf, iou)
                
                # 存入缓存（仅视频文件），使用 LRU 淘汰策略
                if is_video_file:
                    self._detection_cache[self._current_frame] = detections
                    # LRU 淘汰：超过最大缓存帧数时删除最旧的
                    while len(self._detection_cache) > self._max_cache_frames:
                        self._detection_cache.popitem(last=False)
                
                frame_count += 1
                fps_frame_count += 1
                
                # 计算 FPS
                current_time = time.time()
                if current_time - last_fps_time >= fps_update_interval:
                    current_fps = fps_frame_count / (current_time - last_fps_time)
                    last_fps_time = current_time
                    fps_frame_count = 0
                
                # 发射帧和统计信号
                self.frame_ready.emit(annotated_frame, frame, detections)
                self.stats_updated.emit({
                    "fps": round(current_fps, 1),
                    "frame_count": frame_count,
                    "object_count": len(detections),
                })
                
                # 发射进度信号（节流）
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
        
        # 设置播放状态
        self._playback_state = PlaybackState.PLAYING
        self.state_changed.emit(PlaybackState.PLAYING.value)
        
        try:
            with mss.mss() as sct:
                while not self._stop_requested:
                    # 检查暂停（使用 Event.wait 阻塞）
                    if not self._pause_event.wait(timeout=0.1):
                        # 暂停中，只需检查 stop
                        if self._stop_requested:
                            break
                        continue
                    
                    # 截取屏幕
                    screenshot = sct.grab(self._screen_region)
                    frame = np.array(screenshot)
                    
                    # BGRA -> BGR
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    
                    # 获取当前参数
                    with self._params_lock:
                        conf, iou = self._conf, self._iou
                    
                    # 执行推理
                    annotated_frame, detections = self._run_inference(frame, conf, iou)
                    
                    frame_count += 1
                    fps_frame_count += 1
                    
                    # 计算 FPS
                    current_time = time.time()
                    if current_time - last_fps_time >= fps_update_interval:
                        current_fps = fps_frame_count / (current_time - last_fps_time)
                        last_fps_time = current_time
                        fps_frame_count = 0
                    
                    # 发射信号
                    self.frame_ready.emit(annotated_frame, frame, detections)
                    self.stats_updated.emit({
                        "fps": round(current_fps, 1),
                        "frame_count": frame_count,
                        "object_count": len(detections),
                    })
                    
                    # 控制帧率，避免 CPU 过载
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
        """
        执行单帧推理
        
        Returns:
            (标注后的帧, 检测结果列表)
        """
        results = self._model(frame, conf=conf, iou=iou, verbose=False)
        
        # 获取标注后的帧
        annotated_frame = results[0].plot()
        
        # 解析检测结果
        detections = []
        boxes = results[0].boxes
        
        if boxes is not None and len(boxes) > 0:
            h, w = frame.shape[:2]
            
            for i in range(len(boxes)):
                # 获取边界框 (xyxy 格式)
                xyxy = boxes.xyxy[i].cpu().numpy()
                x1, y1, x2, y2 = xyxy
                
                # 转换为 YOLO 格式 (归一化的 xywh)
                x_center = (x1 + x2) / 2 / w
                y_center = (y1 + y2) / 2 / h
                box_w = (x2 - x1) / w
                box_h = (y2 - y1) / h
                
                # 获取类别和置信度
                class_id = int(boxes.cls[i].cpu().numpy())
                confidence = float(boxes.conf[i].cpu().numpy())
                
                # 获取类别名称 (如果模型有名称映射)
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
        """
        从缓存的检测结果绘制边界框（无需调用模型）
        
        Args:
            frame: 原始帧
            detections: 缓存的检测结果列表
            
        Returns:
            标注后的帧
        """
        annotated = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["xyxy"]]
            class_name = det["class_name"]
            confidence = det["confidence"]
            class_id = det["class_id"]
            
            # 使用与 YOLO 一致的颜色（基于类别 ID）
            color = self._get_class_color(class_id)
            
            # 绘制边界框
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            
            # 绘制标签背景
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
            
            # 绘制标签文字
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
        """获取类别对应的颜色（与 YOLO 风格一致）"""
        # 使用固定的颜色调色板
        colors = [
            (255, 56, 56), (255, 157, 151), (255, 112, 31), (255, 178, 29),
            (207, 210, 49), (72, 249, 10), (146, 204, 23), (61, 219, 134),
            (26, 147, 52), (0, 212, 187), (44, 153, 168), (0, 194, 255),
            (52, 69, 147), (100, 115, 255), (0, 24, 236), (132, 56, 255),
            (82, 0, 133), (203, 56, 255), (255, 149, 200), (255, 55, 199),
        ]
        return colors[class_id % len(colors)]


class PredictManager(QObject):
    """
    预测管理器
    
    封装 PredictWorker，提供简洁的 API。
    
    Signals:
        frame_ready(np.ndarray, list): 帧和检测结果
        stats_updated(dict): 统计数据
        error_occurred(str): 错误消息
        finished(): 推理结束
        model_loaded(bool): 模型加载结果
        state_changed(str): 播放状态变化
        progress_updated(int, int): (当前帧, 总帧数)
    """
    
    # 信号: (标注帧, 原始帧, 检测结果)
    frame_ready = Signal(np.ndarray, np.ndarray, list)
    stats_updated = Signal(dict)
    error_occurred = Signal(str)
    finished = Signal()
    model_loaded = Signal(bool)
    state_changed = Signal(str)
    progress_updated = Signal(int, int)
    
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        
        self._model: Any = None
        self._model_path: Optional[str] = None
        self._source_type: Optional[InputSourceType] = None
        
        self._worker: Optional[PredictWorker] = None
        self._thread: Optional[QThread] = None
        
        self._logger = get_logger()
    
    @property
    def is_running(self) -> bool:
        """推理是否正在运行"""
        return self._thread is not None and self._thread.isRunning()
    
    @property
    def is_model_loaded(self) -> bool:
        """模型是否已加载"""
        return self._model is not None
    
    @property
    def is_paused(self) -> bool:
        """当前是否暂停"""
        return self._worker is not None and self._worker.is_paused
    
    @property
    def is_seekable(self) -> bool:
        """当前源是否支持跳转"""
        return self._source_type == InputSourceType.VIDEO
    
    @property
    def total_frames(self) -> int:
        """视频总帧数"""
        return self._worker.total_frames if self._worker else 0
    
    @property
    def current_frame(self) -> int:
        """当前帧索引"""
        return self._worker.current_frame if self._worker else 0
    
    def load_model(self, model_path: str) -> bool:
        """
        加载 YOLO 模型
        
        Args:
            model_path: 模型文件路径 (.pt)
            
        Returns:
            是否成功加载
        """
        try:
            from ultralytics import YOLO
            
            self._model = YOLO(model_path)
            self._model_path = model_path
            
            self._logger.info(f"模型加载成功: {model_path}")
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"模型加载失败: {e}")
            self._logger.error(f"模型加载失败: {e}")
            return False
    
    def start(
        self,
        source: str | int,
        source_type: InputSourceType,
        conf: float = 0.5,
        iou: float = 0.45,
        screen_region: Optional[dict] = None
    ) -> bool:
        """
        启动预测
        
        Args:
            source: 输入源 (文件路径/摄像头ID/RTSP地址)
            source_type: 输入源类型
            conf: 置信度阈值
            iou: IOU 阈值
            screen_region: 屏幕区域 (屏幕录制时使用)
            
        Returns:
            是否成功启动
        """
        if self._model is None:
            self.error_occurred.emit("请先加载模型")
            return False
        
        if self.is_running:
            self.error_occurred.emit("预测正在运行中")
            return False
        
        self._source_type = source_type
        
        # 创建 Worker 和线程
        self._worker = PredictWorker()
        self._worker.set_model(self._model)
        self._worker.set_source(source, source_type, screen_region)
        self._worker.update_params(conf, iou)
        
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        
        # 连接信号
        self._thread.started.connect(self._worker.run)
        self._worker.frame_ready.connect(self.frame_ready.emit)
        self._worker.stats_updated.connect(self.stats_updated.emit)
        self._worker.error_occurred.connect(self.error_occurred.emit)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.state_changed.connect(self.state_changed.emit)
        self._worker.progress_updated.connect(self.progress_updated.emit)
        
        # 启动线程
        self._thread.start()
        
        self._logger.info(f"预测启动: {source} ({source_type.value})")
        return True
    
    def stop(self) -> None:
        """停止预测"""
        if self._worker is not None:
            self._worker.stop()
    
    def pause(self) -> None:
        """暂停预测"""
        if self._worker is not None:
            self._worker.pause()
    
    def resume(self) -> None:
        """恢复预测"""
        if self._worker is not None:
            self._worker.resume()
    
    def seek(self, frame_index: int) -> None:
        """
        跳转到指定帧（仅视频文件有效）
        
        Args:
            frame_index: 目标帧索引
        """
        if self._worker is not None and self.is_seekable:
            self._worker.seek(frame_index)
    
    def update_params(self, conf: float, iou: float) -> None:
        """实时更新参数"""
        if self._worker is not None:
            self._worker.update_params(conf, iou)
    
    def _on_worker_finished(self) -> None:
        """Worker 结束时清理"""
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread.deleteLater()
            self._thread = None
        
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        
        self._source_type = None
        self.finished.emit()
        self._logger.info("预测结束")


class ImageBatchProcessor(QObject):
    """
    图片批量处理器
    
    专门用于图片模式的推理处理，支持：
    - 批量处理多张图片
    - 按条件保存结果
    - 翻页浏览已处理的图片
    
    Signals:
        progress_updated(int, int): (当前索引, 总数)
        image_processed(str, list): (图片路径, 检测结果)
        batch_finished(): 批量处理完成
        error_occurred(str): 错误消息
        current_changed(int, int): (当前索引, 已处理总数)
    """
    
    progress_updated = Signal(int, int)
    image_processed = Signal(str, list)
    batch_finished = Signal()
    error_occurred = Signal(str)
    current_changed = Signal(int, int)
    
    # 支持的图片格式
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}
    
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        
        self._model: Any = None
        self._conf: float = 0.5
        self._iou: float = 0.45
        self._high_conf_threshold: float = 0.7
        
        # 图片列表
        self._image_list: list[Path] = []
        
        # 已处理的图片列表 (按顺序保存)
        self._processed_list: list[Path] = []
        
        # 检测结果缓存 {image_path: detections}
        self._results_cache: dict[Path, list[dict]] = {}
        
        # 当前浏览索引 (在 _processed_list 中的索引)
        self._current_index: int = -1
        
        # 停止和暂停标志
        self._stop_requested: bool = False
        self._pause_requested: bool = False
        self._is_paused: bool = False
        
        # 保存条件
        self._save_condition: SaveCondition = SaveCondition.ALL
        
        self._logger = get_logger()
    
    def set_model(self, model: Any) -> None:
        """设置 YOLO 模型实例"""
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
    
    def load_images(self, source: str | Path | list[str] | list[Path]) -> int:
        """
        加载图片列表
        
        Args:
            source: 文件夹路径、单个图片路径、或图片路径列表
            
        Returns:
            加载的图片数量
        """
        self._image_list.clear()
        self._processed_list.clear()
        self._results_cache.clear()
        self._current_index = -1
        
        if isinstance(source, (str, Path)):
            source_path = Path(source)
            if source_path.is_dir():
                # 文件夹: 扫描所有支持的图片
                for ext in self.IMAGE_EXTENSIONS:
                    self._image_list.extend(source_path.glob(f"*{ext}"))
                # 去重（Windows 不区分大小写可能匹配到相同文件）并排序
                seen = set()
                unique_list = []
                for p in self._image_list:
                    key = p.resolve()
                    if key not in seen:
                        seen.add(key)
                        unique_list.append(p)
                unique_list.sort(key=lambda p: p.name.lower())
                self._image_list = unique_list
            elif source_path.is_file() and source_path.suffix.lower() in self.IMAGE_EXTENSIONS:
                # 单个图片文件
                self._image_list.append(source_path)
        elif isinstance(source, list):
            # 图片路径列表
            for p in source:
                path = Path(p)
                if path.is_file() and path.suffix.lower() in self.IMAGE_EXTENSIONS:
                    self._image_list.append(path)
        
        self._logger.info(f"图片加载完成: {len(self._image_list)} 张")
        return len(self._image_list)
    
    @property
    def image_count(self) -> int:
        """图片总数"""
        return len(self._image_list)
    
    @property
    def processed_count(self) -> int:
        """已处理数量"""
        return len(self._processed_list)
    
    @property
    def current_index(self) -> int:
        """当前浏览索引 (在 processed_list 中)"""
        return self._current_index
    
    @property
    def is_single_image(self) -> bool:
        """是否为单张图片模式"""
        return len(self._image_list) == 1
    
    def should_save(self, detections: list[dict]) -> bool:
        """
        根据保存条件判断是否保存该图片
        
        Args:
            detections: 检测结果列表
            
        Returns:
            是否应该保存
        """
        if self._save_condition == SaveCondition.ALL:
            return True
        elif self._save_condition == SaveCondition.WITH_DETECTIONS:
            return len(detections) > 0
        elif self._save_condition == SaveCondition.WITHOUT_DETECTIONS:
            return len(detections) == 0
        elif self._save_condition == SaveCondition.HIGH_CONFIDENCE:
            return any(d.get("confidence", 0) >= self._high_conf_threshold for d in detections)
        return False
    
    def process_single(self, index: int = 0) -> tuple[np.ndarray, np.ndarray, list[dict]] | None:
        """
        处理单张图片
        
        Args:
            index: 图片在 image_list 中的索引
            
        Returns:
            (原图, 标注图, 检测结果) 或 None
        """
        if self._model is None:
            self.error_occurred.emit("模型未加载")
            return None
        
        if index < 0 or index >= len(self._image_list):
            self.error_occurred.emit(f"索引越界: {index}")
            return None
        
        image_path = self._image_list[index]
        
        # 读取图片
        original = cv2.imread(str(image_path))
        if original is None:
            self.error_occurred.emit(f"无法读取图片: {image_path}")
            return None
        
        # 执行推理
        annotated, detections = self._run_inference(original)
        
        # 缓存结果
        self._results_cache[image_path] = detections
        
        # 添加到已处理列表 (如果未添加)
        if image_path not in self._processed_list:
            self._processed_list.append(image_path)
            self._current_index = len(self._processed_list) - 1
        
        self.image_processed.emit(str(image_path), detections)
        self.current_changed.emit(self._current_index, len(self._processed_list))
        
        return original, annotated, detections
    
    def process_all(self, save_condition: SaveCondition = SaveCondition.ALL) -> None:
        """
        批量处理所有图片
        
        Args:
            save_condition: 保存条件
        """
        if self._model is None:
            self.error_occurred.emit("模型未加载")
            return
        
        self._save_condition = save_condition
        self._stop_requested = False
        self._processed_list.clear()
        self._results_cache.clear()
        self._current_index = -1
        
        total = len(self._image_list)
        
        for i, image_path in enumerate(self._image_list):
            if self._stop_requested:
                self._logger.info("批量处理被用户中止")
                break
            
            # 暂停检查
            while self._pause_requested:
                self._is_paused = True
                import time
                time.sleep(0.1)
                if self._stop_requested:
                    break
            self._is_paused = False
            
            # 读取图片
            original = cv2.imread(str(image_path))
            if original is None:
                self._logger.warning(f"无法读取图片: {image_path}")
                continue
            
            # 执行推理
            annotated, detections = self._run_inference(original)
            
            # 缓存结果
            self._results_cache[image_path] = detections
            
            # 根据条件决定是否添加到已处理列表
            if self.should_save(detections):
                self._processed_list.append(image_path)
            
            # 发射进度信号
            self.progress_updated.emit(i + 1, total)
            self.image_processed.emit(str(image_path), detections)
        
        # 设置当前索引为第一张
        if self._processed_list:
            self._current_index = 0
            self.current_changed.emit(0, len(self._processed_list))
        
        self.batch_finished.emit()
        self._logger.info(f"批量处理完成: {len(self._processed_list)} / {total} 张已保存")
    
    def stop(self) -> None:
        """停止批量处理"""
        self._stop_requested = True
        self._pause_requested = False  # 确保不会卡在暂停循环
    
    def pause(self) -> None:
        """暂停批量处理"""
        self._pause_requested = True
    
    def resume(self) -> None:
        """继续批量处理"""
        self._pause_requested = False
    
    @property
    def is_paused(self) -> bool:
        """是否处于暂停状态"""
        return self._is_paused
    
    def get_result(
        self, 
        index: int
    ) -> tuple[np.ndarray, np.ndarray, list[dict]] | None:
        """
        获取已处理图片的结果 (用于翻页浏览)
        
        Args:
            index: 在 processed_list 中的索引
            
        Returns:
            (原图, 标注图, 检测结果) 或 None
        """
        if index < 0 or index >= len(self._processed_list):
            return None
        
        image_path = self._processed_list[index]
        
        # 重新读取图片
        original = cv2.imread(str(image_path))
        if original is None:
            return None
        
        # 从缓存获取检测结果
        detections = self._results_cache.get(image_path, [])
        
        # 重新绘制标注
        annotated = self._draw_detections(original, detections)
        
        self._current_index = index
        self.current_changed.emit(index, len(self._processed_list))
        
        return original, annotated, detections
    
    def next(self) -> int:
        """
        翻到下一张
        
        Returns:
            新的索引，-1 表示无法翻页
        """
        if self._current_index < len(self._processed_list) - 1:
            self._current_index += 1
            self.current_changed.emit(self._current_index, len(self._processed_list))
            return self._current_index
        return -1
    
    def prev(self) -> int:
        """
        翻到上一张
        
        Returns:
            新的索引，-1 表示无法翻页
        """
        if self._current_index > 0:
            self._current_index -= 1
            self.current_changed.emit(self._current_index, len(self._processed_list))
            return self._current_index
        return -1
    
    def get_current_image_path(self) -> Path | None:
        """获取当前图片路径"""
        if 0 <= self._current_index < len(self._processed_list):
            return self._processed_list[self._current_index]
        return None
    
    def get_image_list(self) -> list[Path]:
        """获取图片列表"""
        return self._image_list.copy()
    
    def get_processed_list(self) -> list[Path]:
        """获取已处理图片列表"""
        return self._processed_list.copy()
    
    def get_detected_list(self) -> list[Path]:
        """获取有检测结果的图片列表"""
        return [p for p in self._processed_list if self._results_cache.get(p)]
    
    def get_empty_list(self) -> list[Path]:
        """获取无检测结果的图片列表"""
        return [p for p in self._image_list if not self._results_cache.get(p, None) or len(self._results_cache.get(p, [])) == 0]
    
    def _run_inference(self, frame: np.ndarray) -> tuple[np.ndarray, list[dict]]:
        """执行单帧推理"""
        results = self._model(frame, conf=self._conf, iou=self._iou, verbose=False)
        
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
                    "xyxy": [float(x1), float(y1), float(x2), float(y2)],
                })
        
        return annotated_frame, detections
    
    def _draw_detections(
        self, 
        frame: np.ndarray, 
        detections: list[dict]
    ) -> np.ndarray:
        """绘制检测结果"""
        annotated = frame.copy()
        
        colors = [
            (255, 56, 56), (255, 157, 151), (255, 112, 31), (255, 178, 29),
            (207, 210, 49), (72, 249, 10), (146, 204, 23), (61, 219, 134),
            (26, 147, 52), (0, 212, 187), (44, 153, 168), (0, 194, 255),
            (52, 69, 147), (100, 115, 255), (0, 24, 236), (132, 56, 255),
            (82, 0, 133), (203, 56, 255), (255, 149, 200), (255, 55, 199),
        ]
        
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det["xyxy"]]
            class_name = det["class_name"]
            confidence = det["confidence"]
            class_id = det["class_id"]
            
            color = colors[class_id % len(colors)]
            
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


class VideoBatchProcessor(QObject):
    """
    视频批量处理器
    
    专门用于批量处理多个视频文件，支持：
    - 批量加载视频文件夹或多选视频
    - 逐个处理每个视频
    - 每个视频独立输出目录
    - 生成汇总报告
    
    Signals:
        video_started(str, int, int): (视频路径, 当前索引, 总数) 开始处理一个视频
        video_finished(str, dict): (视频路径, 统计数据) 单个视频处理完成
        frame_progress(int, int): (当前帧, 总帧数) 当前视频的帧进度
        batch_progress(int, int): (已完成视频数, 总视频数) 整体进度
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
        """
        加载视频列表
        
        Args:
            source: 文件夹路径、单个视频路径、或视频路径列表
            
        Returns:
            加载的视频数量
        """
        self._video_list.clear()
        self._video_stats.clear()
        self._current_index = -1
        
        if isinstance(source, (str, Path)):
            source_path = Path(source)
            if source_path.is_dir():
                # 文件夹: 扫描所有支持的视频
                for ext in self.VIDEO_EXTENSIONS:
                    self._video_list.extend(source_path.glob(f"*{ext}"))
                # 去重（Windows 不区分大小写可能匹配到相同文件）并排序
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
                # 单个视频文件
                self._video_list.append(source_path)
        elif isinstance(source, list):
            # 视频路径列表
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
        """
        批量处理所有视频
        
        注意：此方法应在 QThread 中调用，避免阻塞 UI
        """
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
            
            # 处理单个视频
            stats = self._process_single_video(video_path)
            
            if stats:
                self._video_stats[video_path] = stats
                self.video_finished.emit(str(video_path), stats)
            
            # 发射整体进度
            self.batch_progress.emit(i + 1, total)
        
        self._is_running = False
        self.batch_finished.emit()
        self._logger.info(f"批量处理完成: {len(self._video_stats)}/{total} 个视频")
    
    def _process_single_video(self, video_path: Path) -> dict | None:
        """
        处理单个视频
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            统计数据字典，失败返回 None
        """
        cap = cv2.VideoCapture(str(video_path))
        
        if not cap.isOpened():
            self.error_occurred.emit(f"无法打开视频: {video_path}")
            return None
        
        # 获取视频信息
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
        
        if self._output_dir:
            video_output_dir = self._output_dir / video_path.stem
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
                raw_labels_dir = video_output_dir / "keyframes" / "raw" / "labels"
                raw_keyframe_dir.mkdir(parents=True, exist_ok=True)
                raw_labels_dir.mkdir(parents=True, exist_ok=True)
        
        # 统计数据
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
                # 检查暂停
                while self._pause_requested:
                    self._is_paused = True
                    time.sleep(0.1)
                    if self._stop_requested:
                        break
                self._is_paused = False
                
                ret, frame = cap.read()
                if not ret:
                    break
                
                # 执行推理
                results = self._model(frame, conf=self._conf, iou=self._iou, verbose=False)
                annotated_frame = results[0].plot()
                
                # 解析检测结果
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
                
                # 保存结果视频帧
                if video_writer:
                    video_writer.write(annotated_frame)
                
                # 保存关键帧
                if (keyframe_dir or raw_keyframe_dir) and detections:
                    should_save = True
                    if self._high_conf_only:
                        should_save = any(
                            d["confidence"] >= self._high_conf_threshold 
                            for d in detections
                        )
                    
                    if should_save:
                        # 保存带框关键帧
                        if keyframe_dir:
                            keyframe_path = keyframe_dir / f"frame_{frame_idx:06d}.jpg"
                            cv2.imwrite(str(keyframe_path), annotated_frame)
                        
                        # 保存原图关键帧 + YOLO 标签
                        if raw_keyframe_dir:
                            raw_path = raw_keyframe_dir / f"frame_{frame_idx:06d}.jpg"
                            cv2.imwrite(str(raw_path), frame)
                            
                            # 保存 YOLO TXT 标签
                            h_frame, w_frame = frame.shape[:2]
                            label_path = raw_labels_dir / f"frame_{frame_idx:06d}.txt"
                            with open(label_path, "w", encoding="utf-8") as f:
                                for d in detections:
                                    cid = d["class_id"]
                                    x1, y1, x2, y2 = d["xyxy"]
                                    xc = (x1 + x2) / 2 / w_frame
                                    yc = (y1 + y2) / 2 / h_frame
                                    bw = (x2 - x1) / w_frame
                                    bh = (y2 - y1) / h_frame
                                    f.write(f"{cid} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")
                        
                        keyframe_count += 1
                
                frame_idx += 1
                stats["processed_frames/已处理帧数"] = frame_idx
                
                # 发射帧进度（每 10 帧更新一次，减少信号开销）
                if frame_idx % 10 == 0 or frame_idx == total_frames:
                    self.frame_progress.emit(frame_idx, total_frames)
                    
        finally:
            cap.release()
            if video_writer:
                video_writer.release()
        
        stats["keyframes_saved/已保存关键帧"] = keyframe_count
        
        # 保存单视频报告
        if self._save_report and video_output_dir:
            import json
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
    
    def generate_batch_report(self) -> Path | None:
        """
        生成批量处理汇总报告
        
        Returns:
            报告文件路径，失败返回 None
        """
        if not self._output_dir or not self._video_stats:
            return None
        
        import json
        from datetime import datetime
        
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

