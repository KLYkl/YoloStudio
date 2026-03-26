"""
_inference_utils.py - 推理工具函数
============================================

提供 YOLO 推理和检测结果绘制的纯函数，
供 PredictWorker / ImageBatchProcessor / VideoBatchProcessor 共用。
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from core.predict_handler._frame_decoder import extract_detections_fast


# 20 种预定义的类别颜色 (BGR 格式)
DETECTION_COLORS: list[tuple[int, int, int]] = [
    (255, 56, 56), (255, 157, 151), (255, 112, 31), (255, 178, 29),
    (207, 210, 49), (72, 249, 10), (146, 204, 23), (61, 219, 134),
    (26, 147, 52), (0, 212, 187), (44, 153, 168), (0, 194, 255),
    (52, 69, 147), (100, 115, 255), (0, 24, 236), (132, 56, 255),
    (82, 0, 133), (203, 56, 255), (255, 149, 200), (255, 55, 199),
]


def run_inference(
    model: Any,
    frame: np.ndarray,
    conf: float,
    iou: float,
    include_bbox: bool = True,
) -> tuple[np.ndarray, list[dict]]:
    """
    执行单帧 YOLO 推理

    Args:
        model: YOLO 模型实例
        frame: BGR 格式的输入帧
        conf: 置信度阈值
        iou: IoU 阈值
        include_bbox: 是否计算归一化 bbox (x_center, y_center, w, h)

    Returns:
        (标注后的帧, 检测结果列表)
    """
    results = model(frame, conf=conf, iou=iou, half=True, verbose=False)

    # 向量化批量提取: 3 次 GPU→CPU 传输, 替代逐 box 的 3N 次拷贝
    detections = extract_detections_fast(results[0].boxes, model.names)

    # 按需补充归一化 bbox (仅图片批量处理需要)
    if include_bbox and detections:
        h, w = frame.shape[:2]
        for det in detections:
            x1, y1, x2, y2 = det["xyxy"]
            det["bbox"] = [
                (x1 + x2) / 2 / w,
                (y1 + y2) / 2 / h,
                (x2 - x1) / w,
                (y2 - y1) / h,
            ]

    # 按需绘制标注帧 (替代之前的 results[0].plot() 全量绘制)
    # Issue6-fix: 无检测时不做 frame.copy(), 节省高帧率场景的内存分配
    # draw_detections() 内部已有 copy() 保证不修改原帧
    annotated_frame = draw_detections(frame, detections) if detections else frame

    return annotated_frame, detections


def run_batch_inference(
    model: Any,
    frames: list[np.ndarray],
    conf: float,
    iou: float,
) -> list[list[dict]]:
    """批量多帧 YOLO 推理

    一次将多张图送入模型，GPU 并行处理，显著提高利用率。

    Args:
        model: YOLO 模型实例
        frames: BGR 格式的输入帧列表
        conf: 置信度阈值
        iou: IoU 阈值

    Returns:
        每张图对应的检测结果列表，长度与 frames 相同
    """
    if not frames:
        return []

    # YOLO model() 支持传入 list[ndarray]，自动 batch 推理
    results = model(frames, conf=conf, iou=iou, half=True, verbose=False)

    batch_detections: list[list[dict]] = []
    for i, result in enumerate(results):
        detections = extract_detections_fast(result.boxes, model.names)

        # 补充归一化 bbox (图片批量处理需要)
        if detections:
            h, w = frames[i].shape[:2]
            for det in detections:
                x1, y1, x2, y2 = det["xyxy"]
                det["bbox"] = [
                    (x1 + x2) / 2 / w,
                    (y1 + y2) / 2 / h,
                    (x2 - x1) / w,
                    (y2 - y1) / h,
                ]

        batch_detections.append(detections)

    return batch_detections


def draw_detections(
    frame: np.ndarray,
    detections: list[dict],
) -> np.ndarray:
    """
    在帧上绘制检测结果 (矩形框 + 类别标签)

    Args:
        frame: 原始帧 (BGR)
        detections: 检测结果列表，每项需包含 xyxy, class_name, confidence, class_id

    Returns:
        绘制后的帧副本
    """
    annotated = frame.copy()

    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["xyxy"]]
        class_name = det["class_name"]
        confidence = det["confidence"]
        class_id = det["class_id"]

        color = DETECTION_COLORS[class_id % len(DETECTION_COLORS)]

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        label = f"{class_name} {confidence:.2f}"
        (label_w, label_h), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
        )
        cv2.rectangle(
            annotated,
            (x1, y1 - label_h - baseline - 4),
            (x1 + label_w, y1),
            color,
            -1
        )
        cv2.putText(
            annotated,
            label,
            (x1, y1 - baseline - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1
        )

    return annotated
