"""
_viewport.py - ViewportMixin: 右侧视窗区域 UI 构建
============================================
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.focus_widgets import FocusSlider
from ui.image_result_browser import ImageResultBrowser, ImageProgressBar
from ui.predict_preview import PreviewCanvas


class ViewportMixin:
    """右侧视窗 + 播放控制栏 + 状态栏 UI 构建"""

    def _create_viewport(self) -> QWidget:
        """创建右侧视窗区域"""
        viewport = QWidget()
        layout = QVBoxLayout(viewport)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # QStackedWidget: 视频预览 / 图片浏览器
        self._preview_stack = QStackedWidget()

        self._preview_canvas = PreviewCanvas()
        self._preview_stack.addWidget(self._preview_canvas)

        self._image_browser = ImageResultBrowser()
        self._preview_stack.addWidget(self._image_browser)

        layout.addWidget(self._preview_stack, 1)

        # 控制栏堆叠
        self._control_stack = QStackedWidget()
        self._control_stack.setFixedHeight(36)

        playback_bar = self._create_playback_bar()
        self._control_stack.addWidget(playback_bar)

        self._image_progress_bar = ImageProgressBar()
        self._control_stack.addWidget(self._image_progress_bar)

        layout.addWidget(self._control_stack)

        status_bar = self._create_status_bar()
        layout.addWidget(status_bar)

        return viewport

    def _create_playback_bar(self) -> QFrame:
        """创建播放控制栏"""
        bar = QFrame()
        bar.setObjectName("playbackBar")
        bar.setFixedHeight(28)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)

        self._progress_slider = FocusSlider(Qt.Orientation.Horizontal)
        self._progress_slider.setObjectName("playbackSlider")
        self._progress_slider.setRange(0, 100)
        self._progress_slider.setValue(0)
        self._progress_slider.setEnabled(False)
        self._progress_slider.setFixedHeight(16)
        layout.addWidget(self._progress_slider, 1)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setFixedWidth(90)
        self._time_label.setObjectName("mutedLabel")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._time_label)

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

        # 折叠/展开按钮
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
