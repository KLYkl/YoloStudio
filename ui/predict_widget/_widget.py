"""
_widget.py - PredictWidget: 预测推理模块主控件
============================================

职责:
    - 输入源选择 (图片/视频/摄像头/屏幕/RTSP)
    - 模型加载和参数配置
    - 实时预览和检测结果显示
    - 输出管理 (视频录制/关键帧保存/报告生成)
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QSplitter,
    QWidget,
)

from core.predict_handler import (
    InputSourceType,
    PredictManager,
    ImageBatchProcessor,
    VideoBatchProcessor,
)
from core.output_manager import OutputManager

from ui.predict_widget._panel import PanelMixin
from ui.predict_widget._viewport import ViewportMixin
from ui.predict_widget._slots import SlotsMixin
from ui.predict_widget._image_mode import ImageModeMixin
from ui.predict_widget._video_batch import VideoBatchMixin


class PredictWidget(
    PanelMixin,
    ViewportMixin,
    SlotsMixin,
    ImageModeMixin,
    VideoBatchMixin,
    QWidget,
):
    """
    预测模块主控件

    布局:
        - 左侧: 可折叠配置面板 (输入/模型/输出)
        - 右侧: 预览区域 + 底部状态栏

    信号:
        log_message(str): 发送到全局日志的消息
    """

    log_message = Signal(str)

    # 面板宽度
    PANEL_WIDTH = 260
    PANEL_MIN_WIDTH = 40

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # 核心管理器
        self._predict_manager = PredictManager(self)
        self._output_manager = OutputManager(self)
        self._image_processor = ImageBatchProcessor(self)
        self._video_batch_processor = VideoBatchProcessor(self)

        # 状态
        self._is_panel_collapsed = False
        self._is_recording = False
        self._is_stopping = False
        self._frame_count = 0
        self._object_count = 0
        self._current_fps = 0.0
        self._current_source_type: Optional[InputSourceType] = None

        # 图片模式状态
        self._is_image_mode: bool = False
        self._is_batch_processing: bool = False
        self._selected_image_paths: list[str] = []
        self._batch_thread = None

        # 视频批量模式状态
        self._is_video_batch_mode: bool = False
        self._video_batch_thread = None

        # 设备缓存
        self._cameras: list[dict] = []
        self._screens: list[dict] = []

        # FPS 计算
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps_display)
        self._fps_frame_count = 0

        # 视频帧率 (用于显示节流计算)
        self._video_fps: float = 30.0

        # 显示节流: 0 = 不限速(每帧刷新), >0 = 按间隔刷新
        self._display_interval: float = 0
        self._last_display_time: float = 0.0

        self._setup_ui()
        self._connect_signals()
        self._apply_styles()

        # 初始化图片模式 UI 状态
        self._on_source_type_changed(0)

        # 延迟设备扫描
        self._cameras_scanned = False
        self._screens_scanned = False

    def _setup_ui(self) -> None:
        """构建 UI 布局"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(6)
        self._splitter.setChildrenCollapsible(False)

        # 左侧: 配置面板 (PanelMixin)
        self._settings_panel = self._create_settings_panel()
        self._splitter.addWidget(self._settings_panel)

        # 右侧: 视窗区域 (ViewportMixin)
        viewport = self._create_viewport()
        self._splitter.addWidget(viewport)

        self._splitter.setSizes([self.PANEL_WIDTH, 800])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self._splitter)

    def _connect_signals(self) -> None:
        """连接信号与槽"""
        self._source_btn_group.idClicked.connect(self._on_source_type_changed)
        self._browse_source_btn.clicked.connect(self._on_browse_source)
        self._browse_model_btn.clicked.connect(self._on_browse_model)
        self._browse_output_btn.clicked.connect(self._on_browse_output)
        self._refresh_camera_btn.clicked.connect(self._scan_cameras)
        self._refresh_screen_btn.clicked.connect(self._scan_screens)
        self._rtsp_check.toggled.connect(self._on_rtsp_toggled)
        self._test_rtsp_btn.clicked.connect(self._on_test_rtsp)
        self._conf_slider.valueChanged.connect(self._on_conf_changed)
        self._iou_slider.valueChanged.connect(self._on_iou_changed)
        self._start_btn.clicked.connect(self._on_start_pause_clicked)
        self._stop_btn.clicked.connect(self._on_stop)

        # 播放控制
        self._progress_slider.sliderReleased.connect(self._on_progress_seek)
        self._speed_combo.currentIndexChanged.connect(self._on_speed_changed)

        self._predict_manager.frame_ready.connect(self._on_frame_ready)
        self._predict_manager.stats_updated.connect(self._on_stats_updated)
        self._predict_manager.error_occurred.connect(self._on_error)
        self._predict_manager.finished.connect(self._on_prediction_finished)
        self._predict_manager.state_changed.connect(self._on_playback_state_changed)
        self._predict_manager.progress_updated.connect(self._on_progress_updated)
        self._output_manager.file_saved.connect(self._on_file_saved)
        self._output_manager.error_occurred.connect(self._on_error)

        # 图片模式信号
        self._image_browser.prev_requested.connect(self._on_image_prev)
        self._image_browser.next_requested.connect(self._on_image_next)
        self._image_processor.progress_updated.connect(
            self._on_image_batch_progress, Qt.ConnectionType.QueuedConnection
        )
        self._image_processor.batch_finished.connect(
            self._on_image_batch_finished, Qt.ConnectionType.QueuedConnection
        )
        self._image_processor.error_occurred.connect(self._on_error)

        # 图片子选项和浏览按钮
        self._image_sub_group.idClicked.connect(self._on_image_sub_changed)
        self._browse_single_image_btn.clicked.connect(self._on_browse_single_image)
        self._browse_batch_folder_btn.clicked.connect(self._on_browse_batch_folder)

        # 视频子选项和浏览按钮
        self._video_sub_group.idClicked.connect(self._on_video_sub_changed)
        self._browse_batch_video_btn.clicked.connect(self._on_browse_batch_video_folder)

        # 视频批量处理信号
        self._video_batch_processor.video_started.connect(
            self._on_video_batch_started, Qt.ConnectionType.QueuedConnection
        )
        self._video_batch_processor.frame_progress.connect(
            self._on_video_frame_progress, Qt.ConnectionType.QueuedConnection
        )
        self._video_batch_processor.batch_progress.connect(
            self._on_video_batch_progress, Qt.ConnectionType.QueuedConnection
        )
        self._video_batch_processor.batch_finished.connect(
            self._on_video_batch_finished, Qt.ConnectionType.QueuedConnection
        )
        self._video_batch_processor.error_occurred.connect(self._on_error)

    def _apply_styles(self) -> None:
        """应用语义化样式"""
        pass

    def closeEvent(self, event) -> None:
        """窗口关闭时清理所有线程"""
        # 停止 PredictManager 推理线程
        if self._predict_manager.is_running:
            self._predict_manager.stop()
            self._predict_manager.wait_for_stop(3000)

        # 停止图片批量处理线程
        if self._is_batch_processing:
            self._image_processor.stop()
            if self._batch_thread and self._batch_thread.isRunning():
                self._batch_thread.wait(3000)

        # 停止视频批量处理线程
        if self._video_batch_processor.is_running:
            self._video_batch_processor.stop()
            if self._video_batch_thread and self._video_batch_thread.isRunning():
                self._video_batch_thread.wait(3000)

        # 停止 FPS 计时器
        self._fps_timer.stop()

        super().closeEvent(event)
