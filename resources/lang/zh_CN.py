"""
zh_CN.py - 简体中文翻译
"""

TRANSLATIONS = {
    # ============================================================
    # main.py
    # ============================================================
    "app_name": "YoloStudio",
    "starting_app": "正在启动 YoloStudio...",
    "uncaught_exception": "未捕获的异常:\n{tb}",
    "exception_in_worker": "异常发生在工作线程中，已记录日志（跳过弹窗）",
    "program_error": "程序错误",
    "program_error_msg": "程序遇到了一个未预期的错误，请联系开发者。",

    # ============================================================
    # main_window.py
    # ============================================================
    "app_title": "YoloStudio - YOLO 可视化训练工具",
    "tab_data": "📁 数据准备",
    "tab_train": "🚀 模型训练",
    "tab_predict": "🎯 预测推理",

    # GlobalLogPanel
    "system_log": "📋 系统日志",
    "clear": "清空",
    "expand": "▲ 展开",
    "collapse": "▼ 收起",
    "log_placeholder": "运行日志将显示在这里...",

    # 主题
    "switch_to_light": "切换到亮色主题",
    "switch_to_dark": "切换到暗色主题",
    "switched_to_dark": "已切换到暗色主题",
    "switched_to_light": "已切换到亮色主题",

    # 语言
    "switch_language": "切换语言",
    "language_restart_hint": "语言已切换，重启应用后生效。",

    # 关闭
    "app_started": "YoloStudio 启动完成",
    "config_path": "配置文件路径: {path}",
    "app_closing": "YoloStudio 正在关闭...",

    # ============================================================
    # predict_widget - 面板
    # ============================================================
    "section_input_source": "输入源",
    "section_model": "模型",
    "section_output": "输出",

    "source_image": "图片",
    "source_video": "视频",
    "source_camera": "摄像头",
    "source_screen": "屏幕",

    "single_image": "单张图片",
    "single_video": "单个视频",
    "batch_process": "批量处理",

    "ph_select_image": "选择图片文件...",
    "ph_select_image_folder": "选择图片文件夹...",
    "ph_select_video": "选择视频文件...",
    "ph_select_video_folder": "选择视频文件夹...",
    "ph_select_model": "选择模型 (.pt)...",
    "ph_output_dir": "输出目录...",

    "rtsp_camera": "RTSP 网络摄像头",
    "test": "测试",

    "confidence": "置信度:",
    "performance": "性能:",
    "perf_optimal": "最优性能",
    "perf_high": "高性能",
    "class_filter": "类别:",
    "filter_all": "全部",
    "threshold": "阈值:",

    "save_result_image": "保存结果图片",
    "save_original": "保存原图副本",
    "gen_label_files": "生成标签文件 (TXT+XML)",
    "gen_report": "生成报告 (.json)",
    "filter_conditions": "过滤条件:",
    "filter_save_all": "全部保存",
    "filter_detected_only": "只保存有检测结果",
    "filter_empty_only": "只保存无检测结果",
    "filter_high_conf_only": "只保存高置信度",

    "save_result_video": "保存结果视频",
    "save_keyframe_annotated": "保存关键帧（带框）",
    "save_keyframe_raw": "保存关键帧（原图）",
    "save_high_conf_frames": "只保存高置信度帧",

    # ============================================================
    # predict_widget - 视窗/状态栏
    # ============================================================
    "fps_default": "FPS: --",
    "processed_frames": "已处理: {count} 帧",
    "detections_count": "检测: {count} 个",
    "model_not_loaded": "模型: 未加载",
    "model_label": "模型: {name}",
    "btn_start": "▶ 开始",
    "btn_stop": "⏹ 停止",
    "btn_processing": "⏳ 处理中",
    "collapse_panel": "折叠设置面板",
    "expand_panel": "展开设置面板",
    "speed_tooltip": "播放速度 (0=全速推理)",
    "speed_unlimited": "🚀 不限速",

    # ============================================================
    # predict_widget - 槽函数/交互
    # ============================================================
    "warning": "警告",
    "error": "错误",
    "success": "成功",
    "fail": "失败",

    "dialog_select_image": "选择图片",
    "dialog_select_image_folder": "选择图片文件夹",
    "dialog_select_video": "选择视频",
    "dialog_select_video_folder": "选择视频文件夹",
    "dialog_select_model": "选择模型",
    "dialog_select_output_dir": "选择输出目录",

    "warn_select_valid_model": "请选择有效的模型文件",
    "warn_select_valid_video": "请选择有效的视频",
    "warn_input_rtsp": "请输入 RTSP 地址",
    "warn_select_camera": "请选择摄像头",
    "warn_select_screen": "请选择屏幕",
    "warn_select_model": "请选择模型文件",
    "warn_select_image_file": "请选择有效的图片文件",
    "warn_select_image_folder": "请选择图片文件夹",
    "warn_select_video_folder": "请选择视频文件夹",
    "warn_select_output_dir": "请选择输出目录",
    "warn_no_images_found": "未找到图片文件",
    "warn_no_videos_found": "未找到视频文件",
    "warn_batch_still_running": "上一次批量处理尚未完成",
    "warn_batch_thread_timeout": "[警告] 批量处理线程超时未结束",
    "warn_video_batch_thread_timeout": "[警告] 视频批量处理线程超时未结束",

    "err_model_load_failed": "模型加载失败",
    "err_start_predict_failed": "启动预测失败",
    "error_prefix": "[错误] {msg}",

    "loading_model": "正在加载模型: {path}",
    "model_loaded": "模型加载成功",
    "start_predict": "开始预测: {source}",
    "predict_stopped": "预测已停止",
    "predict_complete": "预测完成",
    "file_saved": "文件已保存: {path}",
    "video_saved": "视频已保存: {path}",
    "report_generated": "报告已生成: {path}",

    "testing_rtsp": "正在测试 RTSP: {url}",
    "rtsp_connect_success": "RTSP 连接成功!",
    "rtsp_test_passed": "RTSP 测试通过",
    "rtsp_connect_failed": "RTSP 连接失败: {error}",
    "rtsp_test_failed": "RTSP 测试失败: {error}",
    "camera_scan_done": "摄像头扫描完成: {count} 个设备",
    "screen_scan_done": "屏幕扫描完成: {count} 个显示器",

    # ============================================================
    # predict_widget - 视频批量处理
    # ============================================================
    "frame_progress_init": "帧: 0/0 (0%)",
    "frame_progress": "帧: {current}/{total} ({percent}%)",
    "video_batch_current": "视频 [{index}/{total}]: {name}",
    "start_processing_video": "开始处理视频: {name}",
    "start_batch_processing": "开始批量处理 {count} 个视频",
    "batch_done": "批量处理完成",
    "batch_done_report": "批量处理完成，汇总报告: {path}",
    "processed_videos": "已处理: {count} 个视频",
    "batch_complete_summary": "已处理 {videos} 个视频\n总检测数: {detections}\n保存关键帧: {keyframes}",
    "perf_mode_info": "性能模式: {mode} | batch_size={batch}, 解码={decode}",
    "image_batch_stopped": "图片批量处理已停止",
    "video_batch_stopped": "视频批量处理已停止",
    "processing_aborted": "处理已中止",

    # ============================================================
    # predict_widget - 图片模式
    # ============================================================
    "processing": "正在处理...",
    "processing_done": "处理完成",
    "image_batch_done": "图片批量处理完成",
    "image_output_saved": "结果已保存: {path}",
    "perf_mode_info_image": "性能模式: {mode} | batch_size={batch}",
}
