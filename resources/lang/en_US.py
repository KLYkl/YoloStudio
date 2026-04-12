"""
en_US.py - English translations
"""

TRANSLATIONS = {
    # ============================================================
    # main.py
    # ============================================================
    "app_name": "YoloStudio",
    "starting_app": "Starting YoloStudio...",
    "uncaught_exception": "Uncaught exception:\n{tb}",
    "exception_in_worker": "Exception in worker thread, logged (skip dialog)",
    "program_error": "Program Error",
    "program_error_msg": "An unexpected error occurred. Please contact the developer.",

    # ============================================================
    # main_window.py
    # ============================================================
    "app_title": "YoloStudio - YOLO Visual Training Tool",
    "tab_data": "📁 Data",
    "tab_train": "🚀 Training",
    "tab_predict": "🎯 Predict",

    # GlobalLogPanel
    "system_log": "📋 System Log",
    "clear": "Clear",
    "expand": "▲ Expand",
    "collapse": "▼ Collapse",
    "log_placeholder": "Logs will appear here...",

    # Theme
    "switch_to_light": "Switch to light theme",
    "switch_to_dark": "Switch to dark theme",
    "switched_to_dark": "Switched to dark theme",
    "switched_to_light": "Switched to light theme",

    # Language
    "switch_language": "Switch Language",
    "warn_switch_lang_busy": "Please stop the current task before switching language.",

    # Startup / close
    "app_started": "YoloStudio started",
    "config_path": "Config path: {path}",
    "app_closing": "YoloStudio is shutting down...",

    # ============================================================
    # predict_widget - Panel
    # ============================================================
    "section_input_source": "Input Source",
    "section_model": "Model",
    "section_output": "Output",

    "source_image": "Image",
    "source_video": "Video",
    "source_camera": "Camera",
    "source_screen": "Screen",

    "single_image": "Single Image",
    "single_video": "Single Video",
    "batch_process": "Batch",

    "ph_select_image": "Select image file...",
    "ph_select_image_folder": "Select image folder...",
    "ph_select_video": "Select video file...",
    "ph_select_video_folder": "Select video folder...",
    "ph_select_model": "Select model (.pt)...",
    "ph_output_dir": "Output directory...",

    "rtsp_camera": "RTSP Network Camera",
    "test": "Test",

    "confidence": "Conf:",
    "performance": "Perf:",
    "perf_optimal": "Optimal",
    "perf_high": "High Perf",
    "class_filter": "Class:",
    "filter_all": "All",
    "threshold": "Thresh:",

    "save_result_image": "Save result images",
    "save_original": "Save original copies",
    "gen_label_files": "Generate labels (TXT+XML)",
    "gen_report": "Generate report (.json)",
    "filter_conditions": "Filter:",
    "filter_save_all": "Save all",
    "filter_detected_only": "Detected only",
    "filter_empty_only": "Empty only",
    "filter_high_conf_only": "High confidence only",

    "save_result_video": "Save result video",
    "save_keyframe_annotated": "Save keyframes (annotated)",
    "save_keyframe_raw": "Save keyframes (raw)",
    "save_high_conf_frames": "High confidence only",

    # ============================================================
    # predict_widget - Viewport / status bar
    # ============================================================
    "fps_default": "FPS: --",
    "processed_frames": "Processed: {count} frames",
    "detections_count": "Detections: {count}",
    "model_not_loaded": "Model: not loaded",
    "model_label": "Model: {name}",
    "btn_start": "▶ Start",
    "btn_stop": "⏹ Stop",
    "btn_processing": "⏳ Processing",
    "collapse_panel": "Collapse settings panel",
    "expand_panel": "Expand settings panel",
    "speed_tooltip": "Playback speed (0=full speed)",
    "speed_unlimited": "🚀 No limit",

    # ============================================================
    # predict_widget - Slots / interaction
    # ============================================================
    "warning": "Warning",
    "error": "Error",
    "success": "Success",
    "fail": "Fail",

    "dialog_select_image": "Select Image",
    "dialog_select_image_folder": "Select Image Folder",
    "dialog_select_video": "Select Video",
    "dialog_select_video_folder": "Select Video Folder",
    "dialog_select_model": "Select Model",
    "dialog_select_output_dir": "Select Output Directory",

    "warn_select_valid_model": "Please select a valid model file",
    "warn_select_valid_video": "Please select a valid video",
    "warn_input_rtsp": "Please enter an RTSP address",
    "warn_select_camera": "Please select a camera",
    "warn_select_screen": "Please select a screen",
    "warn_select_model": "Please select a model file",
    "warn_select_image_file": "Please select a valid image file",
    "warn_select_image_folder": "Please select an image folder",
    "warn_select_video_folder": "Please select a video folder",
    "warn_select_output_dir": "Please select an output directory",
    "warn_no_images_found": "No images found",
    "warn_no_videos_found": "No videos found",
    "warn_batch_still_running": "Previous batch is still running",
    "warn_batch_thread_timeout": "[Warning] Batch thread timed out",
    "warn_video_batch_thread_timeout": "[Warning] Video batch thread timed out",

    "err_model_load_failed": "Model loading failed",
    "err_start_predict_failed": "Failed to start prediction",
    "error_prefix": "[Error] {msg}",

    "loading_model": "Loading model: {path}",
    "model_loaded": "Model loaded successfully",
    "start_predict": "Start prediction: {source}",
    "predict_stopped": "Prediction stopped",
    "predict_complete": "Prediction complete",
    "file_saved": "File saved: {path}",
    "video_saved": "Video saved: {path}",
    "report_generated": "Report generated: {path}",

    "testing_rtsp": "Testing RTSP: {url}",
    "rtsp_connect_success": "RTSP connection successful!",
    "rtsp_test_passed": "RTSP test passed",
    "rtsp_connect_failed": "RTSP connection failed: {error}",
    "rtsp_test_failed": "RTSP test failed: {error}",
    "camera_scan_done": "Camera scan complete: {count} devices",
    "screen_scan_done": "Screen scan complete: {count} displays",

    # ============================================================
    # predict_widget - Video batch
    # ============================================================
    "frame_progress_init": "Frame: 0/0 (0%)",
    "frame_progress": "Frame: {current}/{total} ({percent}%)",
    "video_batch_current": "Video [{index}/{total}]: {name}",
    "start_processing_video": "Processing video: {name}",
    "start_batch_processing": "Start batch processing {count} videos",
    "batch_done": "Batch processing complete",
    "batch_done_report": "Batch complete, report: {path}",
    "processed_videos": "Processed: {count} videos",
    "batch_complete_summary": "Processed {videos} videos\nTotal detections: {detections}\nKeyframes saved: {keyframes}",
    "perf_mode_info": "Performance: {mode} | batch_size={batch}, decode={decode}",
    "image_batch_stopped": "Image batch stopped",
    "video_batch_stopped": "Video batch stopped",
    "processing_aborted": "Processing aborted",

    # ============================================================
    # predict_widget - Image mode
    # ============================================================
    "processing": "Processing...",
    "processing_done": "Processing complete",
    "image_batch_done": "Image batch processing complete",
    "image_output_saved": "Results saved: {path}",
    "perf_mode_info_image": "Performance: {mode} | batch_size={batch}",
}
