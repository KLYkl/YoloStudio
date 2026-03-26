"""
_ffmpeg_writer.py - FFmpeg 视频写入器
============================================
使用 ffmpeg 子进程管道替代 cv2.VideoWriter,
支持 H.264 编码, 输出体积缩小 5~10 倍。

用法:
    writer = FFmpegVideoWriter("output.mp4", fps=30.0, size=(1920, 1080))
    writer.write(frame)  # numpy BGR 帧
    writer.release()
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np

from utils.logger import get_logger

_logger = get_logger()


def _find_ffmpeg() -> Optional[str]:
    """查找系统中的 ffmpeg 可执行文件"""
    path = shutil.which("ffmpeg")
    if path:
        return path
    # 尝试 imageio_ffmpeg (如果已安装)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    return None


class FFmpegVideoWriter:
    """基于 ffmpeg 子进程管道的视频写入器

    通过 stdin 管道发送原始帧数据, ffmpeg 进行 H.264 编码。
    相比 cv2.VideoWriter (mp4v):
    - 输出文件体积缩小 5~10 倍
    - 兼容性更好 (H.264 是通用标准)
    - 编码速度接近 (ultrafast preset)
    """

    def __init__(
        self,
        output_path: str,
        fps: float,
        size: tuple[int, int],
        preset: str = "fast",
        crf: int = 23,
    ) -> None:
        """
        Args:
            output_path: 输出视频文件路径
            fps: 帧率
            size: (宽, 高)
            preset: 编码速度预设 (ultrafast/fast/medium)
            crf: 质量参数 (0=无损, 23=默认, 28=较低质量)
        """
        self._output_path = output_path
        self._width, self._height = size
        self._proc: Optional[subprocess.Popen] = None
        self._closed = False

        ffmpeg_exe = _find_ffmpeg()
        if ffmpeg_exe is None:
            _logger.warning(
                "未找到 ffmpeg, 回退到 cv2.VideoWriter (mp4v 编码)"
            )
            self._fallback = True
            import cv2
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self._cv_writer = cv2.VideoWriter(
                output_path, fourcc, fps, size
            )
            return

        self._fallback = False

        cmd = [
            ffmpeg_exe,
            '-y',                           # 覆盖输出
            '-f', 'rawvideo',               # 输入格式: 原始帧
            '-vcodec', 'rawvideo',
            '-pix_fmt', 'bgr24',            # OpenCV BGR 格式
            '-s', f'{self._width}x{self._height}',
            '-r', str(fps),
            '-i', '-',                      # 从 stdin 读取
            '-c:v', 'libx264',              # H.264 编码
            '-preset', preset,
            '-crf', str(crf),
            '-pix_fmt', 'yuv420p',          # 兼容性最好的像素格式
            '-movflags', '+faststart',      # 支持流式播放
            output_path,
        ]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, FileNotFoundError) as e:
            _logger.warning(f"ffmpeg 启动失败: {e}, 回退到 cv2.VideoWriter")
            self._fallback = True
            import cv2
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self._cv_writer = cv2.VideoWriter(
                output_path, fourcc, fps, size
            )

    def isOpened(self) -> bool:
        """是否可用"""
        if self._closed:
            return False
        if self._fallback:
            return self._cv_writer.isOpened()
        return self._proc is not None and self._proc.poll() is None

    def write(self, frame: np.ndarray) -> None:
        """写入一帧 (BGR numpy 数组)"""
        if self._closed:
            return
        if self._fallback:
            self._cv_writer.write(frame)
            return
        if self._proc is None or self._proc.stdin is None:
            return
        try:
            self._proc.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError):
            _logger.warning("ffmpeg 管道已关闭")
            self._closed = True

    def release(self) -> None:
        """关闭写入器, 等待 ffmpeg 编码完成"""
        if self._closed:
            return
        self._closed = True

        if self._fallback:
            self._cv_writer.release()
            return

        if self._proc is not None:
            if self._proc.stdin is not None:
                try:
                    self._proc.stdin.close()
                except OSError:
                    pass
            # 等待 ffmpeg 处理完剩余数据
            try:
                self._proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                _logger.warning("ffmpeg 编码超时, 强制终止")
                self._proc.kill()
