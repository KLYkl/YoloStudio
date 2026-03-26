"""
_video_batch.py - VideoBatchMixin: 视频批量处理槽函数
============================================
"""

from __future__ import annotations

import logging
import traceback
from pathlib import Path

from PySide6.QtCore import Slot

from ui.base_ui import set_button_class
from ui.styled_message_box import StyledMessageBox


class VideoBatchMixin:
    """视频批量处理相关槽函数"""

    @Slot(str, int, int)
    def _on_video_batch_started(self, video_path: str, index: int, total: int) -> None:
        """单个视频开始处理"""
        video_name = Path(video_path).name
        # 帧进度和FPS分别使用独立控件，避免信号竞争导致闪跳
        self._frame_display.setText(f"帧: 0/0 (0%)")
        self._object_display.setText(f"视频 [{index+1}/{total}]: {video_name}")
        self._fps_display.setText(f"FPS: --")
        self._progress_slider.setValue(0)
        self._time_label.setText("00:00 / 00:00")
        self.log_message.emit(f"开始处理视频: {video_name}")

    @Slot(int, int)
    def _on_video_frame_progress(self, current: int, total: int) -> None:
        """当前视频帧进度更新 → 写入 _frame_display (不与 FPS 竞争)"""
        if total > 0:
            percent = int(current / total * 100)
            self._frame_display.setText(f"帧: {current}/{total} ({percent}%)")

    @Slot(int, int)
    def _on_video_batch_progress(self, completed: int, total: int) -> None:
        """整体批量进度更新"""
        pass

    @Slot(float)
    def _on_video_speed_updated(self, fps: float) -> None:
        """视频批量处理 FPS 更新 → 写入 _fps_display (专用控件)"""
        self._fps_display.setText(f"FPS: {fps:.1f}")

    @Slot()
    def _on_video_batch_finished(self) -> None:
        """视频批量处理完成"""
        if hasattr(self, '_video_batch_thread') and self._video_batch_thread:
            if self._video_batch_thread.isRunning():
                self._video_batch_thread.wait(3000)
            self._video_batch_thread.deleteLater()
            self._video_batch_thread = None
        self._start_btn.setText("▶ 开始")
        set_button_class(self._start_btn, "success")  # Issue15-fix: 重置按钮样式
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

        report_path = self._video_batch_processor.generate_batch_report()
        if report_path:
            self.log_message.emit(f"批量处理完成，汇总报告: {report_path}")
        else:
            self.log_message.emit("批量处理完成")

        stats = self._video_batch_processor.get_all_stats()
        total_detections = sum(s.get("detection_count/检测数量", 0) for s in stats.values())
        total_keyframes = sum(s.get("keyframes_saved/已保存关键帧", 0) for s in stats.values())

        self._frame_display.setText(f"已处理: {len(stats)} 个视频")
        self._object_display.setText(f"检测: {total_detections} 个")

        StyledMessageBox.information(
            self,
            "批量处理完成",
            f"已处理 {len(stats)} 个视频\n"
            f"总检测数: {total_detections}\n"
            f"保存关键帧: {total_keyframes}"
        )

    def _start_video_batch_processing(self) -> None:
        """启动视频批量处理"""
        # 前置检查: 旧线程是否仍在运行 (必须在修改 UI 之前)
        if hasattr(self, '_video_batch_thread') and self._video_batch_thread and self._video_batch_thread.isRunning():
            StyledMessageBox.warning(self, "警告", "上一次批量处理尚未完成")
            return

        source = self._batch_video_folder_edit.text().strip()
        if not source:
            StyledMessageBox.warning(self, "警告", "请选择视频文件夹")
            return

        model_path = self._model_path_edit.text().strip()
        if not model_path:
            StyledMessageBox.warning(self, "警告", "请选择模型文件")
            return

        if not self._predict_manager.is_model_loaded:
            success = self._predict_manager.load_model(model_path)
            if not success:
                return
            self._populate_class_filter()

        output_dir = self._output_dir_edit.text().strip()
        if not output_dir:
            StyledMessageBox.warning(self, "警告", "请选择输出目录")
            return
        model_name = Path(model_path).stem
        output_dir = str(Path(output_dir) / model_name)

        from ui.output_dir_check import check_output_dir
        checked = check_output_dir(self, Path(output_dir))
        if checked is None:
            return
        output_dir = str(checked)

        video_count = self._video_batch_processor.load_videos(source)
        if video_count == 0:
            StyledMessageBox.warning(self, "警告", "未找到视频文件")
            return

        self._video_batch_processor.set_model(self._predict_manager.model)
        self._video_batch_processor.update_params(
            conf=self._conf_slider.value() / 100,
            iou=self._iou_slider.value() / 100,
            high_conf_threshold=self._threshold_slider.value() / 100
        )
        self._video_batch_processor.set_output_options(
            output_dir=output_dir,
            save_video=self._save_video_check.isChecked(),
            save_keyframes_annotated=self._save_keyframe_annotated_check.isChecked(),
            save_keyframes_raw=self._save_keyframe_raw_check.isChecked(),
            save_report=self._save_report_check.isChecked(),
            high_conf_only=self._high_conf_check.isChecked()
        )

        # 读取性能模式，计算最佳 batch size 和解码策略
        from utils.batch_optimizer import compute_optimal_batch, PerformanceMode
        perf_idx = self._performance_combo.currentIndex()
        perf_mode = PerformanceMode.HIGH if perf_idx == 1 else PerformanceMode.OPTIMAL
        batch_config = compute_optimal_batch(mode=perf_mode)
        self._video_batch_processor.set_batch_size(batch_config.video_batch_size)
        self._video_batch_processor.set_decode_mode(
            batch_config.decode_mode, batch_config.decode_workers
        )
        self.log_message.emit(
            f"性能模式: {'高性能' if perf_idx == 1 else '最优性能'} | "
            f"batch_size={batch_config.video_batch_size}, "
            f"解码={batch_config.decode_mode}"
        )

        # 通过所有验证后再修改 UI 状态
        self._start_btn.setText("⏸ 暂停")
        set_button_class(self._start_btn, "warning")
        self._stop_btn.setEnabled(True)
        self._playback_bar.setVisible(False)

        self.log_message.emit(f"开始批量处理 {video_count} 个视频")

        from PySide6.QtCore import QThread

        class VideoBatchThread(QThread):
            """视频批量处理线程"""
            def __init__(self, processor):
                super().__init__()
                self._processor = processor

            def run(self):
                try:
                    self._processor.process_all()
                except Exception:
                    logging.getLogger(__name__).error(
                        f"视频批量处理线程异常:\n{traceback.format_exc()}"
                    )

        self._video_batch_thread = VideoBatchThread(self._video_batch_processor)
        self._video_batch_thread.start()
