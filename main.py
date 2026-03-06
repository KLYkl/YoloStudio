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
import traceback
from typing import Type

# 在导入 OpenCV 之前设置日志级别，抑制摄像头扫描警告
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFont

from config import AppConfig
from ui.main_window import MainWindow
from utils.logger import get_logger, setup_stdout_redirect


def exception_hook(
    exc_type: Type[BaseException], 
    exc_value: BaseException, 
    exc_traceback
) -> None:
    """
    全局异常处理钩子
    
    捕获所有未处理的异常，弹出错误对话框并记录日志，防止程序直接闪退。
    
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
    
    # 记录到日志
    logger = get_logger()
    logger.critical(f"未捕获的异常:\n{tb_text}")
    
    # 弹出错误对话框 (查找当前活动窗口作为父窗口以居中显示)
    app = QApplication.instance()
    parent = app.activeWindow() if app else None
    error_dialog = QMessageBox(parent)
    error_dialog.setIcon(QMessageBox.Icon.Critical)
    error_dialog.setWindowTitle("程序错误")
    error_dialog.setText("程序遇到了一个未预期的错误，请联系开发者。")
    error_dialog.setDetailedText(tb_text)
    error_dialog.exec()


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
    
    # 设置全局字体 (使用 QFont API 避免 CSS font-size 解析问题)
    global_font = QFont("Microsoft YaHei", 10)
    global_font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(global_font)
    
    # 初始化配置 (确保单例创建)
    config = AppConfig()
    
    # 初始化日志系统
    logger = get_logger()
    logger.info("正在启动 YoloStudio...")
    logger.debug(f"Python 版本: {sys.version}")
    logger.debug(f"PySide6 版本: {app.platformName()}")
    
    # 重定向标准输出到日志系统
    setup_stdout_redirect()
    
    # 创建并显示主窗口
    window = MainWindow()
    
    # 将窗口居中显示
    screen = app.primaryScreen().availableGeometry()
    window_size = window.size()
    x = (screen.width() - window_size.width()) // 2
    y = (screen.height() - window_size.height()) // 2
    window.move(x, y)
    
    window.show()
    
    # 进入事件循环
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
