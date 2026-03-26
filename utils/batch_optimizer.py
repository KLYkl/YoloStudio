"""
batch_optimizer.py - 自动 Batch Size 优化器
============================================
基于硬件信息自动计算最佳 batch size，支持两档性能模式。

策略:
    - 最优性能 (OPTIMAL): 安全稳定，留足显存余量
    - 高性能 (HIGH): 激进利用显存，GPU 占用更高
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from utils.hardware_info import HardwareInfo, get_hardware_info
from utils.logger import get_logger

_logger = get_logger()


class PerformanceMode(Enum):
    """性能模式"""
    OPTIMAL = "optimal"    # 最优性能: 安全稳定
    HIGH = "high"          # 高性能: 激进利用显存


@dataclass
class BatchConfig:
    """Batch 配置结果"""
    image_batch_size: int       # 图片批量推理的 batch size
    video_batch_size: int       # 视频批量推理的 batch size
    decoder_queue_size: int     # 视频解码队列大小
    mode: PerformanceMode       # 当前性能模式
    reason: str                 # 决策原因 (用于日志)


# ==================== 策略表 ====================
# (最小显存MB, 最大显存MB): (最优img, 最优vid, 高性能img, 高性能vid)
_BATCH_TABLE: list[tuple[int, int, int, int, int, int]] = [
    # min_mb, max_mb, opt_img, opt_vid, high_img, high_vid
    (0,      2048,   1,       1,       2,        1),
    (2048,   4096,   2,       2,       4,        2),
    (4096,   6144,   4,       4,       8,        4),
    (6144,   8192,   8,       4,       16,       8),
    (8192,   999999, 16,      8,       32,       16),
]


def compute_optimal_batch(
    hw: Optional[HardwareInfo] = None,
    mode: PerformanceMode = PerformanceMode.OPTIMAL,
) -> BatchConfig:
    """根据硬件信息和性能模式计算最佳 batch 配置

    Args:
        hw: 硬件信息，不传则自动检测
        mode: 性能模式

    Returns:
        BatchConfig 实例
    """
    if hw is None:
        hw = get_hardware_info()

    # 无 GPU 时固定 batch=1
    if not hw.gpu_available:
        config = BatchConfig(
            image_batch_size=1,
            video_batch_size=1,
            decoder_queue_size=4,
            mode=mode,
            reason="无 CUDA GPU，使用 CPU 推理，batch=1",
        )
        _logger.info(f"Batch 策略: {config.reason}")
        return config

    # 使用空闲显存作为决策依据
    free_mb = hw.gpu_vram_free_mb

    img_bs, vid_bs = 1, 1
    for min_mb, max_mb, opt_img, opt_vid, high_img, high_vid in _BATCH_TABLE:
        if min_mb <= free_mb < max_mb:
            if mode == PerformanceMode.OPTIMAL:
                img_bs, vid_bs = opt_img, opt_vid
            else:
                img_bs, vid_bs = high_img, high_vid
            break

    # 解码队列 = batch_size * 3，至少 4
    decoder_qs = max(4, vid_bs * 3)

    reason = (
        f"GPU {hw.gpu_name} | 空闲显存 {free_mb} MB | "
        f"模式={mode.value} → img_batch={img_bs}, vid_batch={vid_bs}"
    )

    config = BatchConfig(
        image_batch_size=img_bs,
        video_batch_size=vid_bs,
        decoder_queue_size=decoder_qs,
        mode=mode,
        reason=reason,
    )

    _logger.info(f"Batch 策略: {config.reason}")
    return config
