"""
_panel.py - PanelMixin: 左侧配置面板 UI 构建
============================================
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.focus_widgets import FocusComboBox, FocusSlider


class PanelMixin:
    """左侧配置面板 UI 构建 (输入源/模型/输出区域)"""

    def _create_settings_panel(self) -> QWidget:
        """创建左侧配置面板 (带滚动条)"""
        panel = QFrame()
        panel.setObjectName("settingsPanel")
        panel.setMinimumWidth(200)
        panel.setMaximumWidth(400)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(10)

        # 输入源区域
        layout.addWidget(self._create_section_label("输入源"))
        self._create_source_section_compact(layout)

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

        # === 图片模式专用区域 ===
        self._image_mode_container = QWidget()
        image_mode_layout = QVBoxLayout(self._image_mode_container)
        image_mode_layout.setContentsMargins(0, 8, 0, 0)
        image_mode_layout.setSpacing(8)

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
        self._batch_image_container.setVisible(False)

        parent_layout.addWidget(self._image_mode_container)

        # === 视频模式专用区域 ===
        self._video_mode_container = QWidget()
        video_mode_layout = QVBoxLayout(self._video_mode_container)
        video_mode_layout.setContentsMargins(0, 8, 0, 0)
        video_mode_layout.setSpacing(8)

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
        self._batch_video_container.setVisible(False)

        self._video_mode_container.setVisible(False)
        parent_layout.addWidget(self._video_mode_container)

        # 摄像头选择
        self._camera_container = QWidget()
        camera_layout = QVBoxLayout(self._camera_container)
        camera_layout.setContentsMargins(0, 8, 0, 0)
        camera_layout.setSpacing(8)

        cam_row = QHBoxLayout()
        cam_row.setSpacing(4)
        self._camera_combo = FocusComboBox()
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
        rtsp_row.setSpacing(4)
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

        self._screen_combo = FocusComboBox()
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
        self._class_filter_combo = FocusComboBox()
        self._class_filter_combo.addItem("全部")
        self._class_filter_combo.setFixedHeight(32)

        filter_row.addWidget(filter_label)
        filter_row.addWidget(self._class_filter_combo)
        parent_layout.addLayout(filter_row)

    def _create_output_section_compact(self, parent_layout: QVBoxLayout) -> None:
        """创建紧凑型输出区域"""
        # === 图片模式输出选项 ===
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
        img_threshold_row.setContentsMargins(16, 0, 0, 0)
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

        # === 视频/其他模式输出选项 ===
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

        self._video_output_container.setVisible(False)
        parent_layout.addWidget(self._video_output_container)

        # 信号连接
        self._high_conf_check.toggled.connect(self._on_high_conf_toggled)
        self._threshold_slider.valueChanged.connect(self._on_threshold_changed)
        self._filter_high_conf_radio.toggled.connect(self._on_img_high_conf_toggled)
        self._img_threshold_slider.valueChanged.connect(self._on_img_threshold_changed)

        # 输出目录 (共用)
        output_row = QHBoxLayout()
        output_row.setSpacing(4)
        self._output_dir_edit = QLineEdit()
        self._output_dir_edit.setPlaceholderText("输出目录...")
        self._output_dir_edit.setFixedHeight(32)
        self._browse_output_btn = QToolButton()
        self._browse_output_btn.setText("...")
        self._browse_output_btn.setFixedSize(32, 32)

        output_row.addWidget(self._output_dir_edit)
        output_row.addWidget(self._browse_output_btn)
        parent_layout.addLayout(output_row)
