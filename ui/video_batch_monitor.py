"""
video_batch_monitor.py - 视频批量处理监控面板
============================================

职责:
    - 显示视频批量处理的总体进度
    - 以表格形式展示每个视频的处理状态
    - 实时显示当前视频的帧进度和统计信息

架构要点:
    - 纯 UI 控件，不包含业务逻辑
    - 通过公开方法接收数据并更新显示
    - 作为 _preview_stack 的 index 2 页面
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from utils.i18n import t


class VideoBatchMonitor(QWidget):
    """
    视频批量处理监控面板

    布局:
        - 顶部: 总体进度条 + 时间统计
        - 中部: 视频文件列表 (QTableWidget)
    """

    _COL_NAME = 0
    _COL_STATUS = 1
    _COL_FRAMES = 2
    _COL_DETECTIONS = 3
    _COL_DURATION = 4

    _STATUS_PENDING = t("status_pending")
    _STATUS_PROCESSING = t("status_processing")
    _STATUS_DONE = t("status_done")
    _STATUS_FAILED = t("status_failed")

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._total_videos: int = 0
        self._completed_videos: int = 0
        self._current_index: int = -1
        self._batch_start_time: float = 0.0
        self._video_start_times: dict[int, float] = {}

        self._setup_ui()

    # ==================== UI 构建 ====================

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 8)
        layout.setSpacing(12)

        layout.addWidget(self._create_header())
        layout.addWidget(self._create_table(), 1)

    def _create_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("batchMonitorHeader")
        vl = QVBoxLayout(header)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(8)

        self._title_label = QLabel(t("batch_progress_title"))
        self._title_label.setObjectName("batchMonitorTitle")
        vl.addWidget(self._title_label)

        self._overall_progress = QProgressBar()
        self._overall_progress.setObjectName("batchOverallProgress")
        self._overall_progress.setRange(0, 0)
        self._overall_progress.setFixedHeight(22)
        self._overall_progress.setFormat(t("batch_hint_select_folder"))
        self._overall_progress.setVisible(False)
        vl.addWidget(self._overall_progress)

        self._time_label = QLabel("")
        self._time_label.setObjectName("mutedLabel")
        self._time_label.setVisible(False)
        vl.addWidget(self._time_label)

        return header

    def _create_table(self) -> QTableWidget:
        self._table = QTableWidget(0, 5)
        self._table.setObjectName("batchVideoTable")
        self._table.setHorizontalHeaderLabels(
            [t("col_filename"), t("col_status"), t("col_frame_progress"), t("col_detections"), t("col_duration")]
        )
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)

        h = self._table.horizontalHeader()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(self._COL_NAME, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(self._COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self._COL_FRAMES, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self._COL_DETECTIONS, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self._COL_DURATION, QHeaderView.ResizeMode.ResizeToContents)

        return self._table

    # ==================== 公开 API ====================

    def set_video_list(self, video_paths: list[Path]) -> None:
        """填充视频列表并重置所有状态"""
        self._total_videos = len(video_paths)
        self._completed_videos = 0
        self._current_index = -1
        self._batch_start_time = time.time()
        self._video_start_times.clear()

        self._overall_progress.setVisible(True)
        self._overall_progress.setFormat(t("batch_progress_format"))
        self._overall_progress.setRange(0, self._total_videos)
        self._overall_progress.setValue(0)
        self._time_label.setVisible(True)
        self._time_label.setText(t("batch_time_started"))

        self._table.setRowCount(self._total_videos)
        for row, path in enumerate(video_paths):
            name_item = QTableWidgetItem(path.name)
            name_item.setToolTip(str(path))
            self._table.setItem(row, self._COL_NAME, name_item)

            self._set_cell(row, self._COL_STATUS, self._STATUS_PENDING)
            self._set_cell(row, self._COL_FRAMES, "--")
            self._set_cell(row, self._COL_DETECTIONS, "--")
            self._set_cell(row, self._COL_DURATION, "--")

    def on_video_started(self, video_path: str, index: int, total: int) -> None:
        """某个视频开始处理"""
        self._current_index = index
        self._video_start_times[index] = time.time()

        if 0 <= index < self._table.rowCount():
            self._set_cell(index, self._COL_STATUS, self._STATUS_PROCESSING)
            self._set_cell(index, self._COL_FRAMES, "0 / ?")
            self._highlight_row(index)

    def on_frame_progress(self, current: int, total: int) -> None:
        """当前视频帧进度更新"""
        idx = self._current_index
        if idx < 0 or idx >= self._table.rowCount():
            return

        if total > 0:
            percent = int(current / total * 100)
            text = f"{current} / {total} ({percent}%)"
        else:
            text = f"{current} / ?"
        self._set_cell(idx, self._COL_FRAMES, text)

        self._update_time_estimate()

    def on_video_finished(self, video_path: str, stats: dict) -> None:
        """单个视频处理完成"""
        idx = self._current_index
        if idx < 0 or idx >= self._table.rowCount():
            return

        self._completed_videos += 1
        self._overall_progress.setValue(self._completed_videos)

        self._set_cell(idx, self._COL_STATUS, self._STATUS_DONE)

        det_count = stats.get("detection_count/检测数量", 0)
        self._set_cell(idx, self._COL_DETECTIONS, str(det_count))

        start_t = self._video_start_times.get(idx, 0)
        if start_t > 0:
            elapsed = time.time() - start_t
            self._set_cell(idx, self._COL_DURATION, self._format_duration(elapsed))

        self._clear_row_highlight(idx)
        self._update_time_estimate()

    def on_batch_finished(self) -> None:
        """全部批量处理完成"""
        elapsed = time.time() - self._batch_start_time if self._batch_start_time else 0
        self._time_label.setText(
            t("batch_time_complete", elapsed=self._format_duration(elapsed))
        )

    def clear(self) -> None:
        """清空所有显示，恢复初始状态"""
        self._table.setRowCount(0)
        self._total_videos = 0
        self._completed_videos = 0
        self._current_index = -1
        self._batch_start_time = 0.0
        self._video_start_times.clear()

        self._overall_progress.setRange(0, 0)
        self._overall_progress.setFormat(t("batch_hint_select_folder"))
        self._overall_progress.setVisible(False)
        self._time_label.setText("")
        self._time_label.setVisible(False)

    # ==================== 内部辅助 ====================

    def _set_cell(self, row: int, col: int, text: str) -> None:
        item = self._table.item(row, col)
        if item is None:
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, col, item)
        else:
            item.setText(text)

        if col == self._COL_STATUS:
            self._apply_status_color(item, text)

    def _apply_status_color(self, item: QTableWidgetItem, status: str) -> None:
        from ui.theme import ThemeManager
        tm = ThemeManager.instance()

        color_map = {
            self._STATUS_PENDING: tm.get_color("text_dim"),
            self._STATUS_PROCESSING: tm.get_color("accent"),
            self._STATUS_DONE: tm.get_color("success"),
            self._STATUS_FAILED: tm.get_color("danger"),
        }
        color = color_map.get(status)
        if color:
            item.setForeground(QBrush(QColor(color)))

    def _highlight_row(self, row: int) -> None:
        from ui.theme import ThemeManager
        tm = ThemeManager.instance()
        accent = tm.get_color("accent")
        bg = QColor(accent)
        bg.setAlpha(30)
        brush = QBrush(bg)
        for col in range(self._table.columnCount()):
            item = self._table.item(row, col)
            if item:
                item.setBackground(brush)
        self._table.scrollToItem(self._table.item(row, 0))

    def _clear_row_highlight(self, row: int) -> None:
        for col in range(self._table.columnCount()):
            item = self._table.item(row, col)
            if item:
                item.setBackground(QBrush())

    def _update_time_estimate(self) -> None:
        if not self._batch_start_time or self._completed_videos <= 0:
            elapsed = time.time() - self._batch_start_time if self._batch_start_time else 0
            self._time_label.setText(
                t("batch_time_estimating", elapsed=self._format_duration(elapsed))
            )
            return

        elapsed = time.time() - self._batch_start_time
        avg_per_video = elapsed / self._completed_videos
        remaining_videos = self._total_videos - self._completed_videos
        est_remaining = avg_per_video * remaining_videos

        self._time_label.setText(
            t("batch_time_remaining", elapsed=self._format_duration(elapsed), remaining=self._format_duration(est_remaining))
        )

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total = int(seconds)
        if total >= 3600:
            h = total // 3600
            m = (total % 3600) // 60
            s = total % 60
            return f"{h:02d}:{m:02d}:{s:02d}"
        m = total // 60
        s = total % 60
        return f"{m:02d}:{s:02d}"
