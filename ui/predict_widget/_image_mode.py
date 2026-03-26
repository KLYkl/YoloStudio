"""
_image_mode.py - ImageModeMixin: 图片模式专用槽函数
============================================
"""

from __future__ import annotations

import logging
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, Slot

from core.predict_handler import SaveCondition
from ui.base_ui import set_button_class


class ImageModeMixin:
    """图片模式专用槽函数: 翻页、批量处理、输出保存"""

    @Slot()
    def _on_image_prev(self) -> None:
        """上一张图片"""
        idx = self._image_processor.prev()
        if idx >= 0:
            result = self._image_processor.get_result(idx)
            if result:
                original, annotated, detections = result
                self._image_browser.show_result(original, annotated, detections)
                self._image_browser.update_navigation(idx, self._image_processor.processed_count)
                self._object_display.setText(f"检测: {len(detections)} 个")  # B7-fix

    @Slot()
    def _on_image_next(self) -> None:
        """下一张图片"""
        idx = self._image_processor.next()
        if idx >= 0:
            result = self._image_processor.get_result(idx)
            if result:
                original, annotated, detections = result
                self._image_browser.show_result(original, annotated, detections)
                self._image_browser.update_navigation(idx, self._image_processor.processed_count)
                self._object_display.setText(f"检测: {len(detections)} 个")  # B7-fix

    @Slot(int, int)
    def _on_image_batch_progress(self, current: int, total: int) -> None:
        """批量处理进度更新"""
        self._image_progress_bar.update_progress(current, total, "正在处理...")

    @Slot()
    def _on_image_batch_finished(self) -> None:
        """批量处理完成"""
        self._is_batch_processing = False

        processed = self._image_processor.processed_count
        total = self._image_processor.image_count

        self._image_progress_bar.set_finished(f"处理完成: {processed}/{total}")

        self._start_btn.setText("▶ 开始")
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

        if processed > 0:
            result = self._image_processor.get_result(0)
            if result:
                original, annotated, detections = result
                self._image_browser.show_result(original, annotated, detections)
                self._image_browser.update_navigation(0, processed)

        # R4-fix: 正常完成时也要清理线程对象 (与 _on_stop 路径一致)
        if self._batch_thread:
            self._batch_thread.deleteLater()
            self._batch_thread = None

        self._finalize_image_output()

        self.log_message.emit(f"图片批量处理完成: {processed}/{total}")

    def _start_image_processing(self) -> None:
        """启动图片处理"""
        is_batch = self._image_sub_group.checkedId() == 1

        if is_batch:
            source = self._batch_folder_edit.text().strip()
            if not source:
                self._on_error("请选择图片文件夹")
                return
        else:
            source = self._single_image_edit.text().strip()
            if not source:
                self._on_error("请选择图片文件")
                return

        model_path = self._model_path_edit.text().strip()
        if not model_path:
            self._on_error("请选择模型")
            return

        if self._predict_manager.model_path != model_path:
            if not self._predict_manager.load_model(model_path):
                return
            self._populate_class_filter()

        self._image_processor.set_model(self._predict_manager.model)

        count = self._image_processor.load_images(source)

        if count == 0:
            self._on_error("未找到图片")
            return

        output_dir = self._output_dir_edit.text().strip()
        if output_dir:
            from ui.output_dir_check import check_output_dir
            checked = check_output_dir(self, Path(output_dir))
            if checked is None:
                return
            output_dir = str(checked)
            self._output_dir_edit.setText(output_dir)
            self._output_manager.set_output_dir(output_dir)
            self._output_manager.setup_image_output_dirs()

        conf = self._conf_slider.value() / 100.0
        iou = self._iou_slider.value() / 100.0
        high_conf = self._img_threshold_slider.value() / 100.0
        self._image_processor.update_params(conf, iou, high_conf)

        self._is_image_mode = True
        self._preview_stack.setCurrentIndex(1)
        self._control_stack.setCurrentIndex(1)

        if count == 1:
            result = self._image_processor.process_single(0)
            if result:
                original, annotated, detections = result
                self._image_browser.show_result(original, annotated, detections)
                self._image_browser.update_navigation(0, 1)

            self._finalize_image_output()

            self._start_btn.setText("▶ 开始")
            self._stop_btn.setEnabled(False)
        else:
            # BUG-7: 先检查旧线程，再修改 UI
            if hasattr(self, '_batch_thread') and self._batch_thread and self._batch_thread.isRunning():
                self._on_error("上一次批量处理尚未完成")
                return

            self._is_batch_processing = True
            self._start_btn.setText("⋯ 处理中")
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)

            self._image_progress_bar.update_progress(0, count)

            filter_id = self._filter_group.checkedId()
            if filter_id == 0:
                condition = SaveCondition.ALL
            elif filter_id == 1:
                condition = SaveCondition.WITH_DETECTIONS
            elif filter_id == 2:
                condition = SaveCondition.WITHOUT_DETECTIONS
            elif filter_id == 3:
                condition = SaveCondition.HIGH_CONFIDENCE
            else:
                condition = SaveCondition.ALL

            # 读取性能模式，计算最佳 batch size
            from utils.batch_optimizer import compute_optimal_batch, PerformanceMode
            perf_idx = self._performance_combo.currentIndex()
            perf_mode = PerformanceMode.HIGH if perf_idx == 1 else PerformanceMode.OPTIMAL
            batch_config = compute_optimal_batch(mode=perf_mode)
            self._image_processor.set_batch_size(batch_config.image_batch_size)
            self.log_message.emit(
                f"性能模式: {'高性能' if perf_idx == 1 else '最优性能'} | "
                f"batch_size={batch_config.image_batch_size}"
            )

            from PySide6.QtCore import QThread

            class BatchProcessThread(QThread):
                """批量处理线程"""
                def __init__(self, processor, condition):
                    super().__init__()
                    self._processor = processor
                    self._condition = condition

                def run(self):
                    try:
                        self._processor.process_all(self._condition)
                    except Exception:
                        logging.getLogger(__name__).error(
                            f"图片批量处理线程异常:\n{traceback.format_exc()}"
                        )

            self._batch_thread = BatchProcessThread(self._image_processor, condition)
            self._batch_thread.start()

    def _finalize_image_output(self) -> None:
        """保存图片输出结果（使用后台线程避免阻塞 UI）"""
        output_dir = self._output_dir_edit.text().strip()
        if not output_dir:
            return

        from PySide6.QtCore import QThread

        class ImageOutputThread(QThread):
            """图片输出保存线程"""
            def __init__(self, processor, output_manager, options):
                super().__init__()
                self._processor = processor
                self._output_manager = output_manager
                self._options = options

            def run(self):
                try:
                    import cv2
                    from core.predict_handler._inference_utils import draw_detections

                    for path in self._processor.get_processed_list():
                        try:
                            detections = self._processor.get_detections(path)
                            if not detections and not self._options["save_annotated"]:
                                continue

                            original = cv2.imread(str(path))
                            if original is None:
                                continue

                            annotated = draw_detections(original, detections)

                            self._output_manager.save_image_result(
                                original=original,
                                annotated=annotated,
                                detections=detections,
                                image_name=path.stem,
                                save_original=self._options["save_original"],
                                save_annotated=self._options["save_annotated"],
                                save_labels=self._options["save_labels"],
                            )
                        except Exception:
                            logging.getLogger(__name__).error(
                                f"保存图片结果失败 {path.name}:\n{traceback.format_exc()}"
                            )

                    detected_list = self._processor.get_detected_list()
                    empty_list = self._processor.get_empty_list()
                    self._output_manager.save_path_list(detected_list, empty_list)

                    if self._options["save_report"]:
                        self._output_manager.generate_image_report(
                            total_images=self._processor.image_count,
                            detected_count=len(detected_list),
                            empty_count=len(empty_list),
                        )
                except Exception:
                    logging.getLogger(__name__).error(
                        f"图片输出线程异常:\n{traceback.format_exc()}"
                    )

        options = {
            "save_annotated": self._save_result_image_check.isChecked(),
            "save_original": self._save_original_check.isChecked(),
            "save_labels": self._save_labels_check.isChecked(),
            "save_report": self._save_image_report_check.isChecked(),
        }

        # Bug6-fix: 启动新输出线程前，等待旧线程完成
        if hasattr(self, '_output_thread') and self._output_thread and self._output_thread.isRunning():
            self._output_thread.wait(5000)

        self._output_thread = ImageOutputThread(
            self._image_processor, self._output_manager, options
        )
        self._output_thread.finished.connect(
            lambda: self.log_message.emit("图片输出保存完成")
        )
        # R3-fix: 补充 deleteLater 清理 QObject, 避免孤儿对象泄漏
        self._output_thread.finished.connect(
            lambda: (
                self._output_thread.deleteLater() if self._output_thread else None,
                setattr(self, '_output_thread', None)
            )
        )
        self._output_thread.start()
