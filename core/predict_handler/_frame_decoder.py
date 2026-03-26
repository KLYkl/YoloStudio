"""
_frame_decoder.py - 异步视频帧解码器 + 向量化检测提取
====================================================
将视频解码与 GPU 推理流水线化:
- 解码线程: 提前读取帧到队列, GPU 不用等 CPU 解码
- 向量化提取: 一次性 GPU→CPU 拷贝, 替代逐 box 循环
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Optional

import cv2
import numpy as np


class FrameDecoder(threading.Thread):
    """异步视频帧解码线程

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
                    break  # 哨兵: 视频结束
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
