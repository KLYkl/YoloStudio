"""
predict_widget.py - 预测推理模块 UI
============================================

职责:
    - 输入源选择 (图片/视频/摄像头/屏幕/RTSP)
    - 模型加载和参数配置
    - 实时预览和检测结果显示
    - 输出管理 (视频录制/关键帧保存/报告生成)

架构要点:
    - 左侧可折叠配置面板 + 右侧最大化预览区域
    - 所有推理在子线程运行，不阻塞 UI
    - 通过 Signal/Slot 与 PredictManager 通信
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QStackedWidget,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.camera_scanner import DeviceScanner
from core.output_manager import OutputManager
from core.predict_handler import (
    InputSourceType, 
    PredictManager, 
    ImageBatchProcessor,
    VideoBatchProcessor,
    SaveCondition
)
from ui.base_ui import set_button_class
from ui.focus_widgets import FocusSlider
from ui.image_result_browser import ImageResultBrowser, ImageProgressBar
from ui.predict_preview import PreviewCanvas


class PredictWidget(QWidget):
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
        self._is_stopping = False  # 防止停止过程中状态信号干扰
        self._frame_count = 0
        self._object_count = 0
        self._current_fps = 0.0
        self._current_source_type: Optional[InputSourceType] = None
        
        # 图片模式状态
        self._is_image_mode: bool = False
        self._is_batch_processing: bool = False
        self._selected_image_paths: list[str] = []  # 多选图片时的路径列表
        self._batch_thread = None  # 批量处理线程
        
        # 视频批量模式状态
        self._is_video_batch_mode: bool = False
        self._video_batch_thread = None  # 视频批量处理线程
        
        # 设备缓存
        self._cameras: list[dict] = []
        self._screens: list[dict] = []
        
        # FPS 计算
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps_display)
        self._fps_frame_count = 0
        
        self._setup_ui()
        self._connect_signals()
        self._apply_styles()
        
        # 初始化图片模式 UI 状态 (默认选中图片)
        self._on_source_type_changed(0)
        
        # 延迟设备扫描 - 分别追踪摄像头和屏幕的扫描状态
        self._cameras_scanned = False
        self._screens_scanned = False
    
    def _setup_ui(self) -> None:
        """构建 UI 布局"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(0)
        
        # 使用 QSplitter 替代固定宽度，允许用户拖拽调整面板大小
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(6)
        self._splitter.setChildrenCollapsible(False)
        
        # 左侧: 配置面板
        self._settings_panel = self._create_settings_panel()
        self._splitter.addWidget(self._settings_panel)
        
        # 右侧: 视窗区域
        viewport = self._create_viewport()
        self._splitter.addWidget(viewport)
        
        # 初始比例: 面板 260px, 视窗区域获取剩余空间
        self._splitter.setSizes([self.PANEL_WIDTH, 800])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(self._splitter)
    
    def _create_settings_panel(self) -> QWidget:
        """创建左侧配置面板 (带滚动条)"""
        # 外层容器
        panel = QFrame()
        panel.setObjectName("settingsPanel")
        panel.setMinimumWidth(200)
        panel.setMaximumWidth(400)
        
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        
        # 滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        # 滚动内容
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(10)
        
        # 输入源区域
        layout.addWidget(self._create_section_label("输入源"))
        self._create_source_section_compact(layout)
        
        # 在区域之间添加分隔线
        layout.addSpacing(8)
        layout.addWidget(self._create_separator())
        layout.addSpacing(8)
        
        # 模型区域
        layout.addWidget(self._create_section_label("模型"))
        self._create_model_section_compact(layout)
        
        layout.addSpacing(8)
        layout.addWidget(self._create_separator())
        layout.addSpacing(8)
        
        # 输出区域
        layout.addWidget(self._create_section_label("输出"))
        self._create_output_section_compact(layout)
        
        # 底部空白
        layout.addStretch(1)
        
        scroll_area.setWidget(scroll_content)
        panel_layout.addWidget(scroll_area)
        
        return panel
    
    def _create_section_label(self, text: str) -> QLabel:
        """创建区域标题"""
        label = QLabel(text)
        label.setObjectName("accentLabel")
        return label
    
    def _create_separator(self) -> QFrame:
        """创建分隔线"""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        return line
    
    def _create_source_section_compact(self, parent_layout: QVBoxLayout) -> None:
        """创建紧凑型输入源区域"""
        # 单选按钮 2x2 网格布局
        type_layout = QGridLayout()
        type_layout.setSpacing(10)
        type_layout.setContentsMargins(0, 6, 0, 6)
        
        self._radio_image = QRadioButton("图片")
        self._radio_video = QRadioButton("视频")
        self._radio_camera = QRadioButton("摄像头")
        self._radio_screen = QRadioButton("屏幕")
        
        self._radio_image.setChecked(True)
        
        self._source_btn_group = QButtonGroup(self)
        self._source_btn_group.addButton(self._radio_image, 0)
        self._source_btn_group.addButton(self._radio_video, 1)
        self._source_btn_group.addButton(self._radio_camera, 2)
        self._source_btn_group.addButton(self._radio_screen, 3)
        
        type_layout.addWidget(self._radio_image, 0, 0)
        type_layout.addWidget(self._radio_video, 0, 1)
        type_layout.addWidget(self._radio_camera, 1, 0)
        type_layout.addWidget(self._radio_screen, 1, 1)
        
        parent_layout.addLayout(type_layout)
        
        # === 图片模式专用区域 (单张/批量选项) ===
        self._image_mode_container = QWidget()
        image_mode_layout = QVBoxLayout(self._image_mode_container)
        image_mode_layout.setContentsMargins(0, 8, 0, 0)
        image_mode_layout.setSpacing(8)
        
        # 子选项: 单张 / 批量
        image_sub_layout = QHBoxLayout()
        image_sub_layout.setSpacing(16)
        self._radio_single_image = QRadioButton("单张图片")
        self._radio_batch_image = QRadioButton("批量处理")
        self._radio_single_image.setChecked(True)
        
        self._image_sub_group = QButtonGroup(self)
        self._image_sub_group.addButton(self._radio_single_image, 0)
        self._image_sub_group.addButton(self._radio_batch_image, 1)
        
        image_sub_layout.addWidget(self._radio_single_image)
        image_sub_layout.addWidget(self._radio_batch_image)
        image_sub_layout.addStretch()
        image_mode_layout.addLayout(image_sub_layout)
        
        # 单张图片输入框
        self._single_image_container = QWidget()
        single_layout = QHBoxLayout(self._single_image_container)
        single_layout.setContentsMargins(0, 4, 0, 0)
        single_layout.setSpacing(6)
        
        self._single_image_edit = QLineEdit()
        self._single_image_edit.setPlaceholderText("选择图片文件...")
        self._single_image_edit.setFixedHeight(32)
        self._browse_single_image_btn = QToolButton()
        self._browse_single_image_btn.setText("...")
        self._browse_single_image_btn.setFixedSize(32, 32)
        
        single_layout.addWidget(self._single_image_edit)
        single_layout.addWidget(self._browse_single_image_btn)
        image_mode_layout.addWidget(self._single_image_container)
        
        # 批量处理输入框
        self._batch_image_container = QWidget()
        batch_layout = QHBoxLayout(self._batch_image_container)
        batch_layout.setContentsMargins(0, 4, 0, 0)
        batch_layout.setSpacing(6)
        
        self._batch_folder_edit = QLineEdit()
        self._batch_folder_edit.setPlaceholderText("选择图片文件夹...")
        self._batch_folder_edit.setFixedHeight(32)
        self._browse_batch_folder_btn = QToolButton()
        self._browse_batch_folder_btn.setText("...")
        self._browse_batch_folder_btn.setFixedSize(32, 32)
        
        batch_layout.addWidget(self._batch_folder_edit)
        batch_layout.addWidget(self._browse_batch_folder_btn)
        image_mode_layout.addWidget(self._batch_image_container)
        self._batch_image_container.setVisible(False)  # 默认隐藏
        
        parent_layout.addWidget(self._image_mode_container)
        
        # === 视频模式专用区域 (单个/批量选项) ===
        self._video_mode_container = QWidget()
        video_mode_layout = QVBoxLayout(self._video_mode_container)
        video_mode_layout.setContentsMargins(0, 8, 0, 0)
        video_mode_layout.setSpacing(8)
        
        # 子选项: 单个视频 / 批量处理
        video_sub_layout = QHBoxLayout()
        video_sub_layout.setSpacing(16)
        self._radio_single_video = QRadioButton("单个视频")
        self._radio_batch_video = QRadioButton("批量处理")
        self._radio_single_video.setChecked(True)
        
        self._video_sub_group = QButtonGroup(self)
        self._video_sub_group.addButton(self._radio_single_video, 0)
        self._video_sub_group.addButton(self._radio_batch_video, 1)
        
        video_sub_layout.addWidget(self._radio_single_video)
        video_sub_layout.addWidget(self._radio_batch_video)
        video_sub_layout.addStretch()
        video_mode_layout.addLayout(video_sub_layout)
        
        # 单个视频输入框
        self._single_video_container = QWidget()
        single_video_layout = QHBoxLayout(self._single_video_container)
        single_video_layout.setContentsMargins(0, 4, 0, 0)
        single_video_layout.setSpacing(6)
        
        self._source_path_edit = QLineEdit()
        self._source_path_edit.setPlaceholderText("选择视频文件...")
        self._source_path_edit.setFixedHeight(32)
        self._browse_source_btn = QToolButton()
        self._browse_source_btn.setText("...")
        self._browse_source_btn.setFixedSize(32, 32)
        
        single_video_layout.addWidget(self._source_path_edit)
        single_video_layout.addWidget(self._browse_source_btn)
        video_mode_layout.addWidget(self._single_video_container)
        
        # 批量视频输入框
        self._batch_video_container = QWidget()
        batch_video_layout = QHBoxLayout(self._batch_video_container)
        batch_video_layout.setContentsMargins(0, 4, 0, 0)
        batch_video_layout.setSpacing(6)
        
        self._batch_video_folder_edit = QLineEdit()
        self._batch_video_folder_edit.setPlaceholderText("选择视频文件夹...")
        self._batch_video_folder_edit.setFixedHeight(32)
        self._browse_batch_video_btn = QToolButton()
        self._browse_batch_video_btn.setText("...")
        self._browse_batch_video_btn.setFixedSize(32, 32)
        
        batch_video_layout.addWidget(self._batch_video_folder_edit)
        batch_video_layout.addWidget(self._browse_batch_video_btn)
        video_mode_layout.addWidget(self._batch_video_container)
        self._batch_video_container.setVisible(False)  # 默认隐藏
        
        self._video_mode_container.setVisible(False)  # 默认图片模式，视频区域隐藏
        parent_layout.addWidget(self._video_mode_container)
        
        # 摄像头选择
        self._camera_container = QWidget()
        camera_layout = QVBoxLayout(self._camera_container)
        camera_layout.setContentsMargins(0, 8, 0, 0)
        camera_layout.setSpacing(8)
        
        cam_row = QHBoxLayout()
        cam_row.setSpacing(4)
        self._camera_combo = QComboBox()
        self._camera_combo.setFixedHeight(32)
        self._refresh_camera_btn = QToolButton()
        self._refresh_camera_btn.setText("🔄")
        self._refresh_camera_btn.setFixedSize(34, 32)
        
        cam_row.addWidget(self._camera_combo)
        cam_row.addWidget(self._refresh_camera_btn)
        camera_layout.addLayout(cam_row)
        
        # RTSP 输入
        self._rtsp_check = QCheckBox("RTSP 网络摄像头")
        camera_layout.addWidget(self._rtsp_check)
        
        rtsp_row = QHBoxLayout()
        rtsp_row.setSpacing(2)
        self._rtsp_edit = QLineEdit()
        self._rtsp_edit.setPlaceholderText("rtsp://ip:port/stream")
        self._rtsp_edit.setFixedHeight(32)
        self._rtsp_edit.setEnabled(False)
        self._test_rtsp_btn = QToolButton()
        self._test_rtsp_btn.setText("测试")
        self._test_rtsp_btn.setEnabled(False)
        self._test_rtsp_btn.setFixedSize(42, 32)
        
        rtsp_row.addWidget(self._rtsp_edit)
        rtsp_row.addWidget(self._test_rtsp_btn)
        camera_layout.addLayout(rtsp_row)
        
        parent_layout.addWidget(self._camera_container)
        self._camera_container.setVisible(False)
        
        # 屏幕选择
        self._screen_container = QWidget()
        screen_layout = QHBoxLayout(self._screen_container)
        screen_layout.setContentsMargins(0, 8, 0, 0)
        screen_layout.setSpacing(6)
        
        self._screen_combo = QComboBox()
        self._screen_combo.setFixedHeight(32)
        self._refresh_screen_btn = QToolButton()
        self._refresh_screen_btn.setText("🔄")
        self._refresh_screen_btn.setFixedSize(34, 32)
        
        screen_layout.addWidget(self._screen_combo)
        screen_layout.addWidget(self._refresh_screen_btn)
        
        parent_layout.addWidget(self._screen_container)
        self._screen_container.setVisible(False)
    
    def _create_model_section_compact(self, parent_layout: QVBoxLayout) -> None:
        """创建紧凑型模型区域"""
        # 模型路径
        model_row = QHBoxLayout()
        model_row.setSpacing(4)
        self._model_path_edit = QLineEdit()
        self._model_path_edit.setPlaceholderText("选择模型 (.pt)...")
        self._model_path_edit.setFixedHeight(32)
        self._browse_model_btn = QToolButton()
        self._browse_model_btn.setText("...")
        self._browse_model_btn.setFixedSize(32, 32)
        
        model_row.addWidget(self._model_path_edit)
        model_row.addWidget(self._browse_model_btn)
        parent_layout.addLayout(model_row)
        
        # 置信度滑块
        conf_row = QHBoxLayout()
        conf_row.setSpacing(4)
        conf_label = QLabel("置信度:")
        conf_label.setFixedWidth(50)
        self._conf_slider = FocusSlider(Qt.Orientation.Horizontal)
        self._conf_slider.setRange(0, 100)
        self._conf_slider.setValue(50)
        # self._conf_slider.setFixedHeight(20)
        self._conf_label = QLabel("0.50")
        self._conf_label.setFixedWidth(35)
        self._conf_label.setObjectName("accentLabel")
        
        conf_row.addWidget(conf_label)
        conf_row.addWidget(self._conf_slider)
        conf_row.addWidget(self._conf_label)
        parent_layout.addLayout(conf_row)
        
        # IOU 滑块
        iou_row = QHBoxLayout()
        iou_row.setSpacing(4)
        iou_label = QLabel("IOU:")
        iou_label.setFixedWidth(50)
        self._iou_slider = FocusSlider(Qt.Orientation.Horizontal)
        self._iou_slider.setRange(0, 100)
        self._iou_slider.setValue(45)
        # self._iou_slider.setFixedHeight(20)
        self._iou_label = QLabel("0.45")
        self._iou_label.setFixedWidth(35)
        self._iou_label.setObjectName("accentLabel")
        
        iou_row.addWidget(iou_label)
        iou_row.addWidget(self._iou_slider)
        iou_row.addWidget(self._iou_label)
        parent_layout.addLayout(iou_row)
        
        # 类别过滤
        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)
        filter_label = QLabel("类别:")
        filter_label.setFixedWidth(50)
        self._class_filter_combo = QComboBox()
        self._class_filter_combo.addItem("全部")
        self._class_filter_combo.setFixedHeight(32)
        
        filter_row.addWidget(filter_label)
        filter_row.addWidget(self._class_filter_combo)
        parent_layout.addLayout(filter_row)
    
    def _create_output_section_compact(self, parent_layout: QVBoxLayout) -> None:
        """创建紧凑型输出区域"""
        # === 图片模式输出选项 (默认显示) ===
        self._image_output_container = QWidget()
        image_output_layout = QVBoxLayout(self._image_output_container)
        image_output_layout.setContentsMargins(0, 0, 0, 0)
        image_output_layout.setSpacing(6)
        
        self._save_result_image_check = QCheckBox("保存结果图片")
        self._save_original_check = QCheckBox("保存原图副本")
        self._save_labels_check = QCheckBox("生成标签文件 (TXT+XML)")
        self._save_image_report_check = QCheckBox("生成报告 (.json)")
        
        for cb in [self._save_result_image_check, self._save_original_check, 
                   self._save_labels_check, self._save_image_report_check]:
            image_output_layout.addWidget(cb)
        
        # 图片模式过滤条件
        filter_group = QWidget()
        filter_layout = QVBoxLayout(filter_group)
        filter_layout.setContentsMargins(0, 4, 0, 0)
        filter_layout.setSpacing(4)
        
        filter_title = QLabel("过滤条件:")
        filter_title.setObjectName("mutedLabel")
        filter_layout.addWidget(filter_title)
        
        self._filter_all_radio = QRadioButton("全部保存")
        self._filter_detected_radio = QRadioButton("只保存有检测结果")
        self._filter_empty_radio = QRadioButton("只保存无检测结果")
        self._filter_high_conf_radio = QRadioButton("只保存高置信度")
        self._filter_all_radio.setChecked(True)
        
        self._filter_group = QButtonGroup(self)
        self._filter_group.addButton(self._filter_all_radio, 0)
        self._filter_group.addButton(self._filter_detected_radio, 1)
        self._filter_group.addButton(self._filter_empty_radio, 2)
        self._filter_group.addButton(self._filter_high_conf_radio, 3)
        
        for rb in [self._filter_all_radio, self._filter_detected_radio, 
                   self._filter_empty_radio, self._filter_high_conf_radio]:
            filter_layout.addWidget(rb)
        
        # 图片模式高置信度阈值
        img_threshold_row = QHBoxLayout()
        img_threshold_row.setSpacing(4)
        img_threshold_row.setContentsMargins(16, 0, 0, 0)  # 缩进
        self._img_threshold_slider = FocusSlider(Qt.Orientation.Horizontal)
        self._img_threshold_slider.setRange(50, 100)
        self._img_threshold_slider.setValue(70)
        self._img_threshold_slider.setEnabled(False)
        self._img_threshold_label = QLabel("0.70")
        self._img_threshold_label.setFixedWidth(35)
        
        img_threshold_row.addWidget(self._img_threshold_slider)
        img_threshold_row.addWidget(self._img_threshold_label)
        filter_layout.addLayout(img_threshold_row)
        
        image_output_layout.addWidget(filter_group)
        parent_layout.addWidget(self._image_output_container)
        
        # === 视频/其他模式输出选项 (默认隐藏) ===
        self._video_output_container = QWidget()
        video_output_layout = QVBoxLayout(self._video_output_container)
        video_output_layout.setContentsMargins(0, 0, 0, 0)
        video_output_layout.setSpacing(6)
        
        self._save_video_check = QCheckBox("保存结果视频")
        self._save_keyframe_annotated_check = QCheckBox("保存关键帧（带框）")
        self._save_keyframe_raw_check = QCheckBox("保存关键帧（原图）")
        self._save_report_check = QCheckBox("生成报告 (.json)")
        self._high_conf_check = QCheckBox("只保存高置信度帧")
        
        for cb in [self._save_video_check, self._save_keyframe_annotated_check,
                   self._save_keyframe_raw_check, self._save_report_check, self._high_conf_check]:
            video_output_layout.addWidget(cb)
        
        # 视频模式阈值滑块
        threshold_row = QHBoxLayout()
        threshold_row.setSpacing(4)
        threshold_label = QLabel("阈值:")
        threshold_label.setFixedWidth(50)
        threshold_label.setObjectName("mutedLabel")
        self._threshold_slider = FocusSlider(Qt.Orientation.Horizontal)
        self._threshold_slider.setRange(50, 100)
        self._threshold_slider.setValue(70)
        self._threshold_slider.setEnabled(False)
        self._threshold_label = QLabel("0.70")
        self._threshold_label.setFixedWidth(35)
        self._threshold_label.setObjectName("mutedLabel")
        
        threshold_row.addWidget(threshold_label)
        threshold_row.addWidget(self._threshold_slider)
        threshold_row.addWidget(self._threshold_label)
        video_output_layout.addLayout(threshold_row)
        
        self._video_output_container.setVisible(False)  # 默认隐藏
        parent_layout.addWidget(self._video_output_container)
        
        # 信号连接
        self._high_conf_check.toggled.connect(self._on_high_conf_toggled)
        self._threshold_slider.valueChanged.connect(self._on_threshold_changed)
        self._filter_high_conf_radio.toggled.connect(self._on_img_high_conf_toggled)
        self._img_threshold_slider.valueChanged.connect(self._on_img_threshold_changed)
        
        # 输出目录 (共用)
        output_row = QHBoxLayout()
        output_row.setSpacing(2)
        self._output_dir_edit = QLineEdit()
        self._output_dir_edit.setPlaceholderText("输出目录...")
        self._output_dir_edit.setFixedHeight(32)
        self._browse_output_btn = QToolButton()
        self._browse_output_btn.setText("...")
        self._browse_output_btn.setFixedSize(32, 32)
        
        output_row.addWidget(self._output_dir_edit)
        output_row.addWidget(self._browse_output_btn)
        parent_layout.addLayout(output_row)
    
    def _create_viewport(self) -> QWidget:
        """创建右侧视窗区域"""
        viewport = QWidget()
        layout = QVBoxLayout(viewport)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # 使用 QStackedWidget 切换视频预览和图片浏览器
        self._preview_stack = QStackedWidget()
        
        # 页面 0: 视频/通用预览
        self._preview_canvas = PreviewCanvas()
        self._preview_stack.addWidget(self._preview_canvas)
        
        # 页面 1: 图片结果浏览器
        self._image_browser = ImageResultBrowser()
        self._preview_stack.addWidget(self._image_browser)
        
        layout.addWidget(self._preview_stack, 1)
        
        # 控制栏堆叠区域: 视频播放栏 / 图片进度条
        self._control_stack = QStackedWidget()
        self._control_stack.setFixedHeight(36)
        
        # 页面 0: 播放控制栏 (视频进度条 + 暂停按钮)
        playback_bar = self._create_playback_bar()
        self._control_stack.addWidget(playback_bar)
        
        # 页面 1: 图片批量处理进度条
        self._image_progress_bar = ImageProgressBar()
        self._control_stack.addWidget(self._image_progress_bar)
        
        layout.addWidget(self._control_stack)
        
        status_bar = self._create_status_bar()
        layout.addWidget(status_bar)
        
        return viewport
    
    def _create_playback_bar(self) -> QFrame:
        """创建播放控制栏（仅进度条和时间标签，28px 高度）"""
        bar = QFrame()
        bar.setObjectName("playbackBar")
        bar.setFixedHeight(28)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)
        
        # 进度条
        self._progress_slider = QSlider(Qt.Orientation.Horizontal)
        self._progress_slider.setObjectName("playbackSlider")
        self._progress_slider.setRange(0, 100)
        self._progress_slider.setValue(0)
        self._progress_slider.setEnabled(False)
        self._progress_slider.setFixedHeight(16)
        layout.addWidget(self._progress_slider, 1)
        
        # 时间标签
        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setFixedWidth(90)
        self._time_label.setObjectName("mutedLabel")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._time_label)
        
        # 初始隐藏播放控制栏（启动时显示）
        bar.setVisible(False)
        self._playback_bar = bar
        
        return bar
    
    def _create_status_bar(self) -> QFrame:
        """创建底部状态栏"""
        status_bar = QFrame()
        status_bar.setObjectName("statusBar")
        status_bar.setFixedHeight(50)
        
        layout = QHBoxLayout(status_bar)
        layout.setContentsMargins(12, 8, 16, 8)
        layout.setSpacing(12)
        
        # 折叠/展开按钮 (状态栏最左边)
        self._toggle_btn = QPushButton("☰")
        self._toggle_btn.setFixedSize(32, 32)
        self._toggle_btn.setObjectName("logPanelBtn")
        self._toggle_btn.setToolTip("折叠设置面板")
        self._toggle_btn.clicked.connect(self._toggle_panel)
        layout.addWidget(self._toggle_btn)
        
        self._fps_display = QLabel("FPS: --")
        self._fps_display.setObjectName("successLabel")
        
        self._frame_display = QLabel("已处理: 0 帧")
        
        self._object_display = QLabel("检测: 0 个")
        self._object_display.setObjectName("warningLabel")
        
        self._model_display = QLabel("模型: 未加载")
        self._model_display.setObjectName("mutedLabel")
        
        layout.addWidget(self._fps_display)
        layout.addWidget(self._frame_display)
        layout.addWidget(self._object_display)
        layout.addWidget(self._model_display)
        layout.addStretch()
        
        self._start_btn = QPushButton("▶ 开始")
        self._start_btn.setFixedSize(80, 32)
        self._start_btn.setProperty("class", "success")
        
        self._stop_btn = QPushButton("⏹ 停止")
        self._stop_btn.setFixedSize(80, 32)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setProperty("class", "danger")
        
        layout.addWidget(self._start_btn)
        layout.addWidget(self._stop_btn)
        
        return status_bar
    
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
        
        # 播放控制信号
        self._progress_slider.sliderReleased.connect(self._on_progress_seek)
        
        self._predict_manager.frame_ready.connect(self._on_frame_ready)
        self._predict_manager.stats_updated.connect(self._on_stats_updated)
        self._predict_manager.error_occurred.connect(self._on_error)
        self._predict_manager.finished.connect(self._on_prediction_finished)
        self._predict_manager.state_changed.connect(self._on_playback_state_changed)
        self._predict_manager.progress_updated.connect(self._on_progress_updated)
        self._output_manager.file_saved.connect(self._on_file_saved)
        self._output_manager.error_occurred.connect(self._on_error)
        
        # 图片模式信号 (使用 QueuedConnection 确保跨线程信号正确)
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
        """应用语义化样式 (颜色由全局 QSS 主题控制)"""
        pass
    
    @Slot(int)
    def _on_source_type_changed(self, id: int) -> None:
        """输入源类型切换"""
        is_image_mode = (id == 0)
        is_video_mode = (id == 1)
        
        # 输入源区域
        self._image_mode_container.setVisible(id == 0)
        self._video_mode_container.setVisible(id == 1)
        self._camera_container.setVisible(id == 2)
        self._screen_container.setVisible(id == 3)
        
        # 输出选项区域切换
        self._image_output_container.setVisible(is_image_mode)
        self._video_output_container.setVisible(not is_image_mode)
        
        # 预览区域切换: 0=视频预览, 1=图片浏览器 (图片模式默认显示图片浏览器)
        self._preview_stack.setCurrentIndex(1 if is_image_mode else 0)
        
        # 控制栏切换: 0=视频进度条, 1=图片导航栏
        self._control_stack.setCurrentIndex(1 if is_image_mode else 0)
        
        # 设备扫描 - 按需扫描，避免不必要地激活摄像头
        if id == 2 and not self._cameras_scanned:
            self._scan_cameras()
            self._cameras_scanned = True
        elif id == 3 and not self._screens_scanned:
            self._scan_screens()
            self._screens_scanned = True
    
    @Slot(int)
    def _on_image_sub_changed(self, id: int) -> None:
        """图片子选项切换: 0=单张, 1=批量"""
        self._single_image_container.setVisible(id == 0)
        self._batch_image_container.setVisible(id == 1)
    
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
    
    @Slot(int)
    def _on_video_sub_changed(self, id: int) -> None:
        """视频子选项切换: 0=单个, 1=批量"""
        self._single_video_container.setVisible(id == 0)
        self._batch_video_container.setVisible(id == 1)
        self._is_video_batch_mode = (id == 1)
    
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
    
    @Slot(bool)
    def _on_rtsp_toggled(self, checked: bool) -> None:
        self._rtsp_edit.setEnabled(checked)
        self._test_rtsp_btn.setEnabled(checked)
        self._camera_combo.setEnabled(not checked)
    
    @Slot()
    def _on_test_rtsp(self) -> None:
        url = self._rtsp_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "警告", "请输入 RTSP 地址")
            return
        self.log_message.emit(f"正在测试 RTSP: {url}")
        success, error = DeviceScanner.test_rtsp(url)
        if success:
            QMessageBox.information(self, "成功", "RTSP 连接成功!")
            self.log_message.emit("RTSP 测试通过")
        else:
            QMessageBox.warning(self, "失败", f"RTSP 连接失败: {error}")
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
        # 切换 objectName 并刷新样式
        new_name = "accentLabel" if checked else "mutedLabel"
        self._threshold_label.setObjectName(new_name)
        self._threshold_label.style().unpolish(self._threshold_label)
        self._threshold_label.style().polish(self._threshold_label)
    
    @Slot(int)
    def _on_threshold_changed(self, value: int) -> None:
        self._threshold_label.setText(f"{value / 100.0:.2f}")
    
    @Slot(bool)
    def _on_img_high_conf_toggled(self, checked: bool) -> None:
        """图片模式高置信度过滤开关"""
        self._img_threshold_slider.setEnabled(checked)
    
    @Slot(int)
    def _on_img_threshold_changed(self, value: int) -> None:
        """图片模式阈值变化"""
        self._img_threshold_label.setText(f"{value / 100.0:.2f}")
    
    @Slot()
    def _on_start_pause_clicked(self) -> None:
        """处理开始/暂停按钮点击（复用逻辑）"""
        # 图片模式: 处理批量处理的暂停/继续
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
        
        # 视频/其他模式: 处理暂停/继续
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
        
        # 否则，启动预测
        self._on_start()
    
    def _on_start(self) -> None:
        """启动预测"""
        model_path = self._model_path_edit.text().strip()
        if not model_path or not Path(model_path).exists():
            QMessageBox.warning(self, "警告", "请选择有效的模型文件")
            return
        # 检查模型路径是否变化，如果变化则重新加载
        if self._predict_manager._model_path != model_path:
            self.log_message.emit(f"正在加载模型: {model_path}")
            if not self._predict_manager.load_model(model_path):
                QMessageBox.critical(self, "错误", "模型加载失败")
                return
            self.log_message.emit("模型加载成功")
            self._populate_class_filter()
        
        source_id = self._source_btn_group.checkedId()
        source, source_type, screen_region = None, None, None
        
        # 图片模式: 使用专用的图片处理流程
        if source_id == 0:
            self._start_image_processing()
            return
        elif source_id == 1:
            # 视频模式：区分单个视频和批量视频
            if self._is_video_batch_mode:
                # 批量视频模式
                self._start_video_batch_processing()
                return
            else:
                # 单个视频模式
                source = self._source_path_edit.text().strip()
                source_type = InputSourceType.VIDEO
                if not source or not Path(source).exists():
                    QMessageBox.warning(self, "警告", "请选择有效的视频")
                    return
        elif source_id == 2:
            if self._rtsp_check.isChecked():
                source = self._rtsp_edit.text().strip()
                source_type = InputSourceType.RTSP
                if not source:
                    QMessageBox.warning(self, "警告", "请输入 RTSP 地址")
                    return
            else:
                idx = self._camera_combo.currentIndex()
                if idx < 0 or idx >= len(self._cameras):
                    QMessageBox.warning(self, "警告", "请选择摄像头")
                    return
                source = self._cameras[idx]["id"]
                source_type = InputSourceType.CAMERA
        elif source_id == 3:
            idx = self._screen_combo.currentIndex()
            if idx < 0 or idx >= len(self._screens):
                QMessageBox.warning(self, "警告", "请选择屏幕")
                return
            screen = self._screens[idx]
            source = f"screen_{idx}"  # 仅用于日志标识，实际使用 screen_region
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
                    self._video_fps = info.get("fps", 30.0)  # 保存帧率供进度计算使用
                else:
                    self._video_fps = 30.0
        
        conf = self._conf_slider.value() / 100.0
        iou = self._iou_slider.value() / 100.0
        self.log_message.emit(f"开始预测: {source}")
        
        # 保存当前源类型用于按钮状态判断
        self._current_source_type = source_type
        
        if self._predict_manager.start(source=source, source_type=source_type, conf=conf, iou=iou, screen_region=screen_region):
            self._stop_btn.setEnabled(True)
            self._frame_count = 0
            self._fps_frame_count = 0
            self._fps_timer.start(1000)
            
            # 初始化播放控制栏
            self._playback_bar.setVisible(True)
            
            # 根据源类型配置进度条和开始按钮
            is_video = source_type == InputSourceType.VIDEO
            is_image = source_type == InputSourceType.IMAGE
            self._progress_slider.setEnabled(is_video)
            self._progress_slider.setRange(0, 10000)
            self._progress_slider.setValue(0)
            self._time_label.setText("00:00 / 00:00")
            
            # 图片模式：开始按钮变灰；其他模式：显示暂停
            if is_image:
                self._start_btn.setEnabled(False)
            else:
                self._start_btn.setText("⏸ 暂停")
                set_button_class(self._start_btn, "warning")
        else:
            QMessageBox.critical(self, "错误", "启动预测失败")
    
    @Slot()
    def _on_stop(self) -> None:
        # 设置停止标志，防止后续状态信号干扰按钮重置
        self._is_stopping = True
        
        # 图片模式: 停止批量处理
        if self._is_image_mode and self._is_batch_processing:
            self._image_processor.stop()
            if self._batch_thread and self._batch_thread.isRunning():
                if not self._batch_thread.wait(5000):  # 增加到 5 秒
                    self.log_message.emit("[警告] 批量处理线程超时未结束")
            self._is_batch_processing = False
            self._image_progress_bar.set_finished("处理已中止")
            self.log_message.emit("图片批量处理已停止")
        elif self._video_batch_processor.is_running:
            # 视频批量模式
            self._video_batch_processor.stop()
            if self._video_batch_thread and self._video_batch_thread.isRunning():
                if not self._video_batch_thread.wait(5000):
                    self.log_message.emit("[警告] 视频批量处理线程超时未结束")
            self.log_message.emit("视频批量处理已停止")
        elif self._predict_manager.is_running:
            # 视频/其他模式 - 只有在运行时才执行停止操作
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
            
            # 重置播放控制栏
            self._progress_slider.setValue(0)
            self._progress_slider.setEnabled(False)
            self._time_label.setText("00:00 / 00:00")
            self._current_source_type = None
            self.log_message.emit("预测已停止")
        
        # 重置开始按钮为初始状态
        self._start_btn.setEnabled(True)
        self._start_btn.setText("▶ 开始")
        set_button_class(self._start_btn, "success")
        self._stop_btn.setEnabled(False)
        
        # 重置停止标志
        self._is_stopping = False
    
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
        
        # 保存关键帧逻辑
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
    
    # ==================== 播放控制槽函数 ====================
    
    @Slot()
    def _on_progress_seek(self) -> None:
        """处理进度条拖动释放"""
        if not self._predict_manager.is_seekable:
            return
        
        total = self._predict_manager.total_frames
        if total <= 0:
            return
        
        # 将滑块值 (0-10000) 转换为帧索引
        target_frame = int(self._progress_slider.value() / 10000 * total)
        self._predict_manager.seek(target_frame)
    
    @Slot(str)
    def _on_playback_state_changed(self, state: str) -> None:
        """处理播放状态变化，更新开始按钮"""
        # 停止过程中或已停止时，忽略 playing/paused 信号
        # 这可以防止延迟到达的信号覆盖已经重置的按钮状态
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
        
        # 更新进度条 (使用 0-10000 范围以获得更平滑的拖动体验)
        if not self._progress_slider.isSliderDown():
            progress = int(current / total * 10000)
            self._progress_slider.setValue(progress)
        
        # 更新时间标签 (使用实际帧率，默认 30fps)
        fps = getattr(self, '_video_fps', 30.0)
        current_sec = current / fps
        total_sec = total / fps
        self._time_label.setText(f"{self._format_time(current_sec)} / {self._format_time(total_sec)}")
    
    def _format_time(self, seconds: float) -> str:
        """格式化时间为 MM:SS"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"
    
    # ==================== 图片模式槽函数 ====================
    
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
        
        # 重置按钮状态
        self._start_btn.setText("▶ 开始")
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        
        # 显示第一张结果
        if processed > 0:
            result = self._image_processor.get_result(0)
            if result:
                original, annotated, detections = result
                self._image_browser.show_result(original, annotated, detections)
                self._image_browser.update_navigation(0, processed)
        
        # 保存输出
        self._finalize_image_output()
        
        self.log_message.emit(f"图片批量处理完成: {processed}/{total}")
    
    def _start_image_processing(self) -> None:
        """启动图片处理"""
        # 根据子选项确定图片源
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
        
        # 加载模型
        model_path = self._model_path_edit.text().strip()
        if not model_path:
            self._on_error("请选择模型")
            return
        
        # 检查模型路径是否变化，如果变化则重新加载
        if self._predict_manager._model_path != model_path:
            if not self._predict_manager.load_model(model_path):
                return
            self._populate_class_filter()
        
        # 设置模型到图片处理器
        self._image_processor.set_model(self._predict_manager._model)
        
        # 加载图片
        count = self._image_processor.load_images(source)
        
        if count == 0:
            self._on_error("未找到图片")
            return
        
        # 设置输出目录
        output_dir = self._output_dir_edit.text().strip()
        if output_dir:
            self._output_manager.set_output_dir(output_dir)
            self._output_manager.setup_image_output_dirs()
        
        # 更新推理参数
        conf = self._conf_slider.value() / 100.0
        iou = self._iou_slider.value() / 100.0
        high_conf = self._threshold_slider.value() / 100.0
        self._image_processor.update_params(conf, iou, high_conf)
        
        # 切换到图片模式 UI
        self._is_image_mode = True
        self._preview_stack.setCurrentIndex(1)  # 图片浏览器
        self._control_stack.setCurrentIndex(1)  # 图片进度条
        
        # 单张图片 vs 批量处理
        if count == 1:
            # 单张图片: 立即处理
            result = self._image_processor.process_single(0)
            if result:
                original, annotated, detections = result
                self._image_browser.show_result(original, annotated, detections)
                self._image_browser.update_navigation(0, 1)
            
            # 保存输出
            self._finalize_image_output()
            
            self._start_btn.setText("▶ 开始")
            self._stop_btn.setEnabled(False)
        else:
            # 批量处理
            self._is_batch_processing = True
            self._start_btn.setText("⋯ 处理中")
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)
            
            self._image_progress_bar.update_progress(0, count)
            
            # 确定保存条件
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
            
            # 在后台线程中执行批量处理
            from PySide6.QtCore import QThread
            
            class BatchProcessThread(QThread):
                """批量处理线程"""
                def __init__(self, processor, condition):
                    super().__init__()
                    self._processor = processor
                    self._condition = condition
                
                def run(self):
                    self._processor.process_all(self._condition)
            
            self._batch_thread = BatchProcessThread(self._image_processor, condition)
            self._batch_thread.start()
    
    def _finalize_image_output(self) -> None:
        """保存图片输出结果"""
        output_dir = self._output_dir_edit.text().strip()
        if not output_dir:
            return
        
        processor = self._image_processor
        
        # 保存每张图片的结果
        for path in processor.get_processed_list():
            detections = processor._results_cache.get(path, [])
            if not detections and not self._save_result_image_check.isChecked():
                continue
            
            import cv2
            original = cv2.imread(str(path))
            if original is None:
                continue
            
            annotated = processor._draw_detections(original, detections)
            
            self._output_manager.save_image_result(
                original=original,
                annotated=annotated,
                detections=detections,
                image_name=path.stem,
                save_original=self._save_original_check.isChecked(),
                save_annotated=self._save_result_image_check.isChecked(),
                save_labels=self._save_labels_check.isChecked()
            )
        
        # 保存路径列表
        detected_list = processor.get_detected_list()
        empty_list = processor.get_empty_list()
        self._output_manager.save_path_list(detected_list, empty_list)
        
        # 生成报告 (使用图片模式的报告复选框)
        if self._save_image_report_check.isChecked():
            self._output_manager.generate_image_report(
                total_images=processor.image_count,
                detected_count=len(detected_list),
                empty_count=len(empty_list)
            )

    # =====================================================
    # 视频批量处理相关槽函数
    # =====================================================

    @Slot(str, int, int)
    def _on_video_batch_started(self, video_path: str, index: int, total: int) -> None:
        """单个视频开始处理"""
        video_name = Path(video_path).name
        self._frame_display.setText(f"视频 [{index+1}/{total}]: {video_name}")
        self._object_display.setText(f"进度: {index+1}/{total} 个视频")
        # 重置进度条和时间
        self._progress_slider.setValue(0)
        self._time_label.setText("00:00 / 00:00")
        self.log_message.emit(f"开始处理视频: {video_name}")

    @Slot(int, int)
    def _on_video_frame_progress(self, current: int, total: int) -> None:
        """当前视频帧进度更新 - 批量模式通过状态栏显示"""
        if total > 0:
            percent = int(current / total * 100)
            self._fps_display.setText(f"帧: {current}/{total} ({percent}%)")

    @Slot(int, int)
    def _on_video_batch_progress(self, completed: int, total: int) -> None:
        """整体批量进度更新（视频完成后触发）"""
        # 不再在这里更新，改在 video_started 中更新
        pass

    @Slot()
    def _on_video_batch_finished(self) -> None:
        """视频批量处理完成"""
        # 清理线程
        if hasattr(self, '_video_batch_thread') and self._video_batch_thread:
            if self._video_batch_thread.isRunning():
                self._video_batch_thread.wait(3000)
            self._video_batch_thread.deleteLater()
            self._video_batch_thread = None
        self._start_btn.setText("▶ 开始")
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        
        # 生成汇总报告
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
        
        QMessageBox.information(
            self,
            "批量处理完成",
            f"已处理 {len(stats)} 个视频\n"
            f"总检测数: {total_detections}\n"
            f"保存关键帧: {total_keyframes}"
        )

    def _start_video_batch_processing(self) -> None:
        """启动视频批量处理"""
        source = self._batch_video_folder_edit.text().strip()
        if not source:
            QMessageBox.warning(self, "警告", "请选择视频文件夹")
            return
        
        # 加载模型
        model_path = self._model_path_edit.text().strip()
        if not model_path:
            QMessageBox.warning(self, "警告", "请选择模型文件")
            return
        
        if not self._predict_manager.is_model_loaded:
            success = self._predict_manager.load_model(model_path)
            if not success:
                return
            self._populate_class_filter()
        
        # 获取输出目录，以模型名命名子文件夹
        output_dir = self._output_dir_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "警告", "请选择输出目录")
            return
        model_name = Path(model_path).stem  # 模型名（不含扩展名）
        output_dir = str(Path(output_dir) / model_name)
        
        # 加载视频
        video_count = self._video_batch_processor.load_videos(source)
        if video_count == 0:
            QMessageBox.warning(self, "警告", "未找到视频文件")
            return
        
        # 设置处理器
        self._video_batch_processor.set_model(self._predict_manager._model)
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
        
        # 更新 UI 状态
        self._start_btn.setText("处理中...")
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._playback_bar.setVisible(False)  # 批量模式隐藏播放控制栏
        
        self.log_message.emit(f"开始批量处理 {video_count} 个视频")
        
        # 在子线程中运行（使用继承 QThread 方式，避免 moveToThread 问题）
        from PySide6.QtCore import QThread
        
        class VideoBatchThread(QThread):
            """视频批量处理线程"""
            def __init__(self, processor):
                super().__init__()
                self._processor = processor
            
            def run(self):
                self._processor.process_all()
        
        self._video_batch_thread = VideoBatchThread(self._video_batch_processor)
        self._video_batch_thread.start()

