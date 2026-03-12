"""
core.predict_handler - 预测核心模块
============================================

保持外部 API 不变:
    from core.predict_handler import (
        InputSourceType,
        PlaybackState,
        SaveCondition,
        PredictWorker,
        PredictManager,
        ImageBatchProcessor,
        VideoBatchProcessor,
    )
"""

from core.predict_handler._models import (
    InputSourceType,
    PlaybackState,
    SaveCondition,
)
from core.predict_handler._worker import PredictWorker
from core.predict_handler._manager import PredictManager
from core.predict_handler._image_batch import ImageBatchProcessor
from core.predict_handler._video_batch import VideoBatchProcessor

__all__ = [
    "InputSourceType",
    "PlaybackState",
    "SaveCondition",
    "PredictWorker",
    "PredictManager",
    "ImageBatchProcessor",
    "VideoBatchProcessor",
]
