"""
_image_batch.py - ImageBatchProcessor: 图片批量处理器
============================================
"""

from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any, Optional

import cv2
import numpy as np

from PySide6.QtCore import QObject, Signal

from core.predict_handler._inference_utils import run_inference, draw_detections
from core.predict_handler._models import SaveCondition
from utils.constants import IMAGE_EXTENSIONS
from utils.file_utils import discover_files
from utils.logger import get_logger


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

        # 当前浏览索引
        self._current_index: int = -1

        # 停止和暂停标志 (线程安全)
        self._stop_requested: bool = False
        self._pause_event = Event()
        self._pause_event.set()  # 初始为 "运行" 状态

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
        """加载图片列表"""
        self._image_list.clear()
        self._processed_list.clear()
        self._results_cache.clear()
        self._current_index = -1

        self._image_list = discover_files(source, IMAGE_EXTENSIONS)

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
        """当前浏览索引"""
        return self._current_index

    @property
    def is_single_image(self) -> bool:
        """是否为单张图片模式"""
        return len(self._image_list) == 1

    def should_save(self, detections: list[dict]) -> bool:
        """根据保存条件判断是否保存该图片"""
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
        """处理单张图片"""
        if self._model is None:
            self.error_occurred.emit("模型未加载")
            return None

        if index < 0 or index >= len(self._image_list):
            self.error_occurred.emit(f"索引越界: {index}")
            return None

        image_path = self._image_list[index]

        original = cv2.imread(str(image_path))
        if original is None:
            self.error_occurred.emit(f"无法读取图片: {image_path}")
            return None

        annotated, detections = run_inference(self._model, original, self._conf, self._iou)

        self._results_cache[image_path] = detections

        if image_path not in self._processed_list:
            self._processed_list.append(image_path)
            self._current_index = len(self._processed_list) - 1

        self.image_processed.emit(str(image_path), detections)
        self.current_changed.emit(self._current_index, len(self._processed_list))

        return original, annotated, detections

    def process_all(self, save_condition: SaveCondition = SaveCondition.ALL) -> None:
        """批量处理所有图片"""
        if self._model is None:
            self.error_occurred.emit("模型未加载")
            return

        self._save_condition = save_condition
        self._stop_requested = False
        self._pause_event.set()
        self._processed_list.clear()
        self._results_cache.clear()
        self._current_index = -1

        total = len(self._image_list)

        for i, image_path in enumerate(self._image_list):
            if self._stop_requested:
                self._logger.info("批量处理被用户中止")
                break

            # 使用 Event 等待: 暂停时阻塞, 恢复时自动继续
            while not self._pause_event.wait(timeout=0.1):
                if self._stop_requested:
                    break

            if self._stop_requested:
                break

            original = cv2.imread(str(image_path))
            if original is None:
                self._logger.warning(f"无法读取图片: {image_path}")
                continue

            annotated, detections = run_inference(self._model, original, self._conf, self._iou)

            self._results_cache[image_path] = detections

            if self.should_save(detections):
                self._processed_list.append(image_path)

            self.progress_updated.emit(i + 1, total)
            self.image_processed.emit(str(image_path), detections)

        if self._processed_list:
            self._current_index = 0
            self.current_changed.emit(0, len(self._processed_list))

        self.batch_finished.emit()
        self._logger.info(f"批量处理完成: {len(self._processed_list)} / {total} 张已保存")

    def stop(self) -> None:
        """停止批量处理"""
        self._stop_requested = True
        self._pause_event.set()  # 唤醒暂停中的线程以退出

    def pause(self) -> None:
        """暂停批量处理"""
        self._pause_event.clear()

    def resume(self) -> None:
        """继续批量处理"""
        self._pause_event.set()

    @property
    def is_paused(self) -> bool:
        """是否处于暂停状态"""
        return not self._pause_event.is_set()

    def get_result(
        self,
        index: int
    ) -> tuple[np.ndarray, np.ndarray, list[dict]] | None:
        """获取已处理图片的结果 (用于翻页浏览)"""
        if index < 0 or index >= len(self._processed_list):
            return None

        image_path = self._processed_list[index]

        original = cv2.imread(str(image_path))
        if original is None:
            return None

        detections = self._results_cache.get(image_path, [])

        annotated = draw_detections(original, detections)

        self._current_index = index
        self.current_changed.emit(index, len(self._processed_list))

        return original, annotated, detections

    def next(self) -> int:
        """翻到下一张"""
        if self._current_index < len(self._processed_list) - 1:
            self._current_index += 1
            self.current_changed.emit(self._current_index, len(self._processed_list))
            return self._current_index
        return -1

    def prev(self) -> int:
        """翻到上一张"""
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

    def get_detections(self, image_path: Path) -> list[dict]:
        """获取指定图片的检测结果"""
        return self._results_cache.get(image_path, [])

    def get_detected_list(self) -> list[Path]:
        """获取有检测结果的图片列表"""
        return [p for p in self._processed_list if self._results_cache.get(p)]

    def get_empty_list(self) -> list[Path]:
        """获取无检测结果的图片列表"""
        return [p for p in self._image_list if not self._results_cache.get(p, None) or len(self._results_cache.get(p, [])) == 0]
