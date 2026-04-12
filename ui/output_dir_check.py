"""
output_dir_check.py - 输出目录存在性检查工具
============================================

在执行文件输出操作前，检查目标目录是否已存在且包含文件。
如存在则弹窗询问用户：覆盖 / 新建唯一目录 / 取消。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget

from ui.styled_message_box import StyledMessageBox
from utils.file_utils import get_unique_dir
from utils.i18n import t


def check_output_dir(parent: QWidget, output_dir: Path) -> Path | None:
    """
    检查输出目录是否已存在并包含文件。

    - 目录不存在或为空目录 → 直接返回原路径
    - 目录已存在且有文件 → 弹窗询问
      - 覆盖: 返回原路径 (文件将写入已有目录)
      - 新建: 返回 get_unique_dir(原路径) 生成的唯一路径
      - 取消: 返回 None (调用方应中止操作)

    Args:
        parent: 父窗口 (用于弹窗居中)
        output_dir: 待检查的输出目录路径

    Returns:
        最终确定的输出目录路径，或 None 表示用户取消
    """
    if not output_dir.exists():
        return output_dir

    # 目录存在但为空 → 直接使用
    if not any(output_dir.iterdir()):
        return output_dir

    # 目录存在且包含文件 → 弹窗询问
    # 快速计数 (上限 1000，避免大目录阻塞 UI 线程)
    count_limit = 1000
    file_count = 0
    for item in output_dir.rglob("*"):
        if item.is_file():
            file_count += 1
            if file_count >= count_limit:
                break
    count_text = f"{count_limit}+" if file_count >= count_limit else str(file_count)
    choice = StyledMessageBox.three_way_question(
        parent,
        t("output_dir_exists"),
        t("output_dir_exists_msg", name=output_dir.name, count=count_text),
    )

    if choice == "overwrite":
        return output_dir
    elif choice == "new":
        return get_unique_dir(output_dir)
    else:
        return None
