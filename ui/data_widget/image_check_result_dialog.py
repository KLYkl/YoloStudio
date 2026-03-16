"""
image_check_result_dialog.py - 图像检查结果弹窗集合
============================================

职责:
    - 专用于展示图像检查各项结果（完整性/尺寸/重复/健康检查）
    - 精美卡片式布局，取代简陋的 StyledMessageBox
    - 复用项目 Catppuccin 主题配色

架构要点:
    - _BaseResultDialog: 公共基类，处理主题、圆角背景、居中、标题栏
    - ImageCheckResultDialog: 完整性校验结果
    - SizeAnalysisResultDialog: 尺寸分析结果
    - DuplicateResultDialog: 重复检测结果
    - HealthCheckResultDialog: 一键健康检查综合报告
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QBrush, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.data_handler._models import (
    DuplicateGroup,
    ImageCheckResult,
    ImageSizeStats,
)
from ui.styled_message_box import StyledMessageBox


# ============================================================
# 公共主题色板
# ============================================================

def _get_palette(is_dark: bool) -> dict:
    """返回当前主题的完整色板字典"""
    if is_dark:
        return dict(
            bg="#1e1e2e", border="#313244",
            text_primary="#cdd6f4", text_secondary="#a6adc8",
            text_muted="#6c7086", surface="#181825",
            card_bg="#11111b", card_border="#313244",
            accent="#89b4fa",
            green="#a6e3a1", red="#f38ba8", yellow="#f9e2af",
            blue="#89b4fa", orange="#fab387",
            green_bg="rgba(166, 227, 161, 15)",
            red_bg="rgba(243, 139, 168, 15)",
            yellow_bg="rgba(249, 226, 175, 15)",
            blue_bg="rgba(137, 180, 250, 15)",
            orange_bg="rgba(250, 179, 135, 15)",
            badge_text="#1e1e2e",
            btn_fg="#1e1e2e",
        )
    return dict(
        bg="#eff1f5", border="#bcc0cc",
        text_primary="#4c4f69", text_secondary="#5c5f77",
        text_muted="#7c7f93", surface="#e6e9ef",
        card_bg="#dce0e8", card_border="#bcc0cc",
        accent="#1e66f5",
        green="#40a02b", red="#d20f39", yellow="#df8e1d",
        blue="#1e66f5", orange="#fe640b",
        green_bg="rgba(64, 160, 43, 15)",
        red_bg="rgba(210, 15, 57, 15)",
        yellow_bg="rgba(223, 142, 29, 15)",
        blue_bg="rgba(30, 102, 245, 15)",
        orange_bg="rgba(254, 100, 11, 15)",
        badge_text="#eff1f5",
        btn_fg="#eff1f5",
    )


# ============================================================
# 基类: _BaseResultDialog
# ============================================================

class _BaseResultDialog(QDialog):
    """结果弹窗基类 — 提供主题、圆角背景、居中、标题栏、底部确定按钮"""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        *,
        icon_char: str = "✓",
        icon_color_key: str = "green",
        width: int = 480,
    ) -> None:
        main_window = StyledMessageBox._find_main_window(parent)
        super().__init__(main_window)

        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedWidth(width)

        is_dark = StyledMessageBox._is_dark_theme()
        self.p = _get_palette(is_dark)
        self._bg_color = self.p["bg"]
        self._border_color = self.p["border"]
        self._radius = 12

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._main_layout = QVBoxLayout()
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(28, 22, 28, 12)
        self._content_layout.setSpacing(0)

        # ---- 标题栏 ----
        icon_color = self.p[icon_color_key]
        icon_bg = self.p.get(f"{icon_color_key}_bg", "transparent")

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 16)
        header.setSpacing(10)

        icon_lbl = QLabel(icon_char)
        icon_lbl.setFixedSize(28, 28)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(f"""
            background-color: {icon_bg};
            color: {icon_color};
            border: 1.5px solid {icon_color};
            border-radius: 14px;
            font-size: 14px; font-weight: bold;
        """)
        header.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"""
            color: {self.p['text_primary']};
            font-size: 16px; font-weight: 600;
            background: transparent;
        """)
        header.addWidget(title_lbl)
        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setObjectName("icResultCloseBtn")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton#icResultCloseBtn {{
                background: transparent; color: {self.p['text_secondary']};
                border: none; border-radius: 6px; font-size: 14px; padding: 0;
            }}
            QPushButton#icResultCloseBtn:hover {{
                background-color: #c42b1c; color: #ffffff;
            }}
            QPushButton#icResultCloseBtn:pressed {{
                background-color: #b22a1a; color: #ffffff;
            }}
        """)
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        self._content_layout.addLayout(header)

    def _finalize(self) -> None:
        """子类构建完 content 后调用此方法，添加底部按钮并组装布局"""
        self._main_layout.addWidget(self._content_widget)

        footer = QWidget()
        footer.setStyleSheet("background: transparent;")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(28, 0, 28, 20)
        fl.setSpacing(10)
        fl.addStretch()

        ok_btn = QPushButton("确定")
        ok_btn.setFixedSize(90, 34)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        a = self.p["accent"]
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {a}; color: {self.p['btn_fg']};
                border: none; border-radius: 8px;
                font-size: 14px; font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {StyledMessageBox._lighten(a, 0.1)};
            }}
            QPushButton:pressed {{
                background-color: {StyledMessageBox._darken(a, 0.08)};
            }}
        """)
        ok_btn.clicked.connect(self.accept)
        fl.addWidget(ok_btn)

        self._main_layout.addWidget(footer)
        self.layout().addLayout(self._main_layout)

    # ---- 公共辅助 ----

    def _add_summary_card(self, line1: str, line2: str, line2_color: str) -> None:
        """添加汇总卡片（两行文字）"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {self.p['card_bg']};
                border: 1px solid {self.p['card_border']};
                border-radius: 10px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(6)

        l1 = QLabel(line1)
        l1.setStyleSheet(f"""
            color: {self.p['text_primary']}; font-size: 15px;
            font-weight: 500; background: transparent; border: none;
        """)
        cl.addWidget(l1)

        l2 = QLabel(line2)
        l2.setStyleSheet(f"""
            color: {line2_color}; font-size: 22px;
            font-weight: 700; background: transparent; border: none;
        """)
        cl.addWidget(l2)

        self._content_layout.addWidget(card)

    def _add_stat_row(
        self, emoji: str, label: str, count: int,
        *, has_issue: bool = False,
    ) -> None:
        """添加一行分类统计（emoji + 名称 + badge）"""
        p = self.p
        row = QHBoxLayout()
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(0)

        dot = QLabel(emoji if has_issue else "⚫")
        dot.setFixedWidth(24)
        dot.setStyleSheet("font-size: 10px; background: transparent;")
        row.addWidget(dot)

        name = QLabel(label)
        name.setStyleSheet(f"""
            color: {p['text_primary'] if has_issue else p['text_muted']};
            font-size: 14px; background: transparent;
        """)
        row.addWidget(name)
        row.addStretch()

        badge = QLabel(f"{count} 个")
        if has_issue:
            badge.setStyleSheet(f"""
                color: {p['badge_text']}; background-color: {p['red']};
                border-radius: 9px; font-size: 12px; font-weight: 600;
                padding: 2px 10px; min-width: 30px;
            """)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            badge.setStyleSheet(f"""
                color: {p['text_muted']}; background: transparent;
                font-size: 13px; padding: 2px 10px;
            """)
            badge.setAlignment(Qt.AlignmentFlag.AlignRight)

        row.addWidget(badge)
        self._content_layout.addLayout(row)
        self._content_layout.addSpacing(8)

    def _add_detail_section(self, detail_html: str) -> None:
        """添加可展开的详细信息区域 (接收 HTML)"""
        p = self.p
        self._detail_btn = QPushButton("▸ 显示详细文件列表")
        self._detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._detail_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {p['accent']};
                border: none; font-size: 13px;
                padding: 6px 0 2px 0; text-align: left;
            }}
            QPushButton:hover {{ color: {p['text_primary']}; }}
        """)
        self._content_layout.addWidget(self._detail_btn)

        self._detail_edit = QTextEdit()
        self._detail_edit.setReadOnly(True)
        self._detail_edit.setHtml(detail_html)
        self._detail_edit.setVisible(False)
        self._detail_edit.setMaximumHeight(200)
        self._detail_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {p['card_bg']};
                color: {p['text_muted']};
                border: 1px solid {p['card_border']};
                border-radius: 8px;
                padding: 10px; margin-top: 4px;
            }}
        """)
        self._content_layout.addWidget(self._detail_edit)
        self._detail_btn.clicked.connect(self._toggle_detail)
        # 保存折叠高度
        self._collapsed_height: int = 0

    def _html_section(
        self, title: str, items: list[str],
        *, title_color: str = "",
    ) -> str:
        """构建一个 HTML 详情分组 (标题 + 文件列表)"""
        p = self.p
        tc = title_color or p['accent']
        rows = "".join(
            f'<div style="color:{p["text_muted"]};'
            f'font-family:Consolas,monospace;font-size:12px;'
            f'padding:1px 0 1px 12px;">{item}</div>'
            for item in items
        )
        return (
            f'<div style="margin-bottom:10px;">'
            f'<div style="color:{tc};font-size:12px;font-weight:600;'
            f'padding:2px 0 4px 0;">{title}</div>'
            f'{rows}</div>'
        )

    def _toggle_detail(self) -> None:
        visible = not self._detail_edit.isVisible()
        if visible:
            # 展开: 记住折叠高度 → 释放约束 → 显示 → 设新高度
            self._collapsed_height = self.height()
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self._detail_edit.setVisible(True)
            QApplication.processEvents()
            detail_h = self._detail_edit.maximumHeight()
            new_h = self._collapsed_height + detail_h + 8
            self.setFixedHeight(new_h)
        else:
            # 折叠: 隐藏 → 直接锁定到折叠高度 (不释放约束!)
            self._detail_edit.setVisible(False)
            if self._collapsed_height > 0:
                self.setFixedHeight(self._collapsed_height)
        self._detail_btn.setText(
            "▾ 收起详细文件列表" if visible else "▸ 显示详细文件列表"
        )
        # 重新居中
        QApplication.processEvents()
        parent = self.parent()
        if parent:
            geo = parent.geometry()
            s = self.size()
            self.move(
                geo.x() + (geo.width() - s.width()) // 2,
                geo.y() + (geo.height() - s.height()) // 2,
            )

    # ---- 绘制 & 居中 ----

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(
            float(rect.x()), float(rect.y()),
            float(rect.width()), float(rect.height()),
            self._radius, self._radius,
        )
        painter.fillPath(path, QBrush(QColor(self._bg_color)))
        painter.setPen(QPen(QColor(self._border_color), 1))
        painter.drawPath(path)
        painter.end()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        parent = self.parent()
        if parent:
            geo = parent.geometry()
            s = self.size()
            self.move(
                geo.x() + (geo.width() - s.width()) // 2,
                geo.y() + (geo.height() - s.height()) // 2,
            )
        else:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                s = self.size()
                self.move(
                    (geo.width() - s.width()) // 2,
                    (geo.height() - s.height()) // 2,
                )


# ============================================================
# 1. 图像完整性校验结果
# ============================================================

class ImageCheckResultDialog(_BaseResultDialog):
    """完整性校验结果弹窗"""

    def __init__(self, parent: QWidget | None, result: ImageCheckResult) -> None:
        has_issues = result.has_issues
        super().__init__(
            parent, "图像完整性校验",
            icon_char="!" if has_issues else "✓",
            icon_color_key="yellow" if has_issues else "green",
        )

        # 汇总卡片
        if has_issues:
            self._add_summary_card(
                f"扫描 {result.total_images} 张图片",
                f"发现 {result.issue_count} 个问题",
                self.p["red"],
            )
        else:
            self._add_summary_card(
                f"扫描 {result.total_images} 张图片",
                "全部通过 ✓",
                self.p["green"],
            )

        # 分类条目
        self._content_layout.addSpacing(16)
        items = [
            ("损坏图片", "🔴", len(result.corrupted)),
            ("零字节文件", "🟠", len(result.zero_bytes)),
            ("格式不匹配", "🟡", len(result.format_mismatch)),
            ("EXIF 旋转标记", "🔵", len(result.exif_rotation)),
        ]
        for label, emoji, count in items:
            self._add_stat_row(emoji, label, count, has_issue=count > 0)

        # 详细信息
        if has_issues:
            self._add_detail_section(self._build_detail(result))

        self._finalize()

    def _build_detail(self, r: ImageCheckResult) -> str:
        """构建完整性校验的 HTML 详情"""
        p = self.p
        html = ""
        if r.corrupted:
            items = [
                f'{fp.name} <span style="color:{p["text_muted"]};'
                f'font-size:11px;">— {reason[:70]}</span>'
                for fp, reason in r.corrupted
            ]
            html += self._html_section(
                f"🔴 损坏图片  ({len(r.corrupted)} 个)", items,
                title_color=p['red'],
            )
        if r.zero_bytes:
            items = [fp.name for fp in r.zero_bytes]
            html += self._html_section(
                f"🟠 零字节文件  ({len(r.zero_bytes)} 个)", items,
                title_color=p['orange'],
            )
        if r.format_mismatch:
            items = [
                f'{fp.name} <span style="color:{p["text_muted"]};'
                f'font-size:11px;">({ext} → {real})</span>'
                for fp, ext, real in r.format_mismatch
            ]
            html += self._html_section(
                f"🟡 格式不匹配  ({len(r.format_mismatch)} 个)", items,
                title_color=p['yellow'],
            )
        if r.exif_rotation:
            items = [
                f'{fp.name} <span style="color:{p["text_muted"]};'
                f'font-size:11px;">(orientation={orient})</span>'
                for fp, orient in r.exif_rotation
            ]
            html += self._html_section(
                f"🔵 EXIF 旋转标记  ({len(r.exif_rotation)} 个)", items,
                title_color=p['blue'],
            )
        return html

    @staticmethod
    def show_result(parent: QWidget | None, result: ImageCheckResult) -> None:
        ImageCheckResultDialog(parent, result).exec()


# ============================================================
# 2. 尺寸分析结果
# ============================================================

class SizeAnalysisResultDialog(_BaseResultDialog):
    """尺寸分析结果弹窗"""

    def __init__(self, parent: QWidget | None, result: ImageSizeStats) -> None:
        abnormal = len(result.abnormal_small) + len(result.abnormal_large)
        has_issues = abnormal > 0
        super().__init__(
            parent, "图像尺寸分析",
            icon_char="!" if has_issues else "✓",
            icon_color_key="yellow" if has_issues else "green",
        )
        p = self.p

        # 汇总卡片
        if has_issues:
            self._add_summary_card(
                f"分析 {result.total_images} 张图片",
                f"{abnormal} 张尺寸异常",
                p["yellow"],
            )
        else:
            self._add_summary_card(
                f"分析 {result.total_images} 张图片",
                "所有尺寸正常 ✓",
                p["green"],
            )

        # 尺寸统计卡片 (3列: 最小/最大/平均)
        self._content_layout.addSpacing(16)

        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {p['card_bg']};
                border: 1px solid {p['card_border']};
                border-radius: 10px;
            }}
        """)
        grid = QGridLayout(stats_frame)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        stat_items = [
            ("最小尺寸", f"{result.min_size[0]}×{result.min_size[1]}", p["blue"]),
            ("最大尺寸", f"{result.max_size[0]}×{result.max_size[1]}", p["green"]),
            ("平均尺寸", f"{result.avg_size[0]}×{result.avg_size[1]}", p["orange"]),
        ]
        for col, (title, value, color) in enumerate(stat_items):
            t = QLabel(title)
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t.setStyleSheet(f"""
                color: {p['text_muted']}; font-size: 12px;
                background: transparent; border: none;
            """)
            grid.addWidget(t, 0, col)

            v = QLabel(value)
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.setStyleSheet(f"""
                color: {color}; font-size: 16px; font-weight: 700;
                background: transparent; border: none;
            """)
            grid.addWidget(v, 1, col)

        self._content_layout.addWidget(stats_frame)

        # 异常条目
        if has_issues:
            self._content_layout.addSpacing(14)
            if result.abnormal_small:
                self._add_stat_row(
                    "🔴", f"过小图片 (<32px)",
                    len(result.abnormal_small), has_issue=True,
                )
            if result.abnormal_large:
                self._add_stat_row(
                    "🟠", f"过大图片 (>8192px)",
                    len(result.abnormal_large), has_issue=True,
                )

            # 详细信息 (HTML)
            html = ""
            if result.abnormal_small:
                items = [fp.name for fp in result.abnormal_small]
                html += self._html_section(
                    f"🔴 过小图片 <32px  ({len(result.abnormal_small)} 张)",
                    items, title_color=self.p['red'],
                )
            if result.abnormal_large:
                items = [fp.name for fp in result.abnormal_large]
                html += self._html_section(
                    f"🟠 过大图片 >8192px  ({len(result.abnormal_large)} 张)",
                    items, title_color=self.p['orange'],
                )
            self._add_detail_section(html)

        self._finalize()

    @staticmethod
    def show_result(parent: QWidget | None, result: ImageSizeStats) -> None:
        SizeAnalysisResultDialog(parent, result).exec()


# ============================================================
# 3. 重复检测结果
# ============================================================

class DuplicateResultDialog(_BaseResultDialog):
    """重复检测结果弹窗"""

    def __init__(
        self, parent: QWidget | None, groups: list[DuplicateGroup],
    ) -> None:
        has_issues = bool(groups)
        super().__init__(
            parent, "重复图片检测",
            icon_char="!" if has_issues else "✓",
            icon_color_key="yellow" if has_issues else "green",
        )
        p = self.p

        if has_issues:
            total_files = sum(len(g.paths) for g in groups)
            self._add_summary_card(
                f"发现 {len(groups)} 组重复",
                f"共 {total_files} 个文件",
                p["yellow"],
            )

            # 详细信息
            self._content_layout.addSpacing(12)
            html = ""
            for i, group in enumerate(groups, 1):
                items = [fp.name for fp in group.paths]
                html += self._html_section(
                    f"📁 组 {i}  ({len(group.paths)} 个文件)",
                    items, title_color=self.p['yellow'],
                )
            self._add_detail_section(html)
        else:
            self._add_summary_card(
                "重复检测完成",
                "未发现重复图片 ✓",
                p["green"],
            )

        self._finalize()

    @staticmethod
    def show_result(
        parent: QWidget | None, groups: list[DuplicateGroup],
    ) -> None:
        DuplicateResultDialog(parent, groups).exec()


# ============================================================
# 4. 一键健康检查综合报告
# ============================================================

class HealthCheckResultDialog(_BaseResultDialog):
    """一键健康检查综合报告弹窗"""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        integrity: Optional[ImageCheckResult] = None,
        sizes: Optional[ImageSizeStats] = None,
        duplicates: Optional[list[DuplicateGroup]] = None,
    ) -> None:
        has_any_issue = (
            (integrity and integrity.has_issues)
            or (sizes and (sizes.abnormal_small or sizes.abnormal_large))
            or (duplicates and len(duplicates) > 0)
        )
        super().__init__(
            parent, "一键健康检查",
            icon_char="!" if has_any_issue else "✓",
            icon_color_key="yellow" if has_any_issue else "green",
            width=520,
        )
        p = self.p

        # ---- 汇总卡片 ----
        issue_parts: list[str] = []
        if integrity and integrity.has_issues:
            issue_parts.append(f"完整性 {integrity.issue_count}")
        if sizes:
            ab = len(sizes.abnormal_small) + len(sizes.abnormal_large)
            if ab > 0:
                issue_parts.append(f"尺寸异常 {ab}")
        if duplicates:
            issue_parts.append(f"重复 {len(duplicates)} 组")

        total_count = integrity.total_images if integrity else (
            sizes.total_images if sizes else 0
        )

        if has_any_issue:
            self._add_summary_card(
                f"扫描 {total_count} 张图片",
                f"发现 {len(issue_parts)} 类问题",
                p["red"],
            )
        else:
            self._add_summary_card(
                f"扫描 {total_count} 张图片",
                "所有检查通过 ✓",
                p["green"],
            )

        # ---- 三项检查状态条目 ----
        self._content_layout.addSpacing(16)

        # 完整性
        if integrity:
            ic = integrity.issue_count
            self._add_check_row(
                "完整性校验", ic > 0,
                f"{ic} 个问题" if ic > 0 else "无问题",
            )

        # 尺寸
        if sizes and sizes.total_images > 0:
            ab = len(sizes.abnormal_small) + len(sizes.abnormal_large)
            size_range = (
                f"{sizes.min_size[0]}×{sizes.min_size[1]} ~ "
                f"{sizes.max_size[0]}×{sizes.max_size[1]}"
            )
            self._add_check_row(
                "尺寸分析", ab > 0,
                f"{ab} 张异常 ({size_range})" if ab > 0
                else f"正常 ({size_range})",
            )

        # 重复
        if duplicates is not None:
            if duplicates:
                dup_files = sum(len(g.paths) for g in duplicates)
                self._add_check_row(
                    "重复检测", True,
                    f"{len(duplicates)} 组 / {dup_files} 个文件",
                )
            else:
                self._add_check_row("重复检测", False, "无重复")

        # ---- 详细信息 ----
        if has_any_issue:
            self._content_layout.addSpacing(4)
            details = self._build_detail(integrity, sizes, duplicates)
            self._add_detail_section(details)

        self._finalize()

    def _add_check_row(self, label: str, has_issue: bool, status: str) -> None:
        """添加一行检查状态行 (✓/⚠ + 名称 + 状态描述)"""
        p = self.p
        row = QHBoxLayout()
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(8)

        icon = QLabel("⚠" if has_issue else "✓")
        icon.setFixedWidth(20)
        icon.setStyleSheet(f"""
            color: {p['yellow'] if has_issue else p['green']};
            font-size: 14px; font-weight: bold;
            background: transparent;
        """)
        row.addWidget(icon)

        name = QLabel(label)
        name.setFixedWidth(80)
        name.setStyleSheet(f"""
            color: {p['text_primary']}; font-size: 14px;
            font-weight: 500; background: transparent;
        """)
        row.addWidget(name)

        desc = QLabel(status)
        desc.setStyleSheet(f"""
            color: {p['red'] if has_issue else p['text_muted']};
            font-size: 13px; background: transparent;
        """)
        row.addWidget(desc)
        row.addStretch()

        self._content_layout.addLayout(row)
        self._content_layout.addSpacing(8)

    def _build_detail(
        self,
        integrity: Optional[ImageCheckResult],
        sizes: Optional[ImageSizeStats],
        duplicates: Optional[list[DuplicateGroup]],
    ) -> str:
        """构建健康检查综合报告的 HTML 详情"""
        p = self.p
        html = ""
        if integrity and integrity.has_issues:
            if integrity.corrupted:
                items = [
                    f'{fp.name} <span style="color:{p["text_muted"]};'
                    f'font-size:11px;">— {r[:60]}</span>'
                    for fp, r in integrity.corrupted
                ]
                html += self._html_section(
                    f"🔴 损坏  ({len(integrity.corrupted)} 个)", items,
                    title_color=p['red'],
                )
            if integrity.zero_bytes:
                items = [fp.name for fp in integrity.zero_bytes]
                html += self._html_section(
                    f"🟠 零字节  ({len(integrity.zero_bytes)} 个)", items,
                    title_color=p['orange'],
                )
            if integrity.format_mismatch:
                items = [
                    f'{fp.name} <span style="color:{p["text_muted"]};'
                    f'font-size:11px;">({ext} → {real})</span>'
                    for fp, ext, real in integrity.format_mismatch
                ]
                html += self._html_section(
                    f"🟡 格式不匹配  ({len(integrity.format_mismatch)} 个)",
                    items, title_color=p['yellow'],
                )
        if sizes:
            if sizes.abnormal_small:
                items = [fp.name for fp in sizes.abnormal_small]
                html += self._html_section(
                    f"🔴 过小 <32px  ({len(sizes.abnormal_small)} 张)",
                    items, title_color=p['red'],
                )
            if sizes.abnormal_large:
                items = [fp.name for fp in sizes.abnormal_large]
                html += self._html_section(
                    f"🟠 过大 >8192px  ({len(sizes.abnormal_large)} 张)",
                    items, title_color=p['orange'],
                )
        if duplicates:
            for i, g in enumerate(duplicates, 1):
                items = [fp.name for fp in g.paths]
                html += self._html_section(
                    f"📁 重复组 {i}  ({len(g.paths)} 个)", items,
                    title_color=p['yellow'],
                )
        return html

    @staticmethod
    def show_result(
        parent: QWidget | None,
        *,
        integrity: Optional[ImageCheckResult] = None,
        sizes: Optional[ImageSizeStats] = None,
        duplicates: Optional[list[DuplicateGroup]] = None,
    ) -> None:
        HealthCheckResultDialog(
            parent, integrity=integrity, sizes=sizes, duplicates=duplicates,
        ).exec()
