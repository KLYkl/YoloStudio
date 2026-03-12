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
    results = model(frame, conf=conf, iou=iou, verbose=False)

    annotated_frame = results[0].plot()

    detections: list[dict] = []
    boxes = results[0].boxes

    if boxes is not None and len(boxes) > 0:
        h, w = frame.shape[:2]

        for i in range(len(boxes)):
            xyxy = boxes.xyxy[i].cpu().numpy()
            x1, y1, x2, y2 = xyxy

            class_id = int(boxes.cls[i].cpu().numpy())
            confidence = float(boxes.conf[i].cpu().numpy())
            class_name = model.names.get(class_id, str(class_id))

            det: dict = {
                "class_id": class_id,
                "class_name": class_name,
                "confidence": confidence,
                "xyxy": [float(x1), float(y1), float(x2), float(y2)],
            }

            if include_bbox:
                x_center = (x1 + x2) / 2 / w
                y_center = (y1 + y2) / 2 / h
                box_w = (x2 - x1) / w
                box_h = (y2 - y1) / h
                det["bbox"] = [x_center, y_center, box_w, box_h]

            detections.append(det)

    return annotated_frame, detections


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
