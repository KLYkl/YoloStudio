"""
label_writer.py - 标签写入工具函数
============================================

提供 VOC XML 和 YOLO TXT 格式的标签写入纯函数，
供 OutputManager / VideoBatchProcessor 等共用。
"""

from __future__ import annotations

from pathlib import Path


def write_voc_xml(
    xml_path: Path,
    image_name: str,
    width: int,
    height: int,
    detections: list[dict],
) -> None:
    """
    写入 Pascal VOC XML 格式标签

    Args:
        xml_path: XML 文件输出路径
        image_name: 图片文件名（不含扩展名）
        width: 图片宽度
        height: 图片高度
        detections: 检测结果列表，每项需包含 class_name 和 xyxy
    """
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<annotation>',
        f'    <filename>{image_name}.jpg</filename>',
        '    <size>',
        f'        <width>{width}</width>',
        f'        <height>{height}</height>',
        '        <depth>3</depth>',
        '    </size>',
    ]

    for det in detections:
        name = det.get("class_name", "unknown")
        xyxy = det.get("xyxy", [0, 0, 0, 0])
        x1, y1, x2, y2 = [int(v) for v in xyxy]

        xml_lines.extend([
            '    <object>',
            f'        <name>{name}</name>',
            '        <pose>Unspecified</pose>',
            '        <truncated>0</truncated>',
            '        <difficult>0</difficult>',
            '        <bndbox>',
            f'            <xmin>{x1}</xmin>',
            f'            <ymin>{y1}</ymin>',
            f'            <xmax>{x2}</xmax>',
            f'            <ymax>{y2}</ymax>',
            '        </bndbox>',
            '    </object>',
        ])

    xml_lines.append('</annotation>')

    with open(xml_path, "w", encoding="utf-8") as f:
        f.write("\n".join(xml_lines))


def write_yolo_txt(
    txt_path: Path,
    detections: list[dict],
) -> None:
    """
    写入 YOLO TXT 格式标签

    Args:
        txt_path: TXT 文件输出路径
        detections: 检测结果列表，每项需包含 class_id 和 bbox
                    bbox 格式: [x_center, y_center, width, height] (归一化)
    """
    with open(txt_path, "w", encoding="utf-8") as f:
        for det in detections:
            class_id = det.get("class_id", 0)
            bbox = det.get("bbox", [0.5, 0.5, 0.1, 0.1])
            f.write(f"{class_id} {bbox[0]:.6f} {bbox[1]:.6f} {bbox[2]:.6f} {bbox[3]:.6f}\n")


def write_yolo_txt_from_xyxy(
    txt_path: Path,
    detections: list[dict],
    frame_width: int,
    frame_height: int,
) -> None:
    """
    从 xyxy 坐标写入 YOLO TXT 格式标签 (自动归一化)

    Args:
        txt_path: TXT 文件输出路径
        detections: 检测结果列表，每项需包含 class_id 和 xyxy
        frame_width: 帧宽度
        frame_height: 帧高度
    """
    with open(txt_path, "w", encoding="utf-8") as f:
        for d in detections:
            cid = d["class_id"]
            x1, y1, x2, y2 = d["xyxy"]
            xc = (x1 + x2) / 2 / frame_width
            yc = (y1 + y2) / 2 / frame_height
            bw = (x2 - x1) / frame_width
            bh = (y2 - y1) / frame_height
            f.write(f"{cid} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")
