"""
hardware_info.py - 系统硬件信息检测
============================================
检测 CPU / RAM / GPU 硬件信息，供 batch_optimizer 决策使用。

依赖:
    - psutil (已在 requirements.txt)
    - torch  (已在 requirements.txt)
    - platform (标准库)
"""

from __future__ import annotations

import platform
from dataclasses import dataclass

import psutil

from utils.logger import get_logger

_logger = get_logger()


@dataclass
class HardwareInfo:
    """系统硬件信息快照"""

    # CPU
    cpu_name: str = "未知"
    cpu_cores: int = 1            # 物理核心数
    cpu_threads: int = 1          # 逻辑线程数

    # 内存
    ram_total_gb: float = 0.0     # 总内存 GB
    ram_available_gb: float = 0.0 # 可用内存 GB

    # GPU
    gpu_available: bool = False   # 是否有 CUDA GPU
    gpu_name: str = "无"
    gpu_vram_total_mb: int = 0    # 物理显存 MB
    gpu_vram_free_mb: int = 0     # 当前空闲显存 MB
    gpu_vram_used_mb: int = 0     # 当前已用显存 MB
    gpu_cuda_version: str = "N/A" # CUDA 版本

    def summary(self) -> str:
        """返回硬件信息的可读摘要 (用于日志)"""
        lines = [
            f"CPU: {self.cpu_name} ({self.cpu_cores}核/{self.cpu_threads}线程)",
            f"RAM: {self.ram_available_gb:.1f} GB 可用 / {self.ram_total_gb:.1f} GB 总计",
        ]
        if self.gpu_available:
            lines.append(
                f"GPU: {self.gpu_name} | "
                f"显存: {self.gpu_vram_free_mb} MB 空闲 / "
                f"{self.gpu_vram_total_mb} MB 总计 | "
                f"CUDA {self.gpu_cuda_version}"
            )
        else:
            lines.append("GPU: 无 CUDA GPU (将使用 CPU 推理)")
        return "\n".join(lines)


def _detect_cpu() -> tuple[str, int, int]:
    """检测 CPU 信息

    Returns:
        (cpu_name, physical_cores, logical_threads)
    """
    cpu_name = platform.processor() or "未知"

    # Windows 下 platform.processor() 可能返回不够友好的字符串
    # psutil 没有直接获取 CPU 品牌名的 API，尝试从注册表读取
    if platform.system() == "Windows":
        try:
            import winreg
            # R6-fix: 使用 with 语句保证异常时也能释放注册表句柄
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            ) as key:
                cpu_name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except Exception:
            pass

    cores = psutil.cpu_count(logical=False) or 1
    threads = psutil.cpu_count(logical=True) or 1

    return cpu_name, cores, threads


def _detect_ram() -> tuple[float, float]:
    """检测内存信息

    Returns:
        (total_gb, available_gb)
    """
    mem = psutil.virtual_memory()
    total_gb = mem.total / (1024 ** 3)
    available_gb = mem.available / (1024 ** 3)
    return total_gb, available_gb


def _detect_gpu() -> tuple[bool, str, int, int, int, str]:
    """检测 GPU 信息 (通过 torch.cuda)

    Returns:
        (available, gpu_name, vram_total_mb, vram_free_mb, vram_used_mb, cuda_version)
    """
    try:
        import torch

        if not torch.cuda.is_available():
            return False, "无", 0, 0, 0, "N/A"

        # 获取默认设备 (device 0) 信息
        props = torch.cuda.get_device_properties(0)
        gpu_name = props.name
        vram_total_mb = props.total_memory // (1024 * 1024)

        # 实时显存使用情况
        free_bytes, total_bytes = torch.cuda.mem_get_info(0)
        vram_free_mb = free_bytes // (1024 * 1024)
        vram_used_mb = vram_total_mb - vram_free_mb

        cuda_version = torch.version.cuda or "N/A"

        return True, gpu_name, vram_total_mb, vram_free_mb, vram_used_mb, cuda_version

    except ImportError:
        _logger.warning("torch 未安装，无法检测 GPU 信息")
        return False, "无", 0, 0, 0, "N/A"
    except Exception as e:
        _logger.warning(f"GPU 检测失败: {e}")
        return False, "无", 0, 0, 0, "N/A"


def get_hardware_info() -> HardwareInfo:
    """一次调用获取全部硬件信息

    Returns:
        HardwareInfo 数据类实例
    """
    cpu_name, cores, threads = _detect_cpu()
    ram_total, ram_available = _detect_ram()
    gpu_ok, gpu_name, vram_total, vram_free, vram_used, cuda_ver = _detect_gpu()

    info = HardwareInfo(
        cpu_name=cpu_name,
        cpu_cores=cores,
        cpu_threads=threads,
        ram_total_gb=ram_total,
        ram_available_gb=ram_available,
        gpu_available=gpu_ok,
        gpu_name=gpu_name,
        gpu_vram_total_mb=vram_total,
        gpu_vram_free_mb=vram_free,
        gpu_vram_used_mb=vram_used,
        gpu_cuda_version=cuda_ver,
    )

    _logger.info(f"硬件检测完成:\n{info.summary()}")
    return info
