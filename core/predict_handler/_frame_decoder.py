"""
_frame_decoder.py - 异步视频帧解码器 + 向量化检测提取
====================================================
将视频解码与 GPU 推理流水线化:
- FrameDecoder: 单线程 CPU 解码 (基础模式)
- MultiThreadDecoder: 多线程 CPU 解码 (最优模式)
- NvdecDecoder: NVDEC GPU 硬件解码 (高性能模式)
- 向量化提取: 一次性 GPU→CPU 拷贝, 替代逐 box 循环
"""

from __future__ import annotations

import logging
import queue
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

_logger = logging.getLogger(__name__)


class FrameDecoder(threading.Thread):
    """异步视频帧解码线程 (单线程 CPU 解码)

    在后台持续读取视频帧到缓冲队列, 让 GPU 推理不用等 CPU 解码。

    用法:
        decoder = FrameDecoder(cap, queue_size=4)
        decoder.start()
        while True:
            ret, frame = decoder.read()
            if not ret:
                break
            # ... 推理 ...
        decoder.stop()
    """

    def __init__(
        self,
        cap: cv2.VideoCapture,
        queue_size: int = 4,
        pause_event: Optional[threading.Event] = None,
    ) -> None:
        super().__init__(daemon=True, name="FrameDecoder")
        self._cap = cap
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._stop_event = threading.Event()
        self._pause_event = pause_event  # 共享暂停事件
        self._sentinel_sent = False  # Bug4-fix: 防止重复发送哨兵

    def _send_sentinel(self) -> None:
        """发送结束哨兵（保证只发一次）"""
        if not self._sentinel_sent:
            self._sentinel_sent = True
            self._queue.put(None)

    def run(self) -> None:
        """持续解码视频帧到队列"""
        while not self._stop_event.is_set():
            # 暂停时等待恢复
            if self._pause_event is not None:
                while not self._pause_event.wait(timeout=0.1):
                    if self._stop_event.is_set():
                        self._send_sentinel()
                        return

            ret, frame = self._cap.read()
            if not ret:
                self._send_sentinel()  # 视频结束
                return

            # 放入队列, 队列满时阻塞等待消费
            while not self._stop_event.is_set():
                try:
                    self._queue.put(frame, timeout=0.5)
                    break
                except queue.Full:
                    continue

    def read(self, timeout: float = 2.0) -> tuple[bool, Optional[np.ndarray]]:
        """从缓冲队列读取下一帧

        Returns:
            (成功标志, 帧数据)。视频结束时返回 (False, None)
        """
        try:
            frame = self._queue.get(timeout=timeout)
            if frame is None:
                return False, None
            return True, frame
        except queue.Empty:
            return False, None

    def read_batch(
        self, batch_size: int, timeout: float = 2.0
    ) -> list[np.ndarray]:
        """从缓冲队列批量读取多帧

        尽量读满 batch_size 帧，视频结束时返回已读到的帧。

        Args:
            batch_size: 目标帧数
            timeout: 每帧的等待超时

        Returns:
            帧列表，长度 0 ~ batch_size。空列表表示视频结束。
        """
        frames: list[np.ndarray] = []
        for _ in range(batch_size):
            try:
                frame = self._queue.get(timeout=timeout)
                if frame is None:
                    # Bug3-fix: 放回哨兵供后续 read()/read_batch() 使用
                    self._queue.put(None)
                    break
                frames.append(frame)
            except queue.Empty:
                break
        return frames

    def stop(self) -> None:
        """停止解码线程并等待退出

        必须在 cap.release() 之前调用, 确保解码线程不再访问 cap。
        """
        self._stop_event.set()
        self.join(timeout=2)

    def clear_queue(self) -> None:
        """清空缓冲队列 (seek 后使用)"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break


class MultiThreadDecoder:
    """多线程 CPU 视频帧解码器 (最优模式)

    使用单个 cv2.VideoCapture + 加锁的多 worker 线程并行解码。
    cv2.VideoCapture.read() 在 C++ 层释放 GIL, 多线程可真正并行。
    但 read() 本身会移动帧指针, 必须加锁保证原子性。

    实际策略: 主读取线程持锁连续读帧, 多个 worker 线程并行做
    色彩空间转换等后处理 (如果需要)。对于标准 BGR 输出,
    主要收益来自更大的解码队列缓冲。

    接口与 FrameDecoder 完全一致 (read / read_batch / stop / is_alive)。
    """

    def __init__(
        self,
        cap: cv2.VideoCapture,
        num_workers: int = 2,
        queue_size: int = 12,
        pause_event: Optional[threading.Event] = None,
    ) -> None:
        self._cap = cap
        self._num_workers = max(1, num_workers)
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._stop_event = threading.Event()
        self._pause_event = pause_event
        self._read_lock = threading.Lock()  # 保护 cap.read() 原子性
        self._sentinel_sent = False
        self._threads: list[threading.Thread] = []
        self._finished_count = 0
        self._finished_lock = threading.Lock()

    def _send_sentinel(self) -> None:
        """发送结束哨兵（保证只发一次, 用 _finished_lock 防竞态）"""
        with self._finished_lock:
            if not self._sentinel_sent:
                self._sentinel_sent = True
                self._queue.put(None)

    def _worker_run(self) -> None:
        """Worker 线程: 持锁读帧, 放入共享队列"""
        while not self._stop_event.is_set():
            # 暂停时等待恢复
            if self._pause_event is not None:
                while not self._pause_event.wait(timeout=0.1):
                    if self._stop_event.is_set():
                        break
                if self._stop_event.is_set():
                    break

            # 持锁读帧 (cap.read 在 C++ 层释放 GIL, 但帧指针不能并发移动)
            with self._read_lock:
                if self._stop_event.is_set():
                    break
                ret, frame = self._cap.read()

            if not ret:
                # 视频结束, 通知其他 worker 也退出
                self._stop_event.set()
                break

            # 放入队列
            while not self._stop_event.is_set():
                try:
                    self._queue.put(frame, timeout=0.5)
                    break
                except queue.Full:
                    continue

        # 最后一个退出的 worker 发送哨兵
        with self._finished_lock:
            self._finished_count += 1
            if self._finished_count >= self._num_workers:
                # Issue1-fix: 在锁内发送哨兵, 避免竞态双发
                if not self._sentinel_sent:
                    self._sentinel_sent = True
                    self._queue.put(None)

    def start(self) -> None:
        """启动所有 worker 线程"""
        for i in range(self._num_workers):
            t = threading.Thread(
                target=self._worker_run,
                daemon=True,
                name=f"MultiDecoder-{i}",
            )
            t.start()
            self._threads.append(t)
        _logger.info(f"多线程解码器启动: {self._num_workers} workers")

    def read(self, timeout: float = 2.0) -> tuple[bool, Optional[np.ndarray]]:
        """从缓冲队列读取下一帧"""
        try:
            frame = self._queue.get(timeout=timeout)
            if frame is None:
                return False, None
            return True, frame
        except queue.Empty:
            return False, None

    def read_batch(
        self, batch_size: int, timeout: float = 2.0
    ) -> list[np.ndarray]:
        """从缓冲队列批量读取多帧"""
        frames: list[np.ndarray] = []
        for _ in range(batch_size):
            try:
                frame = self._queue.get(timeout=timeout)
                if frame is None:
                    self._queue.put(None)
                    break
                frames.append(frame)
            except queue.Empty:
                break
        return frames

    def stop(self) -> None:
        """停止所有 worker 并等待退出"""
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=2)

    def is_alive(self) -> bool:
        """是否还有 worker 在运行"""
        return any(t.is_alive() for t in self._threads)

    def clear_queue(self) -> None:
        """清空缓冲队列"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break


class NvdecDecoder:
    """NVDEC GPU 硬件解码器 (高性能模式)

    通过 subprocess 调用 ffmpeg 的 NVIDIA 硬件解码器 (h264_cuvid 等),
    将 raw BGR24 帧数据通过 pipe 传输到 Python。

    解码完全在 GPU 的专用视频解码器上执行, 不占用 CUDA 核心和 CPU。

    接口与 FrameDecoder 完全一致 (read / read_batch / stop / is_alive)。
    """

    def __init__(
        self,
        video_path: str | Path,
        width: int,
        height: int,
        queue_size: int = 12,
        pause_event: Optional[threading.Event] = None,
    ) -> None:
        self._video_path = str(video_path)
        self._width = width
        self._height = height
        self._frame_size = width * height * 3  # BGR24
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._stop_event = threading.Event()
        self._pause_event = pause_event
        self._sentinel_sent = False
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None

    def _detect_codec(self) -> str:
        """探测视频编码格式, 返回对应的 cuvid 解码器名

        Returns:
            ffmpeg 解码器名, 如 'h264_cuvid', 'hevc_cuvid' 等。
            不支持的编码返回空字符串 (降级到软件解码)。
        """
        # 通过 ffprobe 检测编码
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=codec_name",
                    "-of", "csv=p=0",
                    self._video_path,
                ],
                capture_output=True, text=True, timeout=5,
            )
            codec = result.stdout.strip().lower()
        except Exception:
            return ""

        # 映射到 cuvid 解码器
        cuvid_map = {
            "h264": "h264_cuvid",
            "hevc": "hevc_cuvid",
            "h265": "hevc_cuvid",
            "vp8": "vp8_cuvid",
            "vp9": "vp9_cuvid",
            "av1": "av1_cuvid",
            "mpeg1video": "mpeg1_cuvid",
            "mpeg2video": "mpeg2_cuvid",
            "mpeg4": "mpeg4_cuvid",
            "mjpeg": "mjpeg_cuvid",
            "vc1": "vc1_cuvid",
        }
        return cuvid_map.get(codec, "")

    def _send_sentinel(self) -> None:
        if not self._sentinel_sent:
            self._sentinel_sent = True
            self._queue.put(None)

    def _reader_run(self) -> None:
        """读取线程: 从 ffmpeg pipe 读取 raw frames 放入队列"""
        cuvid_decoder = self._detect_codec()

        # 构建 ffmpeg 命令
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
        if cuvid_decoder:
            cmd += ["-hwaccel", "cuda", "-c:v", cuvid_decoder]
            _logger.info(f"NVDEC 解码: {cuvid_decoder}")
        else:
            _logger.warning("视频编码不支持 NVDEC, 降级到 FFmpeg 软件解码")

        cmd += [
            "-i", self._video_path,
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-v", "error",
            "pipe:1",
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # Issue5-fix: 避免 stderr 管道满死锁
                bufsize=self._frame_size * 4,  # 缓冲 4 帧
            )
        except FileNotFoundError:
            _logger.error("ffmpeg 未找到, NVDEC 解码失败")
            self._send_sentinel()
            return

        try:
            while not self._stop_event.is_set():
                # 暂停时等待恢复
                if self._pause_event is not None:
                    while not self._pause_event.wait(timeout=0.1):
                        if self._stop_event.is_set():
                            break
                    if self._stop_event.is_set():
                        break

                # 从 pipe 读取一帧 raw data
                raw = self._process.stdout.read(self._frame_size)
                if len(raw) < self._frame_size:
                    break  # 视频结束或读取中断

                # 转换为 numpy 数组
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(
                    (self._height, self._width, 3)
                )
                # frombuffer 返回只读数组, 需要 copy 才能被后续 cv2 操作修改
                frame = frame.copy()

                # 放入队列
                while not self._stop_event.is_set():
                    try:
                        self._queue.put(frame, timeout=0.5)
                        break
                    except queue.Full:
                        continue
        finally:
            self._send_sentinel()
            # 清理 ffmpeg 进程
            if self._process:
                self._process.stdout.close()
                self._process.terminate()
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.kill()

    def start(self) -> None:
        """启动解码线程"""
        self._thread = threading.Thread(
            target=self._reader_run,
            daemon=True,
            name="NvdecDecoder",
        )
        self._thread.start()
        _logger.info(f"NVDEC 解码器启动: {self._video_path}")

    def read(self, timeout: float = 2.0) -> tuple[bool, Optional[np.ndarray]]:
        """从缓冲队列读取下一帧"""
        try:
            frame = self._queue.get(timeout=timeout)
            if frame is None:
                return False, None
            return True, frame
        except queue.Empty:
            return False, None

    def read_batch(
        self, batch_size: int, timeout: float = 2.0
    ) -> list[np.ndarray]:
        """从缓冲队列批量读取多帧"""
        frames: list[np.ndarray] = []
        for _ in range(batch_size):
            try:
                frame = self._queue.get(timeout=timeout)
                if frame is None:
                    self._queue.put(None)
                    break
                frames.append(frame)
            except queue.Empty:
                break
        return frames

    def stop(self) -> None:
        """停止解码并等待退出"""
        self._stop_event.set()
        # Bug3-fix: 显式终止 ffmpeg 子进程, 中断 stdout.read() 阻塞
        if self._process:
            if self._process.stdout:
                try:
                    self._process.stdout.close()
                except OSError:
                    pass
            self._process.terminate()
        if self._thread:
            self._thread.join(timeout=3)
        # 超时仍未退出则强杀
        if self._process and self._process.poll() is None:
            self._process.kill()
            _logger.warning("NVDEC ffmpeg 进程强制终止")

    def is_alive(self) -> bool:
        """解码线程是否在运行"""
        return self._thread is not None and self._thread.is_alive()

    def clear_queue(self) -> None:
        """清空缓冲队列"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break


def _is_nvdec_available() -> bool:
    """检测系统是否支持 NVDEC (ffmpeg 有 cuvid 解码器)"""
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return False
    try:
        result = subprocess.run(
            ["ffmpeg", "-decoders"],
            capture_output=True, text=True, timeout=5,
        )
        return "h264_cuvid" in result.stdout
    except Exception:
        return False


# 模块级缓存, 避免重复检测
_nvdec_available: Optional[bool] = None


def is_nvdec_available() -> bool:
    """检测 NVDEC 是否可用 (结果缓存)"""
    global _nvdec_available
    if _nvdec_available is None:
        _nvdec_available = _is_nvdec_available()
        _logger.info(f"NVDEC 可用: {_nvdec_available}")
    return _nvdec_available


def create_decoder(
    video_path: str | Path,
    cap: cv2.VideoCapture,
    mode: str = "cpu",
    num_workers: int = 2,
    queue_size: int = 8,
    pause_event: Optional[threading.Event] = None,
) -> FrameDecoder | MultiThreadDecoder | NvdecDecoder:
    """根据模式创建视频帧解码器 (工厂函数)

    Args:
        video_path: 视频文件路径 (NVDEC 模式需要)
        cap: 已打开的 cv2.VideoCapture (CPU 模式需要)
        mode: 解码模式
            - "cpu": 单线程 CPU 解码 (FrameDecoder)
            - "multi": 多线程 CPU 解码 (MultiThreadDecoder)
            - "nvdec": GPU 硬件解码 (NvdecDecoder, 不可用时降级到 multi)
        num_workers: 多线程模式的 worker 数量
        queue_size: 解码队列大小
        pause_event: 暂停事件

    Returns:
        解码器实例, 统一提供 read/read_batch/stop/is_alive 接口
    """
    if mode == "nvdec":
        if is_nvdec_available():
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return NvdecDecoder(
                video_path=video_path,
                width=width,
                height=height,
                queue_size=queue_size,
                pause_event=pause_event,
            )
        else:
            _logger.warning("NVDEC 不可用, 降级到多线程 CPU 解码")
            mode = "multi"

    if mode == "multi":
        return MultiThreadDecoder(
            cap=cap,
            num_workers=num_workers,
            queue_size=queue_size,
            pause_event=pause_event,
        )

    # 默认: 单线程 CPU 解码
    return FrameDecoder(
        cap=cap,
        queue_size=queue_size,
        pause_event=pause_event,
    )


def extract_detections_fast(
    boxes: Any,
    model_names: dict[int, str],
) -> list[dict]:
    """向量化检测数据提取

    一次性 GPU→CPU 拷贝, 替代逐 box 循环中的多次 .cpu().numpy() 调用。

    Args:
        boxes: YOLO Results.boxes 对象
        model_names: 模型类别名映射 {class_id: class_name}

    Returns:
        检测结果列表
    """
    if boxes is None or len(boxes) == 0:
        return []

    # 一次性批量传输 (3 次 GPU→CPU, 而非 N*4 次)
    xyxy_all = boxes.xyxy.cpu().numpy()
    cls_all = boxes.cls.cpu().numpy().astype(int)
    conf_all = boxes.conf.cpu().numpy()

    detections = []
    for i in range(len(cls_all)):
        detections.append({
            "class_id": int(cls_all[i]),
            "class_name": model_names.get(int(cls_all[i]), ""),
            "confidence": float(conf_all[i]),
            "xyxy": xyxy_all[i].tolist(),
        })

    return detections
