"""
main.py - YoloStudio 程序入口
============================================

职责:
    - 初始化 QApplication
    - 挂载全局异常处理器
    - 加载配置并启动主窗口

架构要点:
    - 使用 sys.excepthook 捕获未处理异常，防止程序闪退
    - 设置高 DPI 支持
    - 确保单实例运行 (可选扩展)
"""

from __future__ import annotations

import os
import sys
import threading
import traceback
from typing import Type

# 在导入 OpenCV 之前设置日志级别，抑制摄像头扫描警告
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from config import AppConfig
from ui.main_window import MainWindow
from utils.i18n import init_language, t
from utils.logger import get_logger, setup_stdout_redirect


def exception_hook(
    exc_type: Type[BaseException], 
    exc_value: BaseException, 
    exc_traceback
) -> None:
    """
    全局异常处理钩子
    
    捕获所有未处理的异常，弹出错误对话框并记录日志，防止程序直接闪退。
    注意: 从工作线程触发时仅记录日志，不弹窗（Qt 要求 UI 操作在主线程）。
    
    Args:
        exc_type: 异常类型
        exc_value: 异常实例
        exc_traceback: 堆栈跟踪对象
    """
    # 忽略 KeyboardInterrupt (Ctrl+C)
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    # 格式化错误信息
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    tb_text = "".join(tb_lines)
    
    logger = get_logger()
    logger.critical(t("uncaught_exception", tb=tb_text))
    
    if threading.current_thread() is not threading.main_thread():
        logger.error(t("exception_in_worker"))
        return
    
    from ui.styled_message_box import StyledMessageBox
    app = QApplication.instance()
    parent = app.activeWindow() if app else None
    StyledMessageBox.critical(
        parent,
        t("program_error"),
        t("program_error_msg"),
        detailed_text=tb_text,
    )


def main() -> int:
    """
    程序主入口函数
    
    Returns:
        int: 退出码 (0 = 正常, 非0 = 错误)
    """
    # 挂载全局异常钩子
    sys.excepthook = exception_hook
    
    # 创建应用程序
    app = QApplication(sys.argv)
    app.setApplicationName("YoloStudio")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("YoloStudio")
    
    # 使用系统默认 UI 字体，仅统一字号与风格，避免写死本机字体
    global_font = app.font()
    global_font.setPointSize(10)
    global_font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(global_font)
    
    config = AppConfig()
    
    # 初始化语言 (在创建 UI 之前)
    init_language()
    
    logger = get_logger()
    logger.info(t("starting_app"))
    logger.debug(f"Python 版本: {sys.version}")
    logger.debug(f"PySide6 版本: {app.platformName()}")
    
    # 重定向标准输出到日志系统
    setup_stdout_redirect()
    
    # 窗口管理器: 支持语言切换时重建窗口
    state = {"window": None}

    def create_window():
        old = state["window"]
        if old is not None:
            pos = old.pos()
            size = old.size()
            old.close()
        else:
            pos = None
            size = None

        w = MainWindow()
        state["window"] = w
        w.language_changed.connect(create_window)

        if pos is not None and size is not None:
            w.resize(size)
            w.move(pos)
        else:
            screen = app.primaryScreen().availableGeometry()
            w_size = w.size()
            w.move(
                (screen.width() - w_size.width()) // 2,
                (screen.height() - w_size.height()) // 2,
            )
        w.show()

    create_window()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
