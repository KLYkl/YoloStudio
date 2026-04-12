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

from ui.focus_widgets import FocusComboBox

from core.data_handler import (
    DataWorker,
    LabelFormat,
    ModifyAction,
    ValidateResult,
)
from ui.styled_message_box import StyledMessageBox, StyledProgressDialog
from utils.i18n import t


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
        scroll_layout.setSpacing(6)

        # 路径输入组已提升到 DataWidget 外层 (self.path_group)

        # 下方内容区 (2×2 网格布局，确保左右对称)
        content_grid = QGridLayout()
        content_grid.setHorizontalSpacing(8)
        content_grid.setVerticalSpacing(6)
        content_grid.setColumnStretch(0, 1)
        content_grid.setColumnStretch(1, 1)

        # ---- GroupBox 1: 生成空标签 ----
        gen_group = QGroupBox(t("edit_gen_empty_labels"))
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
        self.gen_empty_btn = QPushButton(t("edit_gen_empty_btn"))
        self.gen_empty_btn.setMinimumHeight(28)
        self.gen_empty_btn.setMinimumWidth(100)
        self.gen_empty_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.gen_empty_btn.setEnabled(False)
        gen_btn_layout.addWidget(self.gen_empty_btn)
        gen_layout.addLayout(gen_btn_layout)

        content_grid.addWidget(gen_group, 0, 0)

        # ---- GroupBox 2: 格式互转 ----
        convert_group = QGroupBox(t("edit_convert_format"))
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
        self.convert_btn = QPushButton(t("edit_convert_btn"))
        self.convert_btn.setMinimumHeight(28)
        self.convert_btn.setMinimumWidth(100)
        self.convert_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.convert_btn.setProperty("class", "success")
        self.convert_btn.setEnabled(False)
        convert_btn_layout.addWidget(self.convert_btn)
        convert_layout.addLayout(convert_btn_layout)

        content_grid.addWidget(convert_group, 1, 0)

        # ---- GroupBox 3: 修改/删除标签 ----
        right_group = QGroupBox(t("edit_modify_labels"))
        right_layout = QVBoxLayout(right_group)

        # 操作类型
        action_label = QLabel(t("edit_action_type"))
        right_layout.addWidget(action_label)

        action_row = QHBoxLayout()
        self.replace_radio = QRadioButton(t("edit_replace_class"))
        self.remove_radio = QRadioButton(t("edit_remove_class"))
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
        self.old_name_input = FocusComboBox()
        self.old_name_input.setEditable(True)
        self.old_name_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.old_name_input.lineEdit().setPlaceholderText(t("edit_old_name_placeholder"))
        form_layout.addRow(t("edit_old_name_label"), self.old_name_input)

        self._new_name_label = QLabel(t("edit_new_name_label"))
        self.new_name_input = FocusComboBox()
        self.new_name_input.setEditable(True)
        self.new_name_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.new_name_input.lineEdit().setPlaceholderText(t("edit_new_name_placeholder"))
        form_layout.addRow(self._new_name_label, self.new_name_input)
        right_layout.addLayout(form_layout)

        # 备份选项
        self.backup_check = QCheckBox(t("edit_backup_check"))
        self.backup_check.setChecked(True)
        right_layout.addWidget(self.backup_check)

        # 操作按钮 (右对齐)
        btn_layout2 = QHBoxLayout()
        btn_layout2.addStretch()
        self.modify_btn = QPushButton(t("edit_modify_btn"))
        self.modify_btn.setMinimumHeight(28)
        self.modify_btn.setMinimumWidth(100)
        self.modify_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.modify_btn.setEnabled(False)
        btn_layout2.addWidget(self.modify_btn)
        right_layout.addLayout(btn_layout2)

        content_grid.addWidget(right_group, 0, 1)

        # ---- GroupBox 4: 标签校验 ----
        validate_group = QGroupBox(t("edit_validate_labels"))
        validate_layout = QVBoxLayout(validate_group)

        self.validate_coords_check = QCheckBox(t("edit_validate_coords"))
        self.validate_coords_check.setChecked(True)
        self.validate_coords_check.setToolTip(t("edit_validate_coords_tooltip"))
        validate_layout.addWidget(self.validate_coords_check)

        self.validate_class_check = QCheckBox(t("edit_validate_class"))
        self.validate_class_check.setChecked(True)
        self.validate_class_check.setToolTip(t("edit_validate_class_tooltip"))
        validate_layout.addWidget(self.validate_class_check)

        self.validate_format_check = QCheckBox(t("edit_validate_format"))
        self.validate_format_check.setChecked(True)
        self.validate_format_check.setToolTip(t("edit_validate_format_tooltip"))
        validate_layout.addWidget(self.validate_format_check)

        self.validate_orphan_check = QCheckBox(t("edit_validate_orphan"))
        self.validate_orphan_check.setChecked(True)
        self.validate_orphan_check.setToolTip(t("edit_validate_orphan_tooltip"))
        validate_layout.addWidget(self.validate_orphan_check)

        # 操作按钮 (右对齐)
        validate_btn_layout = QHBoxLayout()
        validate_btn_layout.addStretch()
        self.validate_btn = QPushButton(t("edit_validate_btn"))
        self.validate_btn.setMinimumHeight(28)
        self.validate_btn.setMinimumWidth(100)
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
        img_path = self.path_group.get_image_dir()
        has_image_dir = bool(img_path and img_path.exists())
        is_busy = bool(self._worker and self._worker.isRunning())
        enabled = has_image_dir and not is_busy

        self.gen_empty_btn.setEnabled(enabled)
        self.convert_btn.setEnabled(enabled)
        self.modify_btn.setEnabled(enabled)
        self.validate_btn.setEnabled(enabled)

        # 类别 ID 检查需要 classes.txt
        classes_path = self.path_group.get_classes_path()
        has_classes = bool(classes_path and classes_path.exists())
        self.validate_class_check.setEnabled(has_classes)
        if not has_classes:
            self.validate_class_check.setChecked(False)
            self.validate_class_check.setToolTip(t("edit_needs_classes_txt"))
        else:
            self.validate_class_check.setToolTip(t("edit_validate_class_tooltip"))

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
        classes_txt = self.path_group.get_classes_path()
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
        StyledMessageBox.warning(self, t("edit_modify_labels_title"), message)

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
        self.log_message.emit(t("edit_cancelling_precheck"))

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
            self.log_message.emit(t("edit_precheck_cancelled"))
            return

        if self._pending_precheck_error:
            StyledMessageBox.warning(self, self._pending_precheck_title or t("edit_precheck"), self._pending_precheck_error)
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
            self.log_message.emit(t("edit_task_running"))
            return

        self._precheck_cancelled = False
        self._pending_precheck_result = None
        self._pending_precheck_handler = on_ready
        self._pending_precheck_cache_key = cache_key
        self._pending_precheck_error = None
        self._pending_precheck_title = title

        self._precheck_dialog = StyledProgressDialog(self, title, label_text, t("cancel"))
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
            StyledMessageBox.information(self, t("edit_gen_empty_labels"), t("edit_no_images_found"))
            return

        if missing_labels == 0:
            StyledMessageBox.information(self, t("edit_gen_empty_labels"), t("edit_no_missing_labels"))
            return

        message = t("edit_gen_empty_confirm",
            total=total_images, missing=missing_labels, format=format_text)
        if not self._confirm_edit_action(t("edit_gen_empty_labels"), message):
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
            StyledMessageBox.information(
                self, t("edit_convert_format"), t("edit_no_convertible_labels", type=source_type))
            return

        message = t("edit_convert_confirm",
            total=total_labels, source=source_type,
            target=target_type, dir=output_dir_name)
        if not self._confirm_edit_action(t("edit_convert_format"), message):
            return

        classes = None
        classes_txt = self.path_group.get_classes_path()
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
            self._show_modify_info(t("edit_modify_labels_title"), t("edit_no_modifiable_labels"))
            return

        if matched_annotations == 0:
            self._show_modify_info(t("edit_modify_labels_title"), t("edit_no_matching_annotations", value=old_value))
            return

        action_text = t("edit_action_replace") if action == ModifyAction.REPLACE else t("edit_action_remove")
        target_text = t("edit_target_new_class", value=new_value) if action == ModifyAction.REPLACE else ""
        backup_text = t("edit_backup_on") if backup_enabled else t("edit_backup_off")
        message = t("edit_modify_confirm",
            total=total_label_files, txt=txt_files, xml=xml_files,
            files=matched_files, annotations=matched_annotations,
            action=action_text, old=old_value, target=target_text,
            backup=backup_text)
        if not self._confirm_edit_action(t("edit_modify_labels_title"), message):
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
        img_path = self.path_group.get_image_dir()
        if not img_path:
            self.log_message.emit(t("edit_select_image_dir_first"))
            return

        if not img_path.exists():
            self.log_message.emit(t("edit_image_dir_not_exist", path=img_path))
            return

        label_path = self.path_group.get_label_dir()
        label_format = LabelFormat.TXT if self.empty_txt_radio.isChecked() else LabelFormat.XML
        cache_key = (
            "generate_empty",
            str(img_path),
            str(label_path) if label_path else "",
            label_format.value,
        )

        self._start_precheck_worker(
            title=t("edit_gen_empty_labels"),
            label_text=t("edit_checking_missing_labels"),
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
        img_path = self.path_group.get_image_dir()
        if not img_path:
            self.log_message.emit(t("edit_select_image_dir_first"))
            return

        if not img_path.exists():
            self.log_message.emit(t("edit_image_dir_not_exist", path=img_path))
            return

        label_path = self.path_group.get_label_dir()
        dataset_root = self._resolve_dataset_root(img_path, label_path)
        to_xml = self.txt_to_xml_radio.isChecked()
        cache_key = (
            "convert_format",
            str(img_path),
            str(label_path) if label_path else "",
            "to_xml" if to_xml else "to_txt",
        )

        self._start_precheck_worker(
            title=t("edit_convert_format"),
            label_text=t("edit_checking_convertible_labels"),
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
        img_path = self.path_group.get_image_dir()
        if not img_path:
            self._show_modify_warning(t("edit_select_image_dir_first"))
            return

        if not img_path.exists():
            self._show_modify_warning(t("edit_image_dir_not_exist", path=img_path))
            return

        old_value = self.old_name_input.currentText().strip()
        if not old_value:
            self._show_modify_warning(t("edit_input_old_class"))
            return

        new_value = self.new_name_input.currentText().strip()
        action = self._resolve_modify_action()

        label_path = self.path_group.get_label_dir()
        dataset_root = self._resolve_dataset_root(img_path, label_path)
        has_explicit_label_dir = bool(label_path and label_path.exists())
        search_dir = label_path if has_explicit_label_dir else dataset_root
        image_scope = None if has_explicit_label_dir else img_path

        classes_txt = self.path_group.get_classes_path()
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
            title=t("edit_modify_labels_title"),
            label_text=t("edit_checking_affected_labels"),
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
        self.log_message.emit(t("edit_generated_empty_labels", count=count))

    def _on_convert_format_finished(self, count: int) -> None:
        """格式转换完成回调"""
        self._invalidate_edit_precheck_cache()
        self.log_message.emit(t("edit_convert_complete", count=count))

    def _on_modify_labels_finished(self, count: int) -> None:
        """修改标签完成回调"""
        self._invalidate_edit_precheck_cache()
        self.log_message.emit(t("edit_modified_files", count=count))
        self._show_modify_info(t("edit_modify_complete"), t("edit_modified_files_msg", count=count))

    @Slot()
    def _on_validate_labels(self) -> None:
        """启动标签校验后台任务"""
        img_path = self.path_group.get_image_dir()
        if not img_path or not img_path.exists():
            self.log_message.emit(t("edit_select_valid_img_dir"))
            return

        label_path = self.path_group.get_label_dir()
        classes_txt = self.path_group.get_classes_path()

        check_coords = self.validate_coords_check.isChecked()
        check_class_ids = (
            self.validate_class_check.isChecked()
            and self.validate_class_check.isEnabled()
        )
        check_format = self.validate_format_check.isChecked()
        check_orphans = self.validate_orphan_check.isChecked()

        if not any([check_coords, check_class_ids, check_format, check_orphans]):
            self.log_message.emit(t("edit_select_at_least_one_check"))
            return

        self.log_message.emit(t("edit_starting_validation"))

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
        lines = [t("edit_scanned_labels", count=result.total_labels)]
        if result.coord_errors:
            lines.append(t("edit_coord_errors", count=len(result.coord_errors)))
        if result.class_errors:
            lines.append(t("edit_class_errors", count=len(result.class_errors)))
        if result.format_errors:
            lines.append(t("edit_format_errors", count=len(result.format_errors)))
        if result.orphan_labels:
            lines.append(t("edit_orphan_labels", count=len(result.orphan_labels)))

        self.log_message.emit("=" * 40)
        self.log_message.emit(t("edit_validation_complete"))
        for line in lines:
            self.log_message.emit(line)

        # 输出详细问题到日志
        if result.coord_errors:
            self.log_message.emit(t("edit_coord_error_detail"))
            for path, loc, reason in result.coord_errors[:50]:
                self.log_message.emit(f"  {path.name} [{loc}]: {reason}")
            if len(result.coord_errors) > 50:
                self.log_message.emit(t("edit_shown_limit", total=len(result.coord_errors), limit=50))

        if result.class_errors:
            self.log_message.emit(t("edit_class_error_detail"))
            for path, loc, reason in result.class_errors[:50]:
                self.log_message.emit(f"  {path.name} [{loc}]: {reason}")
            if len(result.class_errors) > 50:
                self.log_message.emit(t("edit_shown_limit", total=len(result.class_errors), limit=50))

        if result.format_errors:
            self.log_message.emit(t("edit_format_error_detail"))
            for path, reason in result.format_errors[:50]:
                self.log_message.emit(f"  {path.name}: {reason}")
            if len(result.format_errors) > 50:
                self.log_message.emit(t("edit_shown_limit", total=len(result.format_errors), limit=50))

        if result.orphan_labels:
            self.log_message.emit(t("edit_orphan_label_list"))
            for path in result.orphan_labels[:50]:
                self.log_message.emit(f"  {path.name}")
            if len(result.orphan_labels) > 50:
                self.log_message.emit(t("edit_shown_limit_items", total=len(result.orphan_labels), limit=50))

        if not result.has_issues:
            StyledMessageBox.information(self, t("edit_validation_passed"), t("edit_all_labels_passed"))
            return

        StyledMessageBox.warning(
            self,
            t("edit_validation_done"),
            t("edit_issues_found", count=result.issue_count),
        )

        # 孤立标签清理确认
        if result.orphan_labels:
            confirm = StyledMessageBox.question(
                self,
                t("edit_clean_orphan_labels"),
                t("edit_clean_orphan_confirm", count=len(result.orphan_labels)),
                accept_text=t("edit_clean_orphan_accept"),
                reject_text=t("edit_clean_orphan_reject"),
            )
            if confirm:
                self.log_message.emit(t("edit_cleaning_orphan"))
                self._start_worker(
                    lambda: self._handler.clean_orphan_labels(
                        result.orphan_labels,
                        backup=True,
                        interrupt_check=lambda: self._worker.is_interrupted() if self._worker else False,
                        progress_callback=self._emit_progress,
                        message_callback=self._emit_message,
                    ),
                    on_finished=lambda count: self.log_message.emit(
                        t("edit_clean_orphan_complete", count=count)
                    ),
                )

    @Slot(bool)
    def _on_action_changed(self, checked: bool) -> None:
        """操作类型切换: 删除模式时隐藏新名称输入框和标签"""
        self.new_name_input.setVisible(not checked)
        self.new_name_input.setEnabled(not checked)
        self._new_name_label.setVisible(not checked)
        self._invalidate_edit_precheck_cache()
