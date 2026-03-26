"""
_io_worker.py - 后台 I/O 写入线程 (双线程架构)
====================================================
将关键帧保存 / 标签写入 / 视频帧写入从推理线程中分离,
避免磁盘 I/O 阻塞 GPU 推理流水线。

架构:
    - 关键帧线程: 负责 imwrite + 标签写入 (核心产出, 阻塞提交保证不丢)
    - 视频帧线程: 负责 VideoWriter.write() (辅助回放, 非阻塞丢帧)
    两个线程并行写 SSD, 互不阻塞。

用法:
    writer = IOWriter(keyframe_queue_size=64, video_queue_size=32)
    writer.start()
    # 推理循环中:
    writer.submit_keyframe(frame, detections, ...)
    writer.submit_video_frame(frame)
    # 结束时:
    writer.stop()  # 会等待两个队列都排空
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from utils.label_writer import write_voc_xml, write_yolo_txt_from_xyxy
from utils.logger import get_logger


class IOWriter:
    """后台 I/O 双线程写入器: 关键帧 + 视频帧并行写入

    关键帧线程:
        - 阻塞提交 (核心产出, 不能丢帧)
        - 负责: imwrite (标注图/原图) + YOLO/VOC 标签写入

    视频帧线程:
        - 非阻塞提交 (辅助功能, 队列满时静默丢帧)
        - 负责: VideoWriter.write() 视频编码

    两个线程拥有独立队列, 互不阻塞, SSD 上可并行写入。
    """

    def __init__(
        self,
        queue_size: int = 64,
        video_queue_size: int = 32,
    ) -> None:
        # 关键帧队列 + 线程
        self._kf_queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._kf_stop = threading.Event()
        self._kf_thread: Optional[threading.Thread] = None

        # 视频帧队列 + 线程
        self._video_queue: queue.Queue = queue.Queue(maxsize=video_queue_size)
        self._video_stop = threading.Event()
        self._video_thread: Optional[threading.Thread] = None

        self._video_writer: Any = None
        self._logger = get_logger()

        # Bug1-fix: 跨线程计数器用锁保护
        self._counter_lock = threading.Lock()
        self._keyframe_count = 0
        self._video_dropped = 0

    @property
    def keyframe_count(self) -> int:
        """已保存的关键帧数量（线程安全）"""
        with self._counter_lock:
            return self._keyframe_count

    @property
    def video_dropped(self) -> int:
        """视频帧丢弃数量（线程安全）"""
        with self._counter_lock:
            return self._video_dropped

    def set_video_writer(self, writer: Any) -> None:
        """设置视频写入器 (支持 cv2.VideoWriter 或 FFmpegVideoWriter)"""
        self._video_writer = writer

    def reset(self, video_writer: Any = None) -> None:
        """重置计数器并切换视频写入器 (用于跨视频复用)

        注意: 调用前必须确保上一个视频的队列已排空 (调用 drain())。
        """
        with self._counter_lock:
            self._keyframe_count = 0
            self._video_dropped = 0
        self._video_writer = video_writer

    def drain(self) -> None:
        """等待两个队列排空, 但不停止线程 (用于视频切换间隙)"""
        self._kf_queue.join()
        self._video_queue.join()

    def start(self) -> None:
        """启动双线程"""
        self._kf_stop.clear()
        self._video_stop.clear()
        self._keyframe_count = 0
        self._video_dropped = 0

        self._kf_thread = threading.Thread(
            target=self._kf_loop, daemon=True, name="IOWriter-Keyframe"
        )
        self._kf_thread.start()

        self._video_thread = threading.Thread(
            target=self._video_loop, daemon=True, name="IOWriter-Video"
        )
        self._video_thread.start()

    def submit_keyframe(
        self,
        frame_idx: int,
        annotated_frame: Optional[np.ndarray],
        raw_frame: np.ndarray,
        detections: list[dict],
        keyframe_dir: Optional[Path],
        raw_keyframe_dir: Optional[Path],
        raw_labels_dir: Optional[Path],
        raw_labels_voc_dir: Optional[Path],
    ) -> None:
        """提交关键帧保存任务 (阻塞: 关键帧是核心产出, 不能丢)

        注意: 不做 frame.copy()，依赖以下不变量:
        - annotated_frame 已是 draw_detections() 内部 copy 的产物
        - raw_frame 来自 FrameDecoder 队列，每帧独立分配
        - 调用方提交后不会修改这些帧数据
        """
        task = (
            frame_idx,
            annotated_frame,
            raw_frame,
            detections,
            keyframe_dir,
            raw_keyframe_dir,
            raw_labels_dir,
            raw_labels_voc_dir,
        )
        self._kf_queue.put(task)

    def submit_video_frame(self, frame: np.ndarray) -> None:
        """提交视频帧写入任务 (非阻塞: 队列满时静默丢帧)

        视频录制是辅助功能, 丢帧不影响核心产出 (关键帧+标签)。
        非阻塞提交保证推理线程不会因视频编码慢而被阻塞。
        """
        try:
            self._video_queue.put_nowait(frame)
        except queue.Full:
            with self._counter_lock:
                self._video_dropped += 1

    # ==================== 关键帧线程 ====================

    def _kf_loop(self) -> None:
        """关键帧写入线程主循环"""
        while True:
            try:
                task = self._kf_queue.get(timeout=0.5)
            except queue.Empty:
                if self._kf_stop.is_set():
                    break
                continue

            if task is None:
                self._kf_queue.task_done()
                break  # 哨兵: 退出

            try:
                self._save_keyframe(*task)
            except Exception as e:
                self._logger.error(f"IOWriter 关键帧任务失败: {e}")
            finally:
                self._kf_queue.task_done()

    def _save_keyframe(
        self,
        frame_idx: int,
        annotated_frame: Optional[np.ndarray],
        raw_frame: np.ndarray,
        detections: list[dict],
        keyframe_dir: Optional[Path],
        raw_keyframe_dir: Optional[Path],
        raw_labels_dir: Optional[Path],
        raw_labels_voc_dir: Optional[Path],
    ) -> None:
        """执行关键帧保存 (关键帧线程中运行)"""
        frame_name = f"frame_{frame_idx:06d}"

        if keyframe_dir:
            keyframe_path = keyframe_dir / f"{frame_name}.jpg"
            save_frame = annotated_frame if annotated_frame is not None else raw_frame
            cv2.imwrite(str(keyframe_path), save_frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 90])

        if raw_keyframe_dir:
            raw_path = raw_keyframe_dir / f"{frame_name}.jpg"
            cv2.imwrite(str(raw_path), raw_frame,
                        [cv2.IMWRITE_JPEG_QUALITY, 90])

            h_frame, w_frame = raw_frame.shape[:2]

            # YOLO TXT
            if raw_labels_dir:
                label_path = raw_labels_dir / f"{frame_name}.txt"
                write_yolo_txt_from_xyxy(
                    label_path, detections, w_frame, h_frame
                )

            # VOC XML
            if raw_labels_voc_dir:
                write_voc_xml(
                    raw_labels_voc_dir / f"{frame_name}.xml",
                    frame_name, w_frame, h_frame, detections
                )

        with self._counter_lock:
            self._keyframe_count += 1

    # ==================== 视频帧线程 ====================

    def _video_loop(self) -> None:
        """视频帧写入线程主循环"""
        while True:
            try:
                frame = self._video_queue.get(timeout=0.5)
            except queue.Empty:
                if self._video_stop.is_set():
                    break
                continue

            if frame is None:
                self._video_queue.task_done()
                break  # 哨兵: 退出

            try:
                if self._video_writer and self._video_writer.isOpened():
                    self._video_writer.write(frame)
            except Exception as e:
                self._logger.error(f"IOWriter 视频帧任务失败: {e}")
            finally:
                self._video_queue.task_done()

    # ==================== 停止 ====================

    def stop(self) -> None:
        """停止双线程 (会等待两个队列中的任务全部完成)"""
        # 发送停止信号 + 哨兵 (加 timeout 防御性保护, 避免消费线程意外死亡时阻塞)
        self._kf_stop.set()
        try:
            self._kf_queue.put(None, timeout=5)
        except queue.Full:
            self._logger.warning("IOWriter 关键帧队列满, 哨兵发送失败")
        self._video_stop.set()
        try:
            self._video_queue.put(None, timeout=5)
        except queue.Full:
            self._logger.warning("IOWriter 视频队列满, 哨兵发送失败")

        # 等待两个线程排空
        if self._kf_thread is not None:
            self._kf_thread.join(timeout=30)
            if self._kf_thread.is_alive():
                self._logger.warning("IOWriter 关键帧线程超时未退出")

        if self._video_thread is not None:
            self._video_thread.join(timeout=30)
            if self._video_thread.is_alive():
                self._logger.warning("IOWriter 视频帧线程超时未退出")

        if self._video_dropped > 0:
            self._logger.info(
                f"IOWriter 视频帧丢弃: {self._video_dropped} 帧 (队列满)"
            )
