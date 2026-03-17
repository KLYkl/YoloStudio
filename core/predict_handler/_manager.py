"""
_manager.py - PredictManager: 预测管理器
============================================
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from PySide6.QtCore import QObject, QThread, Signal

from core.predict_handler._models import InputSourceType
from core.predict_handler._worker import PredictWorker
from utils.logger import get_logger


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
    def model_path(self) -> str | None:
        """当前已加载的模型路径"""
        return self._model_path

    @property
    def model(self) -> Any:
        """当前已加载的模型实例"""
        return self._model

    @property
    def model_names(self) -> dict:
        """模型的类别名称映射 {class_id: name}"""
        if self._model is not None:
            return getattr(self._model, 'names', {})
        return {}

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
        """加载 YOLO 模型"""
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
        """启动预测"""
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

    def wait_for_stop(self, timeout_ms: int = 3000) -> bool:
        """等待推理线程退出（公开 API，避免外部访问 _thread）

        Returns:
            True 如果线程已退出，False 如果超时
        """
        if self._thread is not None and self._thread.isRunning():
            return self._thread.wait(timeout_ms)
        return True

    def pause(self) -> None:
        """暂停预测"""
        if self._worker is not None:
            self._worker.pause()

    def resume(self) -> None:
        """恢复预测"""
        if self._worker is not None:
            self._worker.resume()

    def seek(self, frame_index: int) -> None:
        """跳转到指定帧（仅视频文件有效）"""
        if self._worker is not None and self.is_seekable:
            self._worker.seek(frame_index)

    def update_params(self, conf: float, iou: float) -> None:
        """实时更新参数"""
        if self._worker is not None:
            self._worker.update_params(conf, iou)

    def _on_worker_finished(self) -> None:
        """Worker 结束时清理"""
        # 先保留引用，等 finished 信号处理完再清理
        thread = self._thread
        worker = self._worker

        self._source_type = None

        # 先发射 finished 信号，让接收者在引用还存在时处理
        self.finished.emit()
        self._logger.info("预测结束")

        # 再清理线程和 worker 引用
        if thread is not None:
            thread.quit()
            thread.wait()
            thread.deleteLater()
            self._thread = None

        if worker is not None:
            worker.deleteLater()
            self._worker = None
