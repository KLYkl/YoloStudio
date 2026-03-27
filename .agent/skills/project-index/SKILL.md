---
name: project-index
description: YoloDo2.0 Project Function Index. Use this skill to quickly locate features, bugs, or functions. If not found in index, auto-search via grep and update the index.
---

# YoloDo2.0 Project Index

**Last Updated**: 2026-03-27

## Usage Rules

1. **Check index first** → Use `references/` files for quick lookup
2. **Not found** → `grep_search` → **Update index** after finding
3. **After code changes** → Review and update relevant index entries

## Module Quick Reference

| Feature | Core Logic | UI Widget |
|---------|-----------|-----------|
| Prediction | `core/predict_handler/` (Package) | `ui/predict_widget/` (Package) |
| Data Processing | `core/data_handler/` (Package) | `ui/data_widget/` (Package) |
| Training | `core/train_handler.py` | `ui/train_widget.py` |
| Logging | `utils/logger.py` | - |
| Config | `config.py` | - |
| Inference Utils | `core/predict_handler/_inference_utils.py` | - |
| FFmpeg Writer | `core/predict_handler/_ffmpeg_writer.py` | - |
| IO Writer | `core/predict_handler/_io_worker.py` | - |
| Hardware Info | `utils/hardware_info.py` | - |
| Batch Optimizer | `utils/batch_optimizer.py` | - |
| Label Writer | `utils/label_writer.py` | - |
| File Utils | `utils/file_utils.py` | - |
| Constants | `utils/constants.py` | - |
| Output Dir Check | `ui/output_dir_check.py` | - |

## Hot Spots 🔥

| Feature | Location | Function |
|---------|----------|----------|
| Model Loading | `core/predict_handler/_manager.py` | `PredictManager.load_model` |
| Model Public API | `core/predict_handler/_manager.py` | `PredictManager.model_path/model_names/model` |
| Inference Loop | `core/predict_handler/_worker.py` | `PredictWorker.run` |
| Worker State Lock | `core/predict_handler/_worker.py` | `PredictWorker._state_lock` |
| YOLO Inference | `core/predict_handler/_inference_utils.py` | `run_inference` |
| Draw Detections | `core/predict_handler/_inference_utils.py` | `draw_detections` |
| Param Update | `core/predict_handler/_worker.py` | `PredictWorker.update_params` |
| Image Batch | `core/predict_handler/_image_batch.py` | `ImageBatchProcessor.process_all` |
| Image Batch Pause | `core/predict_handler/_image_batch.py` | `ImageBatchProcessor._pause_event (Event)` |
| Video Batch | `core/predict_handler/_video_batch.py` | `VideoBatchProcessor.process_all` |
| Video Batch Pause | `core/predict_handler/_video_batch.py` | `VideoBatchProcessor._pause_event (Event)` |
| Worker Cleanup | `core/predict_handler/_manager.py` | `PredictManager._on_worker_finished` |
| Thread Pool | `core/thread_pool.py` | `Worker (setAutoDelete=False)` |
| Output Finalize | `ui/predict_widget/_slots.py` | `SlotsMixin._finalize_output` (with `_output_finalized` guard) |
| Stop Wait Thread | `core/predict_handler/_manager.py` | `PredictManager.wait_for_stop(timeout_ms)` |
| Reset UI | `ui/predict_widget/_slots.py` | `_reset_ui_after_stop` → clears preview |
| Keyframe Dirs | `core/output_manager.py` | `OutputManager._ensure_keyframe_dirs` (lazy init) |
| Display Throttle | `ui/predict_widget/_slots.py` | `_update_display_interval` / `_on_frame_ready` (UI 端节流，后端全速推理) |
| Speed Selector | `ui/predict_widget/_viewport.py` | `_speed_combo` (0.5x/1x/2x/不限速) |
| FP16 Half Precision | `_inference_utils.py` / `_worker.py` / `_video_batch.py` | `model(half=True)` 所有推理调用 |
| Signal Throttle | `core/predict_handler/_worker.py` | 推理循环信号发射 ~60fps 节流，按需 `draw_detections()` |
| Frame Decoder | `core/predict_handler/_frame_decoder.py` | `FrameDecoder` 单线程 CPU 异步解码 (基础模式) |
| Multi-Thread Decoder | `core/predict_handler/_frame_decoder.py` | `MultiThreadDecoder` 多线程 CPU 解码 (最优模式) |
| NVDEC Decoder | `core/predict_handler/_frame_decoder.py` | `NvdecDecoder` GPU 硬件解码 via ffmpeg cuvid (高性能模式) |
| Decoder Factory | `core/predict_handler/_frame_decoder.py` | `create_decoder(mode)` 工厂函数 + `is_nvdec_available()` |
| Fast Detection Extract | `core/predict_handler/_frame_decoder.py` | `extract_detections_fast` 向量化批量 GPU→CPU 提取 |
| Async IO Writer | `core/predict_handler/_io_worker.py` | `IOWriter` 后台 I/O 线程 (关键帧/标签/视频帧异步写入) |
| On-Demand Draw | `core/predict_handler/_video_batch.py` | 批处理仅在录制/关键帧保存时才画框 |
| Window Close | `ui/predict_widget/_widget.py` | `PredictWidget.closeEvent` |
| Image Output Thread | `ui/predict_widget/_image_mode.py` | `ImageModeMixin._finalize_image_output` (背景线程保存) |
| Collapsible Height Fix | `ui/collapsible_box.py` | `CollapsibleGroupBox._on_animation_finished` (展开后解锁高度) |
| Dataset Scan | `core/data_handler/_scan.py` | `ScanMixin.scan_dataset` |
| Label Modify | `core/data_handler/_modify.py` | `ModifyMixin.modify_labels` |
| Label Validate | `core/data_handler/_validate.py` | `ValidateMixin.validate_labels` |
| Dataset Split | `core/data_handler/_split.py` | `SplitMixin.split_dataset` |
| Augment Dataset | `core/data_handler/_augment.py` | `AugmentMixin.augment_dataset` |
| Augment Recipes | `core/data_handler/_models.py` | `AugmentConfig.custom_recipes` / `build_fixed_recipes` |
| Augment Preview | `ui/data_widget/_tabs_augment.py` | `_refresh_preview` / `_try_auto_load_preview` |
| Augment Presets | `ui/data_widget/_tabs_augment.py` | `_apply_preset` / `PRESETS` dict |
| Recipe Management | `ui/data_widget/_tabs_augment.py` | `_on_add_recipe` / `_sync_recipe_display` |
| Write VOC XML | `utils/label_writer.py` | `write_voc_xml` |
| Write YOLO TXT | `utils/label_writer.py` | `write_yolo_txt` / `write_yolo_txt_from_xyxy` |
| File Discovery | `utils/file_utils.py` | `discover_files` |
| Unique Dir | `utils/file_utils.py` | `get_unique_dir` |
| Output Dir Check | `ui/output_dir_check.py` | `check_output_dir` (弹窗: 覆盖/新建/取消) |
| Three-Way Dialog | `ui/styled_message_box.py` | `StyledMessageBox.three_way_question` |
| Stats Card QSS | `ui/base_ui.py` | `#statsAccentBar[accent]` / `#statsCardValue[accent]` |
| Theme Switch | `ui/main_window.py` | `MainWindow._toggle_theme` |
| Focus Widgets | `ui/focus_widgets.py` | `FocusSpinBox` / `FocusDoubleSpinBox` / `FocusSlider` / `FocusComboBox` |
| Image Check Tab | `ui/data_widget/_tabs_image_check.py` | `_on_ic_integrity_finished` / `_on_ic_health_finished` |
| Image Check Dialogs | `ui/data_widget/image_check_result_dialog.py` | `ImageCheckResultDialog` / `HealthCheckResultDialog` |
| Hardware Detection | `utils/hardware_info.py` | `get_hardware_info()` → `HardwareInfo` dataclass |
| Batch Optimizer | `utils/batch_optimizer.py` | `compute_optimal_batch(hw, mode)` → `BatchConfig` (含 decode_mode) |
| Performance Mode | `utils/batch_optimizer.py` | `PerformanceMode.OPTIMAL` (multi解码) / `PerformanceMode.HIGH` (nvdec) |
| Batch Inference | `core/predict_handler/_inference_utils.py` | `run_batch_inference(model, frames, conf, iou)` |
| Batch 推理注意 | `core/predict_handler/_video_batch.py` | ⚠️ 必须用 `model()` 而非 predictor 拆分, 后者 batch>1 时只返回 1 result |
| Video Extract | `core/data_handler/_video_extract.py` | `VideoExtractMixin.extract_video_frames` (间隔/时间/场景变化) |
| Video Extract UI | `ui/data_widget/_tabs_video_extract.py` | 视频帧提取面板 (三种策略 + 场景变化检测) |
| Batch Read Frames | `core/predict_handler/_frame_decoder.py` | `FrameDecoder.read_batch(batch_size, timeout)` |
| FFmpeg Video Writer | `core/predict_handler/_ffmpeg_writer.py` | `FFmpegVideoWriter` (H.264, 5-10x 小文件) |
| Async IO Writer | `core/predict_handler/_io_worker.py` | `IOWriter` 后台 I/O 双线程 (关键帧+视频帧) |
| Perf Mode UI | `ui/predict_widget/_panel.py` | `_performance_combo` (最优性能/高性能) |

## Detailed Index

- [Module Map](references/module_map.md) - File-based classification
- [Function Index](references/function_index.md) - Feature-based classification
