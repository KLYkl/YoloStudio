"""
_models.py - 预测模块数据类型定义
============================================
"""

from enum import Enum


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
