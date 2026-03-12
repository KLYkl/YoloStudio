"""
_slots.py - SlotsMixin: 通用槽函数
============================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QFileDialog

from core.camera_scanner import DeviceScanner
from core.predict_handler import InputSourceType
from ui.base_ui import set_button_class
from ui.styled_message_box import StyledMessageBox


class SlotsMixin:
    """通用槽函数: 浏览/参数/播放控制/开始停止/帧处理"""

    # ==================== 输入源切换 ====================

    @Slot(int)
    def _on_source_type_changed(self, id: int) -> None:
        """输入源类型切换"""
        is_image_mode = (id == 0)

        self._image_mode_container.setVisible(id == 0)
        self._video_mode_container.setVisible(id == 1)
        self._camera_container.setVisible(id == 2)
        self._screen_container.setVisible(id == 3)

        self._image_output_container.setVisible(is_image_mode)
        self._video_output_container.setVisible(not is_image_mode)

        self._preview_stack.setCurrentIndex(1 if is_image_mode else 0)
        self._control_stack.setCurrentIndex(1 if is_image_mode else 0)

        if id == 2 and not self._cameras_scanned:
            self._scan_cameras()
            self._cameras_scanned = True
        elif id == 3 and not self._screens_scanned:
            self._scan_screens()
            self._screens_scanned = True

    @Slot(int)
    def _on_image_sub_changed(self, id: int) -> None:
        """图片子选项切换"""
        self._single_image_container.setVisible(id == 0)
        self._batch_image_container.setVisible(id == 1)

    @Slot(int)
    def _on_video_sub_changed(self, id: int) -> None:
        """视频子选项切换"""
        self._single_video_container.setVisible(id == 0)
        self._batch_video_container.setVisible(id == 1)
        self._is_video_batch_mode = (id == 1)

    # ==================== 浏览按钮 ====================

    @Slot()
    def _on_browse_single_image(self) -> None:
        """浏览单张图片"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp *.tiff *.tif);;所有文件 (*)"
        )
        if path:
            self._single_image_edit.setText(path)

    @Slot()
    def _on_browse_batch_folder(self) -> None:
        """浏览批量处理文件夹"""
        path = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if path:
            self._batch_folder_edit.setText(path)

    @Slot()
    def _on_browse_batch_video_folder(self) -> None:
        """浏览批量视频文件夹"""
        path = QFileDialog.getExistingDirectory(self, "选择视频文件夹")
        if path:
            self._batch_video_folder_edit.setText(path)

    @Slot()
    def _on_browse_source(self) -> None:
        """视频模式浏览按钮"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频", "",
            "视频文件 (*.mp4 *.avi *.mov *.mkv *.wmv);;所有文件 (*)"
        )
        if path:
            self._source_path_edit.setText(path)

    @Slot()
    def _on_browse_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择模型", "", "PyTorch 模型 (*.pt);;所有文件 (*)")
        if path:
            self._model_path_edit.setText(path)
            self._model_display.setText(f"模型: {Path(path).name}")
            self._model_display.setObjectName("successLabel")
            self._model_display.style().unpolish(self._model_display)
            self._model_display.style().polish(self._model_display)

    @Slot()
    def _on_browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self._output_dir_edit.setText(path)

    # ==================== 参数和设备 ====================

    @Slot(bool)
    def _on_rtsp_toggled(self, checked: bool) -> None:
        self._rtsp_edit.setEnabled(checked)
        self._test_rtsp_btn.setEnabled(checked)
        self._camera_combo.setEnabled(not checked)

    @Slot()
    def _on_test_rtsp(self) -> None:
        url = self._rtsp_edit.text().strip()
        if not url:
            StyledMessageBox.warning(self, "警告", "请输入 RTSP 地址")
            return
        self.log_message.emit(f"正在测试 RTSP: {url}")
        success, error = DeviceScanner.test_rtsp(url)
        if success:
            StyledMessageBox.information(self, "成功", "RTSP 连接成功!")
            self.log_message.emit("RTSP 测试通过")
        else:
            StyledMessageBox.warning(self, "失败", f"RTSP 连接失败: {error}")
            self.log_message.emit(f"RTSP 测试失败: {error}")

    @Slot(int)
    def _on_conf_changed(self, value: int) -> None:
        conf = value / 100.0
        self._conf_label.setText(f"{conf:.2f}")
        if self._predict_manager.is_running:
            self._predict_manager.update_params(conf, self._iou_slider.value() / 100.0)

    @Slot(int)
    def _on_iou_changed(self, value: int) -> None:
        iou = value / 100.0
        self._iou_label.setText(f"{iou:.2f}")
        if self._predict_manager.is_running:
            self._predict_manager.update_params(self._conf_slider.value() / 100.0, iou)

    @Slot(bool)
    def _on_high_conf_toggled(self, checked: bool) -> None:
        self._threshold_slider.setEnabled(checked)
        new_name = "accentLabel" if checked else "mutedLabel"
        self._threshold_label.setObjectName(new_name)
        self._threshold_label.style().unpolish(self._threshold_label)
        self._threshold_label.style().polish(self._threshold_label)

    @Slot(int)
    def _on_threshold_changed(self, value: int) -> None:
        self._threshold_label.setText(f"{value / 100.0:.2f}")

    @Slot(bool)
    def _on_img_high_conf_toggled(self, checked: bool) -> None:
        self._img_threshold_slider.setEnabled(checked)

    @Slot(int)
    def _on_img_threshold_changed(self, value: int) -> None:
        self._img_threshold_label.setText(f"{value / 100.0:.2f}")

    def _populate_class_filter(self) -> None:
        """从已加载的模型中填充类别过滤下拉框"""
        self._class_filter_combo.clear()
        self._class_filter_combo.addItem("全部")
        if self._predict_manager._model is not None:
            names = getattr(self._predict_manager._model, 'names', {})
            for class_id in sorted(names.keys()):
                self._class_filter_combo.addItem(f"{class_id}: {names[class_id]}")

    def _scan_cameras(self) -> None:
        """扫描摄像头设备"""
        self._cameras = DeviceScanner.scan_cameras()
        self._camera_combo.clear()
        for cam in self._cameras:
            self._camera_combo.addItem(cam["name"])
        self.log_message.emit(f"摄像头扫描完成: {len(self._cameras)} 个设备")

    def _scan_screens(self) -> None:
        """扫描屏幕设备"""
        self._screens = DeviceScanner.scan_screens()
        self._screen_combo.clear()
        for screen in self._screens:
            self._screen_combo.addItem(screen["name"])
        self.log_message.emit(f"屏幕扫描完成: {len(self._screens)} 个显示器")

    # ==================== 开始/暂停/停止 ====================

    @Slot()
    def _on_start_pause_clicked(self) -> None:
        """处理开始/暂停按钮点击"""
        if self._is_image_mode and self._is_batch_processing:
            if self._image_processor.is_paused:
                self._image_processor.resume()
                self._start_btn.setText("⏸ 暂停")
                set_button_class(self._start_btn, "warning")
                self._image_progress_bar.update_progress(
                    self._image_processor.processed_count,
                    self._image_processor.image_count,
                    "正在处理..."
                )
            else:
                self._image_processor.pause()
                self._start_btn.setText("▶ 继续")
                set_button_class(self._start_btn, "success")
                self._image_progress_bar.update_progress(
                    self._image_processor.processed_count,
                    self._image_processor.image_count,
                    "已暂停"
                )
            return

        if self._predict_manager.is_running:
            if self._predict_manager.is_paused:
                self._predict_manager.resume()
                self._start_btn.setText("⏸ 暂停")
                set_button_class(self._start_btn, "warning")
            else:
                self._predict_manager.pause()
                self._start_btn.setText("▶ 继续")
                set_button_class(self._start_btn, "success")
            return

        self._on_start()

    def _on_start(self) -> None:
        """启动预测"""
        model_path = self._model_path_edit.text().strip()
        if not model_path or not Path(model_path).exists():
            StyledMessageBox.warning(self, "警告", "请选择有效的模型文件")
            return
        if self._predict_manager._model_path != model_path:
            self.log_message.emit(f"正在加载模型: {model_path}")
            if not self._predict_manager.load_model(model_path):
                StyledMessageBox.critical(self, "错误", "模型加载失败")
                return
            self.log_message.emit("模型加载成功")
            self._populate_class_filter()

        source_id = self._source_btn_group.checkedId()
        source, source_type, screen_region = None, None, None

        if source_id == 0:
            self._start_image_processing()
            return
        elif source_id == 1:
            if self._is_video_batch_mode:
                self._start_video_batch_processing()
                return
            else:
                source = self._source_path_edit.text().strip()
                source_type = InputSourceType.VIDEO
                if not source or not Path(source).exists():
                    StyledMessageBox.warning(self, "警告", "请选择有效的视频")
                    return
        elif source_id == 2:
            if self._rtsp_check.isChecked():
                source = self._rtsp_edit.text().strip()
                source_type = InputSourceType.RTSP
                if not source:
                    StyledMessageBox.warning(self, "警告", "请输入 RTSP 地址")
                    return
            else:
                idx = self._camera_combo.currentIndex()
                if idx < 0 or idx >= len(self._cameras):
                    StyledMessageBox.warning(self, "警告", "请选择摄像头")
                    return
                source = self._cameras[idx]["id"]
                source_type = InputSourceType.CAMERA
        elif source_id == 3:
            idx = self._screen_combo.currentIndex()
            if idx < 0 or idx >= len(self._screens):
                StyledMessageBox.warning(self, "警告", "请选择屏幕")
                return
            screen = self._screens[idx]
            source = f"screen_{idx}"
            source_type = InputSourceType.SCREEN
            screen_region = {"left": screen["left"], "top": screen["top"], "width": screen["width"], "height": screen["height"]}

        output_dir = self._output_dir_edit.text().strip()
        if output_dir and (self._save_video_check.isChecked() or self._save_keyframe_annotated_check.isChecked() or self._save_keyframe_raw_check.isChecked() or self._save_report_check.isChecked()):
            self._output_manager.set_output_dir(output_dir)
            self._output_manager.reset_stats()
            if self._save_video_check.isChecked():
                info = DeviceScanner.get_video_info(source)
                if info:
                    self._output_manager.start_video(fps=info.get("fps", 30.0), size=(info.get("width", 1920), info.get("height", 1080)))
                    self._is_recording = True
                    self._video_fps = info.get("fps", 30.0)
                else:
                    self._video_fps = 30.0

        conf = self._conf_slider.value() / 100.0
        iou = self._iou_slider.value() / 100.0
        self.log_message.emit(f"开始预测: {source}")

        self._current_source_type = source_type

        if self._predict_manager.start(source=source, source_type=source_type, conf=conf, iou=iou, screen_region=screen_region):
            self._stop_btn.setEnabled(True)
            self._frame_count = 0
            self._fps_frame_count = 0
            self._fps_timer.start(1000)

            self._playback_bar.setVisible(True)

            is_video = source_type == InputSourceType.VIDEO
            is_image = source_type == InputSourceType.IMAGE
            self._progress_slider.setEnabled(is_video)
            self._progress_slider.setRange(0, 10000)
            self._progress_slider.setValue(0)
            self._time_label.setText("00:00 / 00:00")

            if is_image:
                self._start_btn.setEnabled(False)
            else:
                self._start_btn.setText("⏸ 暂停")
                set_button_class(self._start_btn, "warning")
        else:
            StyledMessageBox.critical(self, "错误", "启动预测失败")

    @Slot()
    def _on_stop(self) -> None:
        self._is_stopping = True

        if self._is_image_mode and self._is_batch_processing:
            self._image_processor.stop()
            if self._batch_thread and self._batch_thread.isRunning():
                if not self._batch_thread.wait(5000):
                    self.log_message.emit("[警告] 批量处理线程超时未结束")
            self._is_batch_processing = False
            self._image_progress_bar.set_finished("处理已中止")
            self.log_message.emit("图片批量处理已停止")
        elif self._video_batch_processor.is_running:
            self._video_batch_processor.stop()
            if self._video_batch_thread and self._video_batch_thread.isRunning():
                if not self._video_batch_thread.wait(5000):
                    self.log_message.emit("[警告] 视频批量处理线程超时未结束")
            self.log_message.emit("视频批量处理已停止")
        elif self._predict_manager.is_running:
            self._predict_manager.stop()
            self._fps_timer.stop()
            if self._is_recording:
                video_path = self._output_manager.stop_video()
                if video_path:
                    self.log_message.emit(f"视频已保存: {video_path}")
                self._is_recording = False
            if self._save_report_check.isChecked():
                report_path = self._output_manager.generate_report()
                if report_path:
                    self.log_message.emit(f"报告已生成: {report_path}")

            self._progress_slider.setValue(0)
            self._progress_slider.setEnabled(False)
            self._time_label.setText("00:00 / 00:00")
            self._current_source_type = None
            self.log_message.emit("预测已停止")

        self._start_btn.setEnabled(True)
        self._start_btn.setText("▶ 开始")
        set_button_class(self._start_btn, "success")
        self._stop_btn.setEnabled(False)

        self._is_stopping = False

    # ==================== 帧处理和回调 ====================

    @Slot(np.ndarray, np.ndarray, list)
    def _on_frame_ready(self, annotated_frame: np.ndarray, raw_frame: np.ndarray, detections: list) -> None:
        self._preview_canvas.update_frame(annotated_frame)
        self._frame_count += 1
        self._fps_frame_count += 1
        self._object_count = len(detections)
        self._frame_display.setText(f"已处理: {self._frame_count} 帧")
        self._object_display.setText(f"检测: {self._object_count} 个")
        if self._is_recording:
            self._output_manager.write_frame(annotated_frame)

        save_annotated = self._save_keyframe_annotated_check.isChecked()
        save_raw = self._save_keyframe_raw_check.isChecked()

        if (save_annotated or save_raw) and detections:
            if self._high_conf_check.isChecked():
                thresh = self._threshold_slider.value() / 100.0
                high_conf = [d for d in detections if d.get("confidence", 0) >= thresh]
                if high_conf:
                    self._output_manager.save_keyframe(
                        annotated_frame, high_conf,
                        save_annotated=save_annotated,
                        save_raw=save_raw,
                        raw_frame=raw_frame
                    )
            else:
                self._output_manager.save_keyframe(
                    annotated_frame, detections,
                    save_annotated=save_annotated,
                    save_raw=save_raw,
                    raw_frame=raw_frame
                )

    @Slot(dict)
    def _on_stats_updated(self, stats: dict) -> None:
        if "fps" in stats:
            self._current_fps = stats["fps"]

    @Slot(str)
    def _on_error(self, error: str) -> None:
        self.log_message.emit(f"[错误] {error}")

    @Slot()
    def _on_prediction_finished(self) -> None:
        self._on_stop()

    @Slot(str)
    def _on_file_saved(self, path: str) -> None:
        self.log_message.emit(f"文件已保存: {path}")

    @Slot()
    def _toggle_panel(self) -> None:
        """切换配置面板显示/隐藏"""
        if self._is_panel_collapsed:
            self._settings_panel.setVisible(True)
            self._splitter.setSizes([self.PANEL_WIDTH, self._splitter.width() - self.PANEL_WIDTH])
            self._toggle_btn.setToolTip("折叠设置面板")
        else:
            self._settings_panel.setVisible(False)
            self._toggle_btn.setToolTip("展开设置面板")
        self._is_panel_collapsed = not self._is_panel_collapsed

    def _set_layout_visible(self, layout, visible: bool) -> None:
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget():
                item.widget().setVisible(visible)
            elif item.layout():
                self._set_layout_visible(item.layout(), visible)

    @Slot()
    def _update_fps_display(self) -> None:
        self._fps_display.setText(f"FPS: {self._fps_frame_count}")
        self._fps_frame_count = 0

    # ==================== 播放控制 ====================

    @Slot()
    def _on_progress_seek(self) -> None:
        """处理进度条拖动释放"""
        if not self._predict_manager.is_seekable:
            return
        total = self._predict_manager.total_frames
        if total <= 0:
            return
        target_frame = int(self._progress_slider.value() / 10000 * total)
        self._predict_manager.seek(target_frame)

    @Slot(str)
    def _on_playback_state_changed(self, state: str) -> None:
        """处理播放状态变化"""
        if state in ("playing", "paused"):
            if self._is_stopping or not self._predict_manager.is_running:
                return

        if state == "playing":
            self._start_btn.setText("⏸ 暂停")
            set_button_class(self._start_btn, "warning")
        elif state == "paused":
            self._start_btn.setText("▶ 继续")
            set_button_class(self._start_btn, "success")
        elif state == "idle":
            self._start_btn.setEnabled(True)
            self._start_btn.setText("▶ 开始")
            self._stop_btn.setEnabled(False)
            self._is_stopping = False
            set_button_class(self._start_btn, "success")

    @Slot(int, int)
    def _on_progress_updated(self, current: int, total: int) -> None:
        """处理进度更新"""
        if total <= 0:
            return

        if not self._progress_slider.isSliderDown():
            progress = int(current / total * 10000)
            self._progress_slider.setValue(progress)

        fps = getattr(self, '_video_fps', 30.0)
        current_sec = current / fps
        total_sec = total / fps
        self._time_label.setText(f"{self._format_time(current_sec)} / {self._format_time(total_sec)}")

    def _format_time(self, seconds: float) -> str:
        """格式化时间为 MM:SS"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"
