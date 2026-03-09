"""
train_widget.py - 模型训练 UI 模块
============================================

职责:
    - 训练参数配置界面 (紧凑 2 列布局)
    - 命令预览与编辑
    - 训练进程控制
    - 实时日志显示

架构要点:
    - 左右分栏: 配置面板 + 终端监视器
    - 使用 QGridLayout 实现紧凑布局
    - 命令自动生成 + 用户可编辑
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.train_handler import TrainManager
from core.thread_pool import Worker, run_in_thread
from ui.focus_widgets import FocusComboBox, FocusDoubleSpinBox, FocusSpinBox


class TrainWidget(QWidget):
    """
    模型训练模块 UI
    
    布局:
        - 左侧: 配置面板 (可滚动, 紧凑 2 列布局)
        - 右侧: 终端监视器
    
    Signals:
        log_message(str): 发送到全局日志的消息
    """
    
    # 信号定义
    log_message = Signal(str)
    
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """初始化训练模块 UI"""
        super().__init__(parent)
        
        # 训练管理器
        self._manager = TrainManager(self)
        self._scan_worker: Optional[Worker] = None
        
        # 初始化 UI
        self._setup_ui()
        self._connect_signals()
        self._apply_styles()
        
        # 初始扫描环境
        self._scan_envs()
    
    def _setup_ui(self) -> None:
        """构建 UI 布局"""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # ========== 左侧: 配置面板 ==========
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setSpacing(10)
        
        # --- Group 1: 环境与数据 (使用 GridLayout 确保按钮可见) ---
        env_group = QGroupBox("环境与数据")
        env_grid = QGridLayout(env_group)
        env_grid.setColumnStretch(1, 1)  # 输入列获取所有拉伸
        env_grid.setColumnStretch(2, 0)  # 按钮列固定宽度
        
        # Row 0: Python 解释器
        env_grid.addWidget(QLabel("Python:"), 0, 0)
        self.python_combo = FocusComboBox()
        self.python_combo.setEditable(True)
        self.python_combo.setMinimumWidth(150)
        env_grid.addWidget(self.python_combo, 0, 1)
        
        self.scan_env_btn = QPushButton("扫描")
        self.scan_env_btn.setFixedWidth(70)
        env_grid.addWidget(self.scan_env_btn, 0, 2)
        
        # Row 1: 模型文件
        env_grid.addWidget(QLabel("模型:"), 1, 0)
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("yolov8n.pt")
        self.model_input.setText("yolov8n.pt")
        env_grid.addWidget(self.model_input, 1, 1)
        
        self.model_browse_btn = QPushButton("...")
        self.model_browse_btn.setFixedWidth(70)
        env_grid.addWidget(self.model_browse_btn, 1, 2)
        
        # Row 2: 数据配置
        env_grid.addWidget(QLabel("数据:"), 2, 0)
        self.data_input = QLineEdit()
        self.data_input.setPlaceholderText("data.yaml")
        env_grid.addWidget(self.data_input, 2, 1)
        
        self.data_browse_btn = QPushButton("...")
        self.data_browse_btn.setFixedWidth(70)
        env_grid.addWidget(self.data_browse_btn, 2, 2)
        
        left_layout.addWidget(env_group)
        
        # --- Group 2: 基础超参数 (2 列 GridLayout) ---
        param_group = QGroupBox("基础超参数")
        param_grid = QGridLayout(param_group)
        param_grid.setColumnStretch(1, 1)
        param_grid.setColumnStretch(3, 1)
        
        # Row 0: Epochs | Batch Size
        param_grid.addWidget(QLabel("Epochs:"), 0, 0)
        self.epochs_spin = FocusSpinBox()
        self.epochs_spin.setRange(1, 10000)
        self.epochs_spin.setValue(100)
        param_grid.addWidget(self.epochs_spin, 0, 1)
        
        param_grid.addWidget(QLabel("Batch:"), 0, 2)
        self.batch_spin = FocusSpinBox()
        self.batch_spin.setRange(1, 512)
        self.batch_spin.setValue(16)
        param_grid.addWidget(self.batch_spin, 0, 3)
        
        # Row 1: Image Size | Workers
        param_grid.addWidget(QLabel("ImgSz:"), 1, 0)
        self.imgsz_spin = FocusSpinBox()
        self.imgsz_spin.setRange(32, 2048)
        self.imgsz_spin.setValue(640)
        self.imgsz_spin.setSingleStep(32)
        param_grid.addWidget(self.imgsz_spin, 1, 1)
        
        param_grid.addWidget(QLabel("Workers:"), 1, 2)
        self.workers_spin = FocusSpinBox()
        self.workers_spin.setRange(0, 16)
        self.workers_spin.setValue(8)
        param_grid.addWidget(self.workers_spin, 1, 3)
        
        # Row 2: Device (Full Width)
        param_grid.addWidget(QLabel("Device:"), 2, 0)
        self.device_combo = FocusComboBox()
        self.device_combo.setEditable(True)
        self.device_combo.addItems(["0", "0,1", "0,1,2,3", "cpu", "mps"])
        self.device_combo.setCurrentText("0")
        param_grid.addWidget(self.device_combo, 2, 1, 1, 3)  # Span 3 columns
        
        left_layout.addWidget(param_group)
        
        # --- Group 3: 高级参数 (可折叠, 每参数带启用复选框) ---
        advanced_group = QGroupBox("高级参数")
        advanced_outer = QVBoxLayout(advanced_group)
        advanced_outer.setSpacing(8)
        
        # 折叠按钮
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setObjectName("advancedToggle")
        self.advanced_toggle.setText("▼ 展开高级参数")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        advanced_outer.addWidget(self.advanced_toggle)
        
        # 可折叠内容容器
        self.advanced_container = QWidget()
        adv_layout = QVBoxLayout(self.advanced_container)
        adv_layout.setContentsMargins(0, 0, 0, 0)
        adv_layout.setSpacing(4)
        
        # 参数存储字典 (用于生成命令)
        self.param_checks = {}
        self.param_widgets = {}
        
        # === 数据增强参数 ===
        aug_label = QLabel("数据增强")
        aug_label.setObjectName("accentLabel")
        adv_layout.addWidget(aug_label)
        
        aug_grid = QGridLayout()
        aug_grid.setColumnStretch(1, 1)
        aug_grid.setColumnStretch(3, 1)
        
        # Row 0: Mosaic | Mixup
        self.mosaic_check = QCheckBox("Mosaic:")
        self.mosaic_spin = FocusDoubleSpinBox()
        self.mosaic_spin.setRange(0.0, 1.0)
        self.mosaic_spin.setValue(1.0)
        self.mosaic_spin.setSingleStep(0.1)
        self.mosaic_spin.setDecimals(2)
        aug_grid.addWidget(self.mosaic_check, 0, 0)
        aug_grid.addWidget(self.mosaic_spin, 0, 1)
        self.param_checks["mosaic"] = self.mosaic_check
        self.param_widgets["mosaic"] = self.mosaic_spin
        
        self.mixup_check = QCheckBox("Mixup:")
        self.mixup_spin = FocusDoubleSpinBox()
        self.mixup_spin.setRange(0.0, 1.0)
        self.mixup_spin.setValue(0.0)
        self.mixup_spin.setSingleStep(0.1)
        self.mixup_spin.setDecimals(2)
        aug_grid.addWidget(self.mixup_check, 0, 2)
        aug_grid.addWidget(self.mixup_spin, 0, 3)
        self.param_checks["mixup"] = self.mixup_check
        self.param_widgets["mixup"] = self.mixup_spin
        
        # Row 1: Degrees | Scale
        self.degrees_check = QCheckBox("Degrees:")
        self.degrees_spin = FocusDoubleSpinBox()
        self.degrees_spin.setRange(0.0, 180.0)
        self.degrees_spin.setValue(0.0)
        self.degrees_spin.setSingleStep(5.0)
        self.degrees_spin.setDecimals(1)
        aug_grid.addWidget(self.degrees_check, 1, 0)
        aug_grid.addWidget(self.degrees_spin, 1, 1)
        self.param_checks["degrees"] = self.degrees_check
        self.param_widgets["degrees"] = self.degrees_spin
        
        self.scale_check = QCheckBox("Scale:")
        self.scale_spin = FocusDoubleSpinBox()
        self.scale_spin.setRange(0.0, 1.0)
        self.scale_spin.setValue(0.5)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setDecimals(2)
        aug_grid.addWidget(self.scale_check, 1, 2)
        aug_grid.addWidget(self.scale_spin, 1, 3)
        self.param_checks["scale"] = self.scale_check
        self.param_widgets["scale"] = self.scale_spin
        
        # Row 2: Translate | Shear
        self.translate_check = QCheckBox("Translate:")
        self.translate_spin = FocusDoubleSpinBox()
        self.translate_spin.setRange(0.0, 1.0)
        self.translate_spin.setValue(0.1)
        self.translate_spin.setSingleStep(0.05)
        self.translate_spin.setDecimals(2)
        aug_grid.addWidget(self.translate_check, 2, 0)
        aug_grid.addWidget(self.translate_spin, 2, 1)
        self.param_checks["translate"] = self.translate_check
        self.param_widgets["translate"] = self.translate_spin
        
        self.shear_check = QCheckBox("Shear:")
        self.shear_spin = FocusDoubleSpinBox()
        self.shear_spin.setRange(0.0, 90.0)
        self.shear_spin.setValue(0.0)
        self.shear_spin.setSingleStep(1.0)
        self.shear_spin.setDecimals(1)
        aug_grid.addWidget(self.shear_check, 2, 2)
        aug_grid.addWidget(self.shear_spin, 2, 3)
        self.param_checks["shear"] = self.shear_check
        self.param_widgets["shear"] = self.shear_spin
        
        # Row 3: FlipLR | FlipUD
        self.fliplr_check = QCheckBox("FlipLR:")
        self.fliplr_spin = FocusDoubleSpinBox()
        self.fliplr_spin.setRange(0.0, 1.0)
        self.fliplr_spin.setValue(0.5)
        self.fliplr_spin.setSingleStep(0.1)
        self.fliplr_spin.setDecimals(2)
        aug_grid.addWidget(self.fliplr_check, 3, 0)
        aug_grid.addWidget(self.fliplr_spin, 3, 1)
        self.param_checks["fliplr"] = self.fliplr_check
        self.param_widgets["fliplr"] = self.fliplr_spin
        
        self.flipud_check = QCheckBox("FlipUD:")
        self.flipud_spin = FocusDoubleSpinBox()
        self.flipud_spin.setRange(0.0, 1.0)
        self.flipud_spin.setValue(0.0)
        self.flipud_spin.setSingleStep(0.1)
        self.flipud_spin.setDecimals(2)
        aug_grid.addWidget(self.flipud_check, 3, 2)
        aug_grid.addWidget(self.flipud_spin, 3, 3)
        self.param_checks["flipud"] = self.flipud_check
        self.param_widgets["flipud"] = self.flipud_spin
        
        # Row 4: HSV_H | HSV_S
        self.hsv_h_check = QCheckBox("HSV_H:")
        self.hsv_h_spin = FocusDoubleSpinBox()
        self.hsv_h_spin.setRange(0.0, 1.0)
        self.hsv_h_spin.setValue(0.015)
        self.hsv_h_spin.setSingleStep(0.005)
        self.hsv_h_spin.setDecimals(3)
        aug_grid.addWidget(self.hsv_h_check, 4, 0)
        aug_grid.addWidget(self.hsv_h_spin, 4, 1)
        self.param_checks["hsv_h"] = self.hsv_h_check
        self.param_widgets["hsv_h"] = self.hsv_h_spin
        
        self.hsv_s_check = QCheckBox("HSV_S:")
        self.hsv_s_spin = FocusDoubleSpinBox()
        self.hsv_s_spin.setRange(0.0, 1.0)
        self.hsv_s_spin.setValue(0.7)
        self.hsv_s_spin.setSingleStep(0.1)
        self.hsv_s_spin.setDecimals(2)
        aug_grid.addWidget(self.hsv_s_check, 4, 2)
        aug_grid.addWidget(self.hsv_s_spin, 4, 3)
        self.param_checks["hsv_s"] = self.hsv_s_check
        self.param_widgets["hsv_s"] = self.hsv_s_spin
        
        # Row 5: HSV_V
        self.hsv_v_check = QCheckBox("HSV_V:")
        self.hsv_v_spin = FocusDoubleSpinBox()
        self.hsv_v_spin.setRange(0.0, 1.0)
        self.hsv_v_spin.setValue(0.4)
        self.hsv_v_spin.setSingleStep(0.1)
        self.hsv_v_spin.setDecimals(2)
        aug_grid.addWidget(self.hsv_v_check, 5, 0)
        aug_grid.addWidget(self.hsv_v_spin, 5, 1)
        self.param_checks["hsv_v"] = self.hsv_v_check
        self.param_widgets["hsv_v"] = self.hsv_v_spin
        
        adv_layout.addLayout(aug_grid)
        adv_layout.addSpacing(10)
        
        # === 优化器参数 ===
        opt_label = QLabel("优化器")
        opt_label.setObjectName("accentLabel")
        adv_layout.addWidget(opt_label)
        
        opt_grid = QGridLayout()
        opt_grid.setColumnStretch(1, 1)
        opt_grid.setColumnStretch(3, 1)
        
        # Row 0: Optimizer | LR
        self.optimizer_check = QCheckBox("Optimizer:")
        self.optimizer_combo = FocusComboBox()
        self.optimizer_combo.addItems(["auto", "SGD", "Adam", "AdamW", "NAdam", "RAdam", "RMSProp"])
        opt_grid.addWidget(self.optimizer_check, 0, 0)
        opt_grid.addWidget(self.optimizer_combo, 0, 1)
        self.param_checks["optimizer"] = self.optimizer_check
        self.param_widgets["optimizer"] = self.optimizer_combo
        
        self.lr0_check = QCheckBox("LR:")
        self.lr0_spin = FocusDoubleSpinBox()
        self.lr0_spin.setRange(0.0001, 1.0)
        self.lr0_spin.setValue(0.01)
        self.lr0_spin.setSingleStep(0.001)
        self.lr0_spin.setDecimals(4)
        opt_grid.addWidget(self.lr0_check, 0, 2)
        opt_grid.addWidget(self.lr0_spin, 0, 3)
        self.param_checks["lr0"] = self.lr0_check
        self.param_widgets["lr0"] = self.lr0_spin
        
        # Row 1: Final LR | Momentum
        self.lrf_check = QCheckBox("Final LR:")
        self.lrf_spin = FocusDoubleSpinBox()
        self.lrf_spin.setRange(0.0001, 1.0)
        self.lrf_spin.setValue(0.01)
        self.lrf_spin.setSingleStep(0.001)
        self.lrf_spin.setDecimals(4)
        opt_grid.addWidget(self.lrf_check, 1, 0)
        opt_grid.addWidget(self.lrf_spin, 1, 1)
        self.param_checks["lrf"] = self.lrf_check
        self.param_widgets["lrf"] = self.lrf_spin
        
        self.momentum_check = QCheckBox("Momentum:")
        self.momentum_spin = FocusDoubleSpinBox()
        self.momentum_spin.setRange(0.0, 1.0)
        self.momentum_spin.setValue(0.937)
        self.momentum_spin.setSingleStep(0.01)
        self.momentum_spin.setDecimals(3)
        opt_grid.addWidget(self.momentum_check, 1, 2)
        opt_grid.addWidget(self.momentum_spin, 1, 3)
        self.param_checks["momentum"] = self.momentum_check
        self.param_widgets["momentum"] = self.momentum_spin
        
        # Row 2: Weight Decay
        self.weight_decay_check = QCheckBox("W.Decay:")
        self.weight_decay_spin = FocusDoubleSpinBox()
        self.weight_decay_spin.setRange(0.0, 1.0)
        self.weight_decay_spin.setValue(0.0005)
        self.weight_decay_spin.setSingleStep(0.0001)
        self.weight_decay_spin.setDecimals(5)
        opt_grid.addWidget(self.weight_decay_check, 2, 0)
        opt_grid.addWidget(self.weight_decay_spin, 2, 1)
        self.param_checks["weight_decay"] = self.weight_decay_check
        self.param_widgets["weight_decay"] = self.weight_decay_spin
        
        adv_layout.addLayout(opt_grid)
        adv_layout.addSpacing(10)
        
        # === 训练控制参数 ===
        ctrl_label = QLabel("训练控制")
        ctrl_label.setObjectName("accentLabel")
        adv_layout.addWidget(ctrl_label)
        
        ctrl_grid = QGridLayout()
        ctrl_grid.setColumnStretch(1, 1)
        ctrl_grid.setColumnStretch(3, 1)
        
        # Row 0: Patience | Close Mosaic
        self.patience_check = QCheckBox("Patience:")
        self.patience_spin = FocusSpinBox()
        self.patience_spin.setRange(1, 1000)
        self.patience_spin.setValue(100)
        ctrl_grid.addWidget(self.patience_check, 0, 0)
        ctrl_grid.addWidget(self.patience_spin, 0, 1)
        self.param_checks["patience"] = self.patience_check
        self.param_widgets["patience"] = self.patience_spin
        
        self.close_mosaic_check = QCheckBox("CloseMos:")
        self.close_mosaic_spin = FocusSpinBox()
        self.close_mosaic_spin.setRange(0, 100)
        self.close_mosaic_spin.setValue(10)
        ctrl_grid.addWidget(self.close_mosaic_check, 0, 2)
        ctrl_grid.addWidget(self.close_mosaic_spin, 0, 3)
        self.param_checks["close_mosaic"] = self.close_mosaic_check
        self.param_widgets["close_mosaic"] = self.close_mosaic_spin
        
        # Row 1: Cache | Multi-scale
        self.cache_check = QCheckBox("Cache:")
        self.cache_combo = FocusComboBox()
        self.cache_combo.addItems(["False", "ram", "disk"])
        ctrl_grid.addWidget(self.cache_check, 1, 0)
        ctrl_grid.addWidget(self.cache_combo, 1, 1)
        self.param_checks["cache"] = self.cache_check
        self.param_widgets["cache"] = self.cache_combo
        
        self.multi_scale_check = QCheckBox("Multi-scale")
        self.multi_scale_check.setToolTip("启用多尺度训练")
        ctrl_grid.addWidget(self.multi_scale_check, 1, 2, 1, 2)
        self.param_checks["multi_scale"] = self.multi_scale_check
        self.param_widgets["multi_scale"] = self.multi_scale_check  # 特殊: 自身就是控件
        
        # Row 2: AMP
        self.amp_check = QCheckBox("AMP 混合精度")
        ctrl_grid.addWidget(self.amp_check, 2, 0, 1, 4)
        self.param_checks["amp"] = self.amp_check
        self.param_widgets["amp"] = self.amp_check  # 特殊: 自身就是控件
        
        adv_layout.addLayout(ctrl_grid)
        
        self.advanced_container.setVisible(False)  # 默认收起
        advanced_outer.addWidget(self.advanced_container)
        
        left_layout.addWidget(advanced_group)
        
        # --- Group 5: 命令预览 ---
        cmd_group = QGroupBox("命令预览 (可编辑)")
        cmd_layout = QVBoxLayout(cmd_group)
        
        self.command_preview = QPlainTextEdit()
        self.command_preview.setMaximumHeight(80)
        self.command_preview.setPlaceholderText("训练命令将在这里生成...")
        cmd_layout.addWidget(self.command_preview)
        
        left_layout.addWidget(cmd_group)
        
        # --- Group 6: 操作按钮 ---
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        
        self.stop_btn = QPushButton("⏹ 停止训练")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setProperty("class", "danger")
        action_layout.addWidget(self.stop_btn)
        
        self.start_btn = QPushButton("▶ 开始训练")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setProperty("class", "primary")
        action_layout.addWidget(self.start_btn)
        
        left_layout.addLayout(action_layout)
        left_layout.addStretch()
        
        left_scroll.setWidget(left_container)
        main_layout.addWidget(left_scroll, 1)
        
        # ========== 右侧: 终端监视器 ==========
        right_layout = QVBoxLayout()
        
        terminal_label = QLabel("📺 训练输出")
        terminal_label.setObjectName("successLabel")
        right_layout.addWidget(terminal_label)
        
        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setPlaceholderText("训练日志将显示在这里...")
        right_layout.addWidget(self.terminal, 1)
        
        # 清空按钮
        clear_layout = QHBoxLayout()
        clear_layout.addStretch()
        self.clear_terminal_btn = QPushButton("清空")
        self.clear_terminal_btn.setFixedWidth(60)
        clear_layout.addWidget(self.clear_terminal_btn)
        right_layout.addLayout(clear_layout)
        
        main_layout.addLayout(right_layout, 1)
    
    def _connect_signals(self) -> None:
        """连接信号与槽"""
        # 环境扫描
        self.scan_env_btn.clicked.connect(self._scan_envs)
        
        # 文件浏览
        self.model_browse_btn.clicked.connect(self._browse_model)
        self.data_browse_btn.clicked.connect(self._browse_data)
        
        # 高级选项折叠
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        
        # 参数变化 → 生成命令
        self.python_combo.currentTextChanged.connect(self._on_param_changed)
        self.model_input.textChanged.connect(self._on_param_changed)
        self.data_input.textChanged.connect(self._on_param_changed)
        self.epochs_spin.valueChanged.connect(self._on_param_changed)
        self.batch_spin.valueChanged.connect(self._on_param_changed)
        self.imgsz_spin.valueChanged.connect(self._on_param_changed)
        self.workers_spin.valueChanged.connect(self._on_param_changed)
        self.device_combo.currentTextChanged.connect(self._on_param_changed)
        
        # 高级参数 - 复选框和值变化都触发命令更新
        for check in self.param_checks.values():
            check.toggled.connect(self._on_param_changed)
        for name, widget in self.param_widgets.items():
            # 跳过 checkbox 类型的参数 (amp, multi_scale)
            if widget == self.param_checks.get(name):
                continue
            if isinstance(widget, (FocusSpinBox, FocusDoubleSpinBox)):
                widget.valueChanged.connect(self._on_param_changed)
            elif isinstance(widget, FocusComboBox):
                widget.currentTextChanged.connect(self._on_param_changed)
        
        # 训练控制
        self.start_btn.clicked.connect(self._start_training)
        self.stop_btn.clicked.connect(self._stop_training)
        self.clear_terminal_btn.clicked.connect(self.terminal.clear)
        
        # 训练管理器信号
        self._manager.raw_output.connect(self._on_raw_output)
        self._manager.system_msg.connect(self._on_system_msg)
        self._manager.finished.connect(self._on_training_finished)
    
    def _apply_styles(self) -> None:
        """应用样式"""
        self.terminal.setObjectName("terminalOutput")
    
    # ============================================================
    # 槽函数
    # ============================================================
    
    @Slot()
    def _scan_envs(self) -> None:
        """Scan Conda environments in the background."""
        # Disable the button to avoid duplicate scans.
        self.scan_env_btn.setEnabled(False)
        self.scan_env_btn.setText("扫描中...")
        self.python_combo.clear()
        self.python_combo.addItem("正在扫描环境...")
        
        def do_scan():
            """Run the environment scan on a worker thread."""
            return self._manager.detect_conda_envs()

        worker = run_in_thread(
            do_scan,
            on_finished=lambda envs: self._handle_env_scan_finished(worker, envs),
            on_error=lambda err_info: self._handle_env_scan_error(worker, err_info),
        )
        self._scan_worker = worker

    def _handle_env_scan_finished(self, worker: Worker, envs) -> None:
        """Apply scan results if this worker is still current."""
        if self._scan_worker is not worker:
            return

        self._scan_worker = None
        self.python_combo.clear()
        for env_name, python_path in envs:
            # Show the environment name and keep the python path in userData.
            self.python_combo.addItem(env_name, userData=python_path)
        self.log_message.emit(f"扫描到 {len(envs)} 个 Python 环境")
        self.scan_env_btn.setEnabled(True)
        self.scan_env_btn.setText("扫描")

    def _handle_env_scan_error(self, worker: Worker, err_info) -> None:
        """Ignore late errors from outdated scan workers."""
        if self._scan_worker is not worker:
            return

        self._scan_worker = None
        self.python_combo.clear()
        self.log_message.emit(f"环境扫描失败: {err_info[1]}")
        self.scan_env_btn.setEnabled(True)
        self.scan_env_btn.setText("扫描")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Detach scan callbacks when the widget is closing."""
        if self._scan_worker is not None:
            self._scan_worker.cancel()
            self._scan_worker = None
        super().closeEvent(event)

    @Slot()
    def _browse_model(self) -> None:
        """浏览模型文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择模型文件", "", "PyTorch 模型 (*.pt);;所有文件 (*)"
        )
        if path:
            self.model_input.setText(path)
    
    @Slot()
    def _browse_data(self) -> None:
        """浏览数据配置文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择数据配置", "", "YAML 文件 (*.yaml *.yml);;所有文件 (*)"
        )
        if path:
            self.data_input.setText(path)
    
    @Slot(bool)
    def _toggle_advanced(self, checked: bool) -> None:
        """切换高级参数显示"""
        self.advanced_container.setVisible(checked)
        self.advanced_toggle.setText("▲ 收起高级参数" if checked else "▼ 展开高级参数")
    
    @Slot()
    def _on_param_changed(self) -> None:
        """参数变化时生成命令"""
        self._generate_command()
    
    def _generate_command(self) -> None:
        """生成训练命令"""
        # 优先从 userData 获取完整路径，如果用户手动输入则使用文本
        python = self.python_combo.currentData()
        if not python:
            python = self.python_combo.currentText().strip()
        model = self.model_input.text().strip()
        data = self.data_input.text().strip()
        
        # 构建命令
        cmd_parts = [
            f'"{python}"' if " " in python else python,
            "-m", "ultralytics", "train",
            f'model="{model}"' if model else "",
            f'data="{data}"' if data else "",
            f"epochs={self.epochs_spin.value()}",
            f"batch={self.batch_spin.value()}",
            f"imgsz={self.imgsz_spin.value()}",
            f"workers={self.workers_spin.value()}",
            f"device={self.device_combo.currentText()}",
        ]
        
        # 高级参数 (只添加勾选的参数)
        for param_name, check in self.param_checks.items():
            if not check.isChecked():
                continue
            
            widget = self.param_widgets.get(param_name)
            
            # 特殊处理: 布尔类型参数 (amp, multi_scale)
            if param_name in ("amp", "multi_scale"):
                cmd_parts.append(f"{param_name}=True")
            # ComboBox 参数
            elif isinstance(widget, FocusComboBox):
                value = widget.currentText()
                # 特殊处理: optimizer=auto 不需要添加
                if param_name == "optimizer" and value == "auto":
                    continue
                # 特殊处理: cache=False 不需要添加
                if param_name == "cache" and value == "False":
                    continue
                cmd_parts.append(f"{param_name}={value}")
            # 数值类型参数
            elif isinstance(widget, (FocusSpinBox, FocusDoubleSpinBox)):
                cmd_parts.append(f"{param_name}={widget.value()}")
        
        # 过滤空值并组合
        cmd = " ".join(part for part in cmd_parts if part)
        
        # 临时禁用信号避免循环
        self.command_preview.blockSignals(True)
        self.command_preview.setPlainText(cmd)
        self.command_preview.blockSignals(False)
    
    @Slot()
    def _start_training(self) -> None:
        """开始训练"""
        command = self.command_preview.toPlainText().strip()
        
        if not command:
            self.log_message.emit("请先配置训练参数")
            return
        
        # 验证必要路径
        data_path = self.data_input.text().strip()
        if not data_path:
            self.log_message.emit("请选择数据配置文件 (.yaml)")
            return
        
        # 确定工作目录
        if Path(data_path).exists():
            work_dir = str(Path(data_path).parent)
        else:
            work_dir = str(Path.cwd())
        
        # 清空终端
        self.terminal.clear()
        
        # 启动训练
        success = self._manager.start_training(command, work_dir)
        
        if success:
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
    
    @Slot()
    def _stop_training(self) -> None:
        """停止训练"""
        self._manager.stop_training()
    
    @Slot(str)
    def _on_raw_output(self, text: str) -> None:
        """处理原始输出 → 终端"""
        self.terminal.insertPlainText(text)
        # 自动滚动到底部
        scrollbar = self.terminal.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    @Slot(str, str)
    def _on_system_msg(self, msg: str, level: str) -> None:
        """处理系统消息 → 全局日志"""
        self.log_message.emit(f"[训练] {msg}")
    
    @Slot()
    def _on_training_finished(self) -> None:
        """训练结束"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
