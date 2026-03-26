"""
batch_optimizer.py - 自动 Batch Size 优化器
============================================
基于硬件信息自动计算最佳 batch size，支持两档性能模式。

实测数据 (RTX 3050 4GB, YOLO 模型):
    batch=1  → 显存增量 ~0MB
    batch=4  → 显存增量 ~18MB
    batch=8  → 显存增量 ~52MB
    batch=16 → 显存增量 ~154MB

结论: YOLO 推理显存开销极低, 真正瓶颈是 CPU 解码速度。
策略以 CPU 核心数 + 显存余量双因素决策。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from utils.hardware_info import HardwareInfo, get_hardware_info
from utils.logger import get_logger

_logger = get_logger()

# 安全显存余量 (MB): 推理期间至少保留这么多空闲显存
_VRAM_RESERVE_OPTIMAL_MB = 800   # 最优模式: 留 800MB 余量
_VRAM_RESERVE_HIGH_MB = 400      # 高性能模式: 留 400MB 余量

# 每帧推理的显存增量 (MB) — 中间激活层/特征图的显存开销
# 实测数据 (640x640 输入):
#   nano  模型: ~12 MB/帧
#   small 模型: ~30 MB/帧 (估)
#   medium模型: ~60 MB/帧 (估)
#   large 模型: ~100 MB/帧 (估)
# 取 80 MB 作为保守通用值，确保对多数模型安全
# 注: 空闲显存已在模型加载后测量，模型权重已扣除
_VRAM_PER_FRAME_MB = 80


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
    decode_mode: str            # 解码模式: "cpu" / "multi" / "nvdec"
    decode_workers: int         # 多线程解码 worker 数 (仅 multi 模式)
    mode: PerformanceMode       # 当前性能模式
    reason: str                 # 决策原因 (用于日志)


def _clamp(value: int, lo: int, hi: int) -> int:
    """限制值在 [lo, hi] 范围内"""
    return max(lo, min(hi, value))


def _calc_max_batch_by_vram(free_mb: int, reserve_mb: int) -> int:
    """基于空闲显存计算最大安全 batch size

    Args:
        free_mb: 当前空闲显存 (MB)
        reserve_mb: 需要保留的安全余量 (MB)

    Returns:
        最大安全 batch size (>= 1)
    """
    usable_mb = free_mb - reserve_mb
    if usable_mb <= 0:
        return 1
    # 每帧约 12MB 增量 (实测保守值)
    max_bs = int(usable_mb / _VRAM_PER_FRAME_MB)
    return max(1, max_bs)


def _calc_batch_by_cpu(cpu_threads: int, mode: PerformanceMode) -> tuple[int, int]:
    """基于 CPU 线程数推荐 batch size

    CPU 解码速度是真正瓶颈，batch 太大反而 GPU 空等。

    Args:
        cpu_threads: CPU 逻辑线程数
        mode: 性能模式

    Returns:
        (推荐 img_batch, 推荐 vid_batch)
    """
    if mode == PerformanceMode.OPTIMAL:
        # 最优模式: 保守, 留 CPU 余量给系统和 UI
        vid_bs = max(1, cpu_threads // 4)
        img_bs = max(1, cpu_threads // 2)
    else:
        # 高性能模式: 激进, 充分利用 CPU
        vid_bs = max(2, cpu_threads // 2)
        img_bs = max(2, cpu_threads)
    return img_bs, vid_bs


def compute_optimal_batch(
    hw: Optional[HardwareInfo] = None,
    mode: PerformanceMode = PerformanceMode.OPTIMAL,
) -> BatchConfig:
    """根据硬件信息和性能模式计算最佳 batch 配置

    决策逻辑:
        1. 基于 CPU 线程数推荐初始 batch size (解码瓶颈)
        2. 基于 GPU 空闲显存计算上限 (安全约束)
        3. 取 min(CPU推荐, GPU上限) 作为最终值
        4. 限制在合理范围内 (vid: 1~16, img: 1~32)

    Args:
        hw: 硬件信息，不传则自动检测
        mode: 性能模式

    Returns:
        BatchConfig 实例
    """
    if hw is None:
        hw = get_hardware_info()

    # 无 GPU 时固定 batch=1, 多线程 CPU 解码
    if not hw.gpu_available:
        config = BatchConfig(
            image_batch_size=1,
            video_batch_size=1,
            decoder_queue_size=4,
            decode_mode="multi",
            decode_workers=max(1, hw.cpu_threads // 4),
            mode=mode,
            reason="无 CUDA GPU，使用 CPU 推理，batch=1",
        )
        _logger.info(f"Batch 策略: {config.reason}")
        return config

    # Step 1: CPU 推荐值
    cpu_img_bs, cpu_vid_bs = _calc_batch_by_cpu(hw.cpu_threads, mode)

    # Step 2: GPU 显存上限
    reserve = _VRAM_RESERVE_OPTIMAL_MB if mode == PerformanceMode.OPTIMAL else _VRAM_RESERVE_HIGH_MB
    vram_max_bs = _calc_max_batch_by_vram(hw.gpu_vram_free_mb, reserve)

    # Step 3: 取较小值 (不超过 GPU 安全上限)
    img_bs = _clamp(min(cpu_img_bs, vram_max_bs), 1, 32)
    vid_bs = _clamp(min(cpu_vid_bs, vram_max_bs), 1, 16)

    # 解码队列 = batch_size * 3，至少 4
    decoder_qs = max(4, vid_bs * 3)

    # Step 4: 解码模式决策
    # 最优模式 → 多线程 CPU 解码 (安全稳定)
    # 高性能模式 → NVDEC GPU 硬件解码 (如果可用, 否则降级到 multi)
    from core.predict_handler._frame_decoder import is_nvdec_available
    if mode == PerformanceMode.HIGH and is_nvdec_available():
        decode_mode = "nvdec"
        decode_workers = 1  # NVDEC 不需要多 worker
    else:
        decode_mode = "multi"
        decode_workers = max(1, hw.cpu_threads // 4)

    reason = (
        f"GPU {hw.gpu_name} | 空闲显存 {hw.gpu_vram_free_mb}MB | "
        f"CPU {hw.cpu_threads}线程 | "
        f"模式={mode.value} → img_batch={img_bs}, vid_batch={vid_bs}, "
        f"解码={decode_mode} "
        f"(CPU推荐: img={cpu_img_bs}/vid={cpu_vid_bs}, "
        f"显存上限: {vram_max_bs})"
    )

    config = BatchConfig(
        image_batch_size=img_bs,
        video_batch_size=vid_bs,
        decoder_queue_size=decoder_qs,
        decode_mode=decode_mode,
        decode_workers=decode_workers,
        mode=mode,
        reason=reason,
    )

    _logger.info(f"Batch 策略: {config.reason}")
    return config
