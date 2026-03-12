"""
_tabs_edit.py - EditTabMixin: 编辑 Tab UI + 逻辑
============================================
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.data_handler import (
    DataWorker,
    LabelFormat,
    ModifyAction,
    ValidateResult,
)
from ui.path_input_group import PathInputGroup
from ui.styled_message_box import StyledMessageBox, StyledProgressDialog


class EditTabMixin:
    """编辑 Tab 的 UI 构建 + 槽函数 + 预检查基础设施"""

    # ==================== UI 构建 ====================

    def _create_edit_tab(self) -> QWidget:
        """
        创建编辑 Tab (路径区 + 2×2 对称布局)

        顶部: 路径输入组
        下方:
            左列: 生成空标签 / 格式互转
            右列: 修改/删除标签 / 标签校验
        """
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        # 用 QScrollArea 包裹所有内容，防止日志面板展开时被压缩
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)

        # 路径输入组
        self.edit_path_group = PathInputGroup(
            show_image_dir=True,
            show_label_dir=True,
            show_classes=True,
            group_title="数据源路径",
        )
        scroll_layout.addWidget(self.edit_path_group)

        # 下方内容区 (2×2 网格布局，确保左右对称)
        content_grid = QGridLayout()
        content_grid.setHorizontalSpacing(15)
        content_grid.setVerticalSpacing(10)
        content_grid.setColumnStretch(0, 1)
        content_grid.setColumnStretch(1, 1)

        # ---- GroupBox 1: 生成空标签 ----
        gen_group = QGroupBox("生成空标签")
        gen_layout = QVBoxLayout(gen_group)

        self.empty_txt_radio = QRadioButton("TXT (YOLO)")
        self.empty_xml_radio = QRadioButton("XML (VOC)")
        self.empty_txt_radio.setChecked(True)

        self.empty_format_group = QButtonGroup(self)
        self.empty_format_group.addButton(self.empty_txt_radio, 0)
        self.empty_format_group.addButton(self.empty_xml_radio, 1)

        gen_layout.addWidget(self.empty_txt_radio)
        gen_layout.addWidget(self.empty_xml_radio)

        # 操作按钮 (右对齐)
        gen_btn_layout = QHBoxLayout()
        gen_btn_layout.addStretch()
        self.gen_empty_btn = QPushButton("📝 生成空标签")
        self.gen_empty_btn.setMinimumHeight(35)
        self.gen_empty_btn.setMinimumWidth(120)
        self.gen_empty_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.gen_empty_btn.setEnabled(False)
        gen_btn_layout.addWidget(self.gen_empty_btn)
        gen_layout.addLayout(gen_btn_layout)

        content_grid.addWidget(gen_group, 0, 0)

        # ---- GroupBox 2: 格式互转 ----
        convert_group = QGroupBox("格式互转")
        convert_layout = QVBoxLayout(convert_group)

        self.txt_to_xml_radio = QRadioButton("TXT (YOLO) → XML (VOC)")
        self.xml_to_txt_radio = QRadioButton("XML (VOC) → TXT (YOLO)")
        self.txt_to_xml_radio.setChecked(True)

        self.convert_group = QButtonGroup(self)
        self.convert_group.addButton(self.txt_to_xml_radio, 0)
        self.convert_group.addButton(self.xml_to_txt_radio, 1)

        convert_layout.addWidget(self.txt_to_xml_radio)
        convert_layout.addWidget(self.xml_to_txt_radio)

        # 操作按钮 (右对齐)
        convert_btn_layout = QHBoxLayout()
        convert_btn_layout.addStretch()
        self.convert_btn = QPushButton("🔄 执行转换")
        self.convert_btn.setMinimumHeight(35)
        self.convert_btn.setMinimumWidth(120)
        self.convert_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.convert_btn.setProperty("class", "success")
        self.convert_btn.setEnabled(False)
        convert_btn_layout.addWidget(self.convert_btn)
        convert_layout.addLayout(convert_btn_layout)

        content_grid.addWidget(convert_group, 1, 0)

        # ---- GroupBox 3: 修改/删除标签 ----
        right_group = QGroupBox("修改/删除标签")
        right_layout = QVBoxLayout(right_group)

        # 操作类型
        action_label = QLabel("操作类型:")
        right_layout.addWidget(action_label)

        action_row = QHBoxLayout()
        self.replace_radio = QRadioButton("替换类别")
        self.remove_radio = QRadioButton("删除类别")
        self.replace_radio.setChecked(True)

        self.action_group = QButtonGroup(self)
        self.action_group.addButton(self.replace_radio, 0)
        self.action_group.addButton(self.remove_radio, 1)

        action_row.addWidget(self.replace_radio)
        action_row.addWidget(self.remove_radio)
        action_row.addStretch()
        right_layout.addLayout(action_row)

        # 输入字段
        form_layout = QFormLayout()
        self.old_name_input = QComboBox()
        self.old_name_input.setEditable(True)
        self.old_name_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.old_name_input.lineEdit().setPlaceholderText("原类别名称或 ID")
        form_layout.addRow("原类别/ID:", self.old_name_input)

        self._new_name_label = QLabel("新类别/ID:")
        self.new_name_input = QComboBox()
        self.new_name_input.setEditable(True)
        self.new_name_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.new_name_input.lineEdit().setPlaceholderText("新类别名称或 ID (留空表示删除)")
        form_layout.addRow(self._new_name_label, self.new_name_input)
        right_layout.addLayout(form_layout)

        # 备份选项
        self.backup_check = QCheckBox("修改前备份原文件 (.bak)")
        self.backup_check.setChecked(True)
        right_layout.addWidget(self.backup_check)

        # 操作按钮 (右对齐)
        btn_layout2 = QHBoxLayout()
        btn_layout2.addStretch()
        self.modify_btn = QPushButton("⚡ 执行修改")
        self.modify_btn.setMinimumHeight(35)
        self.modify_btn.setMinimumWidth(120)
        self.modify_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.modify_btn.setEnabled(False)
        btn_layout2.addWidget(self.modify_btn)
        right_layout.addLayout(btn_layout2)

        content_grid.addWidget(right_group, 0, 1)

        # ---- GroupBox 4: 标签校验 ----
        validate_group = QGroupBox("标签校验")
        validate_layout = QVBoxLayout(validate_group)

        self.validate_coords_check = QCheckBox("坐标越界检查")
        self.validate_coords_check.setChecked(True)
        self.validate_coords_check.setToolTip(
            "TXT: 检查 x, y, w, h ∈ [0, 1]\n"
            "XML: 检查 bbox 不超出图片尺寸"
        )
        validate_layout.addWidget(self.validate_coords_check)

        self.validate_class_check = QCheckBox("类别 ID 无效检查")
        self.validate_class_check.setChecked(True)
        self.validate_class_check.setToolTip(
            "TXT: 类别 ID 超出 classes.txt 范围\n"
            "XML: 类别名不在 classes.txt 中"
        )
        validate_layout.addWidget(self.validate_class_check)

        self.validate_format_check = QCheckBox("格式错误检查")
        self.validate_format_check.setChecked(True)
        self.validate_format_check.setToolTip(
            "TXT: 行字段数 ≠ 5\n"
            "XML: 缺少必要节点 (size, bndbox)"
        )
        validate_layout.addWidget(self.validate_format_check)

        self.validate_orphan_check = QCheckBox("清理孤立标签")
        self.validate_orphan_check.setChecked(True)
        self.validate_orphan_check.setToolTip(
            "查找无对应图片的标签文件\n"
            "校验后可选择备份清理"
        )
        validate_layout.addWidget(self.validate_orphan_check)

        # 操作按钮 (右对齐)
        validate_btn_layout = QHBoxLayout()
        validate_btn_layout.addStretch()
        self.validate_btn = QPushButton("🔍 开始校验")
        self.validate_btn.setMinimumHeight(35)
        self.validate_btn.setMinimumWidth(120)
        self.validate_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.validate_btn.setProperty("class", "primary")
        self.validate_btn.setEnabled(False)
        validate_btn_layout.addWidget(self.validate_btn)
        validate_layout.addLayout(validate_btn_layout)

        content_grid.addWidget(validate_group, 1, 1)

        scroll_layout.addLayout(content_grid, 0)  # 不拉伸，自然高度
        scroll_layout.addStretch(1)  # 剩余空间推到底部

        # 将内容装入滚动区域
        scroll_area.setWidget(scroll_content)
        tab_layout.addWidget(scroll_area)

        return tab

    # ==================== 编辑状态管理 ====================

    def _update_edit_action_states(self) -> None:
        """根据路径输入状态更新编辑按钮"""
        img_path = self.edit_path_group.get_image_dir()
        has_image_dir = bool(img_path and img_path.exists())
        is_busy = bool(self._worker and self._worker.isRunning())
        enabled = has_image_dir and not is_busy

        self.gen_empty_btn.setEnabled(enabled)
        self.convert_btn.setEnabled(enabled)
        self.modify_btn.setEnabled(enabled)
        self.validate_btn.setEnabled(enabled)

        # 类别 ID 检查需要 classes.txt
        classes_path = self.edit_path_group.get_classes_path()
        has_classes = bool(classes_path and classes_path.exists())
        self.validate_class_check.setEnabled(has_classes)
        if not has_classes:
            self.validate_class_check.setChecked(False)
            self.validate_class_check.setToolTip("需要先加载 classes.txt 文件")
        else:
            self.validate_class_check.setToolTip(
                "TXT: 类别 ID 超出 classes.txt 范围\n"
                "XML: 类别名不在 classes.txt 中"
            )

    def _apply_edit_class_options(self, options: list[str]) -> None:
        """应用修改标签下拉选项并保留当前输入"""
        old_value = self.old_name_input.currentText().strip()
        new_value = self.new_name_input.currentText().strip()

        self.old_name_input.blockSignals(True)
        self.new_name_input.blockSignals(True)

        self.old_name_input.clear()
        self.new_name_input.clear()

        if options:
            self.old_name_input.addItems(options)
            self.new_name_input.addItems(options)

        self.old_name_input.setCurrentText(old_value)
        self.new_name_input.setCurrentText(new_value)

        self.old_name_input.blockSignals(False)
        self.new_name_input.blockSignals(False)

    def _refresh_edit_class_options(self) -> None:
        """刷新修改标签下拉选项 (轻量模式)"""
        classes_txt = self.edit_path_group.get_classes_path()
        if classes_txt and classes_txt.exists():
            self._apply_edit_class_options(self._handler.load_classes_txt(classes_txt))
        elif self.detected_classes:
            self._apply_edit_class_options(self.detected_classes)
        else:
            self._apply_edit_class_options([])

    def _resolve_modify_action(self) -> ModifyAction:
        """根据当前输入解析修改动作"""
        new_value = self.new_name_input.currentText().strip()
        if self.remove_radio.isChecked() or not new_value:
            return ModifyAction.REMOVE
        return ModifyAction.REPLACE

    def _show_modify_warning(self, message: str) -> None:
        """修改功能警告弹窗"""
        StyledMessageBox.warning(self, "修改标签", message)

    def _show_modify_info(self, title: str, message: str) -> None:
        """修改功能信息弹窗"""
        StyledMessageBox.information(self, title, message)

    def _confirm_edit_action(self, title: str, message: str) -> bool:
        """显示确认弹窗"""
        return StyledMessageBox.question(self, title, message)

    # ==================== 预检查基础设施 ====================

    def _invalidate_edit_precheck_cache(self, *_args) -> None:
        """清除编辑页最近一次预检查缓存"""
        self._edit_precheck_cache = None

    def _get_edit_precheck_cache(self, cache_key: tuple) -> Optional[object]:
        """获取有效的编辑预检查缓存"""
        if not self._edit_precheck_cache:
            return None

        if self._edit_precheck_cache.get("key") != cache_key:
            return None

        timestamp = self._edit_precheck_cache.get("timestamp", 0.0)
        if time.monotonic() - timestamp > self._edit_precheck_cache_ttl:
            self._edit_precheck_cache = None
            return None

        return self._edit_precheck_cache.get("result")

    def _set_edit_precheck_cache(self, cache_key: tuple, result: object) -> None:
        """保存编辑页最近一次预检查结果"""
        self._edit_precheck_cache = {
            "key": cache_key,
            "timestamp": time.monotonic(),
            "result": result,
        }

    def _cancel_precheck(self) -> None:
        """取消正在进行的预检查"""
        if not (self._worker and self._worker.isRunning()):
            return

        self._precheck_cancelled = True
        self._worker.request_interrupt()
        self.log_message.emit("正在取消预检查...")

    @Slot(int, int)
    def _on_precheck_progress(self, current: int, total: int) -> None:
        """更新预检查进度弹窗"""
        dialog = self._precheck_dialog
        if dialog is None:
            return

        maximum = max(total, 1)
        try:
            if dialog.maximum() == 0:
                dialog.setRange(0, maximum)
            dialog.setMaximum(maximum)
            dialog.setValue(min(current, maximum))
            dialog.setLabelText(f"{self._precheck_dialog_text}\n{current}/{maximum}")
        except RuntimeError:
            return

    def _cleanup_precheck_dialog(self) -> None:
        """关闭预检查进度弹窗"""
        dialog = self._precheck_dialog
        self._precheck_dialog = None
        if dialog is None:
            return

        try:
            dialog.canceled.disconnect(self._cancel_precheck)
        except (RuntimeError, TypeError):
            pass

        dialog.blockSignals(True)
        dialog.close()
        dialog.deleteLater()
        self._precheck_dialog_text = ""

    def _on_precheck_result(self, result: object) -> None:
        """保存预检查结果，等待线程收尾后再确认"""
        if self._precheck_cancelled:
            return

        self._pending_precheck_result = result

    def _on_precheck_error(self, error: str) -> None:
        """记录预检查错误"""
        self._pending_precheck_error = error

    @Slot()
    def _on_precheck_finished(self) -> None:
        """预检查线程完成后做清理和确认"""
        self._set_ui_busy(False)
        self._cleanup_precheck_dialog()

        worker = self._worker
        self._worker = None
        if worker:
            worker.deleteLater()

        if self._precheck_cancelled:
            self._pending_precheck_result = None
            self._pending_precheck_handler = None
            self._pending_precheck_cache_key = None
            self._pending_precheck_error = None
            self._pending_precheck_title = ""
            self.log_message.emit("已取消预检查")
            return

        if self._pending_precheck_error:
            StyledMessageBox.warning(self, self._pending_precheck_title or "预检查", self._pending_precheck_error)
            self._pending_precheck_result = None
            self._pending_precheck_handler = None
            self._pending_precheck_cache_key = None
            self._pending_precheck_error = None
            self._pending_precheck_title = ""
            return

        result = self._pending_precheck_result
        handler = self._pending_precheck_handler
        cache_key = self._pending_precheck_cache_key

        self._pending_precheck_result = None
        self._pending_precheck_handler = None
        self._pending_precheck_cache_key = None
        self._pending_precheck_error = None
        self._pending_precheck_title = ""

        if result is not None and handler:
            if cache_key is not None:
                self._set_edit_precheck_cache(cache_key, result)
            handler(result)

    def _start_precheck_worker(
        self,
        *,
        title: str,
        label_text: str,
        cache_key: tuple,
        task,
        on_ready: Callable[[object], None],
    ) -> None:
        """启动后台预检查，并在完成后弹出确认框"""
        cached_result = self._get_edit_precheck_cache(cache_key)
        if cached_result is not None:
            on_ready(cached_result)
            return

        if self._worker and self._worker.isRunning():
            self.log_message.emit("已有任务在运行中")
            return

        self._precheck_cancelled = False
        self._pending_precheck_result = None
        self._pending_precheck_handler = on_ready
        self._pending_precheck_cache_key = cache_key
        self._pending_precheck_error = None
        self._pending_precheck_title = title

        self._precheck_dialog = StyledProgressDialog(self, title, label_text, "取消")
        self._precheck_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._precheck_dialog.setRange(0, 0)
        self._precheck_dialog.setValue(0)
        self._precheck_dialog_text = label_text
        self._precheck_dialog.canceled.connect(self._cancel_precheck)

        self._worker = DataWorker(self)
        self._worker.set_task(task)
        self._worker.progress.connect(self._on_precheck_progress)
        self._worker.result_ready.connect(self._on_precheck_result)
        self._worker.error.connect(self._on_precheck_error)
        self._worker.finished.connect(self._on_precheck_finished)

        self._set_ui_busy(True, enable_cancel=False)
        self.log_message.emit(label_text)
        self._precheck_dialog.show()
        self._worker.start()

    # ==================== 编辑操作确认 (预检查后) ====================

    def _confirm_generate_empty_after_precheck(
        self,
        preview: dict,
        img_path: Path,
        label_path: Optional[Path],
        label_format: LabelFormat,
    ) -> None:
        """根据预检查结果确认是否生成空标签"""
        total_images = preview.get("total_images", 0)
        missing_labels = preview.get("missing_labels", 0)
        format_text = "TXT (YOLO)" if label_format == LabelFormat.TXT else "XML (VOC)"

        if total_images == 0:
            StyledMessageBox.information(self, "生成空标签", "未找到可检查的图片文件。")
            return

        if missing_labels == 0:
            StyledMessageBox.information(self, "生成空标签", "未发现缺失标签图片，无需生成空标签。")
            return

        message = (
            f"将检查 {total_images} 张图片。\n"
            f"预计生成 {missing_labels} 个空标签。\n"
            f"标签格式: {format_text}\n\n"
            "是否继续执行？"
        )
        if not self._confirm_edit_action("生成空标签", message):
            return

        self._start_worker(
            lambda: self._handler.generate_missing_labels(
                img_path,
                label_format,
                label_dir=label_path,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_generate_empty_finished,
        )

    def _confirm_convert_after_precheck(
        self,
        preview: dict,
        img_path: Path,
        label_path: Optional[Path],
        to_xml: bool,
    ) -> None:
        """根据预检查结果确认是否执行格式转换"""
        total_labels = preview.get("total_labels", 0)
        source_type = preview.get("source_type", "TXT")
        target_type = preview.get("target_type", "XML")
        output_dir_name = preview.get("output_dir_name", "")

        if total_labels == 0:
            StyledMessageBox.information(self, "格式互转", f"未找到可转换的 {source_type} 标签文件。")
            return

        message = (
            f"将转换 {total_labels} 个 {source_type} 标签文件。\n"
            f"输出格式: {target_type}\n"
            f"输出目录: {output_dir_name}\n\n"
            "是否继续执行？"
        )
        if not self._confirm_edit_action("格式互转", message):
            return

        classes = None
        classes_txt = self.edit_path_group.get_classes_path()
        if classes_txt and classes_txt.exists():
            classes = self._handler.load_classes_txt(classes_txt)
        elif self.detected_classes:
            classes = self.detected_classes

        dataset_root = self._resolve_dataset_root(img_path, label_path)
        self._start_worker(
            lambda: self._handler.convert_format(
                dataset_root,
                to_xml=to_xml,
                classes=classes,
                label_dir=label_path,
                image_dir=img_path,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_convert_format_finished,
        )

    def _confirm_modify_after_precheck(
        self,
        preview: dict,
        search_dir: Path,
        action: ModifyAction,
        old_value: str,
        new_value: str,
        classes_txt: Optional[Path],
        image_dir: Optional[Path],
        label_dir: Optional[Path],
    ) -> None:
        """根据预检查结果确认是否执行标签修改"""
        total_label_files = preview.get("total_label_files", 0)
        txt_files = preview.get("txt_files", 0)
        xml_files = preview.get("xml_files", 0)
        matched_files = preview.get("matched_files", 0)
        matched_annotations = preview.get("matched_annotations", 0)
        backup_enabled = self.backup_check.isChecked()

        if total_label_files == 0:
            self._show_modify_info("修改标签", "未找到可修改的标签文件。")
            return

        if matched_annotations == 0:
            self._show_modify_info("修改标签", f"未找到与\u201c{old_value}\u201d匹配的标注。")
            return

        action_text = "替换类别" if action == ModifyAction.REPLACE else "删除类别"
        target_text = f"\n新类别/ID: {new_value}" if action == ModifyAction.REPLACE else ""
        backup_text = "开" if backup_enabled else "关"
        message = (
            f"将检查 {total_label_files} 个标签文件 (TXT {txt_files} / XML {xml_files})。\n"
            f"预计影响 {matched_files} 个文件 / {matched_annotations} 条标注。\n"
            f"操作: {action_text}\n"
            f"原类别/ID: {old_value}"
            f"{target_text}\n"
            f"备份: {backup_text}\n\n"
            "是否继续执行？"
        )
        if not self._confirm_edit_action("修改标签", message):
            return

        self._start_worker(
            lambda: self._handler.modify_labels(
                search_dir,
                action,
                old_value,
                new_value,
                backup=backup_enabled,
                classes_txt=classes_txt,
                image_dir=image_dir,
                label_dir=label_dir,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_modify_labels_finished,
        )

    # ==================== 编辑槽函数 ====================

    @Slot()
    def _on_generate_empty(self) -> None:
        """生成空标签"""
        img_path = self.edit_path_group.get_image_dir()
        if not img_path:
            self.log_message.emit("请先选择图片目录")
            return

        if not img_path.exists():
            self.log_message.emit(f"图片目录不存在: {img_path}")
            return

        label_path = self.edit_path_group.get_label_dir()
        label_format = LabelFormat.TXT if self.empty_txt_radio.isChecked() else LabelFormat.XML
        cache_key = (
            "generate_empty",
            str(img_path),
            str(label_path) if label_path else "",
            label_format.value,
        )

        self._start_precheck_worker(
            title="生成空标签",
            label_text="正在检查缺失标签...",
            cache_key=cache_key,
            task=lambda: self._handler.preview_generate_missing_labels(
                img_path,
                label_dir=label_path,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
            ),
            on_ready=lambda result: self._confirm_generate_empty_after_precheck(
                result,
                img_path,
                label_path,
                label_format,
            ),
        )

    @Slot()
    def _on_convert_format(self) -> None:
        """执行格式转换"""
        img_path = self.edit_path_group.get_image_dir()
        if not img_path:
            self.log_message.emit("请先选择图片目录")
            return

        if not img_path.exists():
            self.log_message.emit(f"图片目录不存在: {img_path}")
            return

        label_path = self.edit_path_group.get_label_dir()
        dataset_root = self._resolve_dataset_root(img_path, label_path)
        to_xml = self.txt_to_xml_radio.isChecked()
        cache_key = (
            "convert_format",
            str(img_path),
            str(label_path) if label_path else "",
            "to_xml" if to_xml else "to_txt",
        )

        self._start_precheck_worker(
            title="格式互转",
            label_text="正在检查可转换的标签文件...",
            cache_key=cache_key,
            task=lambda: self._handler.preview_convert_format(
                dataset_root,
                to_xml=to_xml,
                label_dir=label_path,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
            ),
            on_ready=lambda result: self._confirm_convert_after_precheck(
                result,
                img_path,
                label_path,
                to_xml,
            ),
        )

    @Slot()
    def _on_modify_labels(self) -> None:
        """修改标签"""
        img_path = self.edit_path_group.get_image_dir()
        if not img_path:
            self._show_modify_warning("请先选择图片目录")
            return

        if not img_path.exists():
            self._show_modify_warning(f"图片目录不存在:\n{img_path}")
            return

        old_value = self.old_name_input.currentText().strip()
        if not old_value:
            self._show_modify_warning("请输入原类别名称或 ID")
            return

        new_value = self.new_name_input.currentText().strip()
        action = self._resolve_modify_action()

        label_path = self.edit_path_group.get_label_dir()
        dataset_root = self._resolve_dataset_root(img_path, label_path)
        has_explicit_label_dir = bool(label_path and label_path.exists())
        search_dir = label_path if has_explicit_label_dir else dataset_root
        image_scope = None if has_explicit_label_dir else img_path

        classes_txt = self.edit_path_group.get_classes_path()
        cache_key = (
            "modify_labels",
            str(search_dir),
            str(image_scope) if image_scope else "",
            str(classes_txt) if classes_txt else "",
            action.value,
            old_value,
            new_value,
            self.backup_check.isChecked(),
        )

        self._start_precheck_worker(
            title="修改标签",
            label_text="正在检查将受影响的标签文件...",
            cache_key=cache_key,
            task=lambda: self._handler.preview_modify_labels(
                search_dir,
                action,
                old_value,
                new_value,
                classes_txt=classes_txt,
                image_dir=image_scope,
                label_dir=label_path,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
            ),
            on_ready=lambda result: self._confirm_modify_after_precheck(
                result,
                search_dir,
                action,
                old_value,
                new_value,
                classes_txt,
                image_scope,
                label_path,
            ),
        )

    def _on_generate_empty_finished(self, count: int) -> None:
        """生成空标签完成回调"""
        self._invalidate_edit_precheck_cache()
        self.log_message.emit(f"已生成 {count} 个空标签文件")

    def _on_convert_format_finished(self, count: int) -> None:
        """格式转换完成回调"""
        self._invalidate_edit_precheck_cache()
        self.log_message.emit(f"格式转换完成: 成功 {count} 个文件")

    def _on_modify_labels_finished(self, count: int) -> None:
        """修改标签完成回调"""
        self._invalidate_edit_precheck_cache()
        self.log_message.emit(f"已修改 {count} 个标签文件")
        self._show_modify_info("修改完成", f"已修改 {count} 个标签文件。")

    @Slot()
    def _on_validate_labels(self) -> None:
        """启动标签校验后台任务"""
        img_path = self.edit_path_group.get_image_dir()
        if not img_path or not img_path.exists():
            self.log_message.emit("请先选择有效的图片目录")
            return

        label_path = self.edit_path_group.get_label_dir()
        classes_txt = self.edit_path_group.get_classes_path()

        check_coords = self.validate_coords_check.isChecked()
        check_class_ids = (
            self.validate_class_check.isChecked()
            and self.validate_class_check.isEnabled()
        )
        check_format = self.validate_format_check.isChecked()
        check_orphans = self.validate_orphan_check.isChecked()

        if not any([check_coords, check_class_ids, check_format, check_orphans]):
            self.log_message.emit("请至少勾选一项校验内容")
            return

        self.log_message.emit("开始标签校验...")

        self._start_worker(
            lambda: self._handler.validate_labels(
                img_path,
                label_dir=label_path,
                classes_txt=classes_txt,
                check_coords=check_coords,
                check_class_ids=check_class_ids,
                check_format=check_format,
                check_orphans=check_orphans,
                interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                progress_callback=self._emit_progress,
                message_callback=self._emit_message,
            ),
            on_finished=self._on_validate_finished,
        )

    def _on_validate_finished(self, result: ValidateResult) -> None:
        """标签校验完成回调 — 弹窗摘要 + 日志详情 + 孤立标签清理确认"""
        lines = [f"扫描标签文件: {result.total_labels}"]
        if result.coord_errors:
            lines.append(f"  坐标越界: {len(result.coord_errors)} 处")
        if result.class_errors:
            lines.append(f"  类别无效: {len(result.class_errors)} 处")
        if result.format_errors:
            lines.append(f"  格式错误: {len(result.format_errors)} 处")
        if result.orphan_labels:
            lines.append(f"  孤立标签: {len(result.orphan_labels)} 个")

        self.log_message.emit("=" * 40)
        self.log_message.emit("标签校验完成:")
        for line in lines:
            self.log_message.emit(line)

        # 输出详细问题到日志
        if result.coord_errors:
            self.log_message.emit("--- 坐标越界详情 ---")
            for path, loc, reason in result.coord_errors[:50]:
                self.log_message.emit(f"  {path.name} [{loc}]: {reason}")
            if len(result.coord_errors) > 50:
                self.log_message.emit(f"  ... 共 {len(result.coord_errors)} 处 (仅显示前 50)")

        if result.class_errors:
            self.log_message.emit("--- 类别无效详情 ---")
            for path, loc, reason in result.class_errors[:50]:
                self.log_message.emit(f"  {path.name} [{loc}]: {reason}")
            if len(result.class_errors) > 50:
                self.log_message.emit(f"  ... 共 {len(result.class_errors)} 处 (仅显示前 50)")

        if result.format_errors:
            self.log_message.emit("--- 格式错误详情 ---")
            for path, reason in result.format_errors[:50]:
                self.log_message.emit(f"  {path.name}: {reason}")
            if len(result.format_errors) > 50:
                self.log_message.emit(f"  ... 共 {len(result.format_errors)} 处 (仅显示前 50)")

        if result.orphan_labels:
            self.log_message.emit("--- 孤立标签列表 ---")
            for path in result.orphan_labels[:50]:
                self.log_message.emit(f"  {path.name}")
            if len(result.orphan_labels) > 50:
                self.log_message.emit(f"  ... 共 {len(result.orphan_labels)} 个 (仅显示前 50)")

        if not result.has_issues:
            StyledMessageBox.information(self, "校验通过", "所有标签文件校验通过，未发现问题。✅")
            return

        StyledMessageBox.warning(
            self,
            "校验完成",
            f"发现 {result.issue_count} 个问题，请查看日志面板了解详情。",
        )

        # 孤立标签清理确认
        if result.orphan_labels:
            confirm = StyledMessageBox.question(
                self,
                "清理孤立标签",
                f"发现 {len(result.orphan_labels)} 个孤立标签文件 (无对应图片)。\n"
                f"是否备份后删除这些文件？",
                accept_text="备份并删除",
                reject_text="跳过",
            )
            if confirm:
                self.log_message.emit("开始清理孤立标签...")
                self._start_worker(
                    lambda: self._handler.clean_orphan_labels(
                        result.orphan_labels,
                        backup=True,
                        interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                        progress_callback=self._emit_progress,
                        message_callback=self._emit_message,
                    ),
                    on_finished=lambda count: self.log_message.emit(
                        f"孤立标签清理完成: 已处理 {count} 个文件"
                    ),
                )

    @Slot(bool)
    def _on_action_changed(self, checked: bool) -> None:
        """操作类型切换: 删除模式时隐藏新名称输入框和标签"""
        self.new_name_input.setVisible(not checked)
        self.new_name_input.setEnabled(not checked)
        self._new_name_label.setVisible(not checked)
        self._invalidate_edit_precheck_cache()
