"""
logger.py - 信号驱动的日志管理器
============================================

职责:
    - 提供统一的日志记录接口
    - 同时输出到控制台和 GUI (通过 Signal)
    - 重定向 stdout/stderr 到日志系统

架构要点:
    - LogManager 继承 QObject，定义 log_emitted Signal
    - SignalHandler 自定义 logging.Handler，桥接 logging -> Signal
    - 全局单例访问: get_logger()
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, TextIO

from PySide6.QtCore import QObject, Signal


class LogManager(QObject):
    """
    日志管理器 (单例)
    
    通过 Signal 机制将日志消息发送到 UI 层。
    
    Signals:
        log_emitted(str): 当有新日志消息时发射，携带格式化后的消息文本
    
    使用方式:
        log_manager = get_logger()
        log_manager.log_emitted.connect(ui_log_widget.append)
        log_manager.info("应用程序启动")
    """
    
    # 日志信号: 发送格式化后的日志文本到 UI
    log_emitted = Signal(str)
    
    _instance: Optional[LogManager] = None
    
    def __new__(cls) -> LogManager:
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        """初始化日志管理器"""
        if self._initialized:
            return
        
        super().__init__()
        self._initialized = True
        
        # 创建 logger
        self._logger = logging.getLogger("YoloStudio")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False  # 防止重复输出
        
        # 日志格式
        self._formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        )
        
        # 添加控制台 Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(self._formatter)
        self._logger.addHandler(console_handler)
        
        # 添加文件 Handler (按大小轮转，保存到程序目录/logs/)
        log_dir = Path(__file__).resolve().parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "yolostudio.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(self._formatter)
        self._logger.addHandler(file_handler)
        
        # 添加 Signal Handler (用于 GUI)
        signal_handler = SignalHandler(self)
        signal_handler.setLevel(logging.DEBUG)
        signal_handler.setFormatter(self._formatter)
        self._logger.addHandler(signal_handler)
    
    def debug(self, message: str) -> None:
        """记录 DEBUG 级别日志"""
        self._logger.debug(message)
    
    def info(self, message: str) -> None:
        """记录 INFO 级别日志"""
        self._logger.info(message)
    
    def warning(self, message: str) -> None:
        """记录 WARNING 级别日志"""
        self._logger.warning(message)
    
    def error(self, message: str) -> None:
        """记录 ERROR 级别日志"""
        self._logger.error(message)
    
    def critical(self, message: str) -> None:
        """记录 CRITICAL 级别日志"""
        self._logger.critical(message)
    
    def exception(self, message: str) -> None:
        """记录异常信息 (包含堆栈跟踪)"""
        self._logger.exception(message)


class SignalHandler(logging.Handler):
    """
    自定义 logging.Handler，将日志消息通过 Signal 发送到 UI
    
    这是 logging 模块与 Qt Signal 机制的桥接器。
    """
    
    def __init__(self, log_manager: LogManager) -> None:
        """
        初始化 Handler
        
        Args:
            log_manager: 持有 log_emitted Signal 的 LogManager 实例
        """
        super().__init__()
        self._log_manager = log_manager
    
    def emit(self, record: logging.LogRecord) -> None:
        """
        处理日志记录并发射 Signal
        
        Args:
            record: 日志记录对象
        """
        try:
            message = self.format(record)
            # 通过 Signal 发送到 UI (线程安全)
            self._log_manager.log_emitted.emit(message)
        except Exception:
            # 防止日志处理异常导致程序崩溃
            self.handleError(record)


class StdoutRedirector(TextIO):
    """
    标准输出重定向器
    
    将 print() 输出同时发送到原始 stdout 和日志系统。
    用于捕获第三方库 (如 ultralytics) 的控制台输出。
    """
    
    def __init__(self, original: TextIO, log_manager: LogManager) -> None:
        """
        初始化重定向器
        
        Args:
            original: 原始的 sys.stdout/sys.stderr
            log_manager: 日志管理器实例
        """
        self._original = original
        self._log_manager = log_manager
    
    def write(self, text: str) -> int:
        """写入文本到原始输出和日志系统"""
        if text.strip():  # 忽略空白行
            # 发送到 GUI (去除尾部换行符)
            self._log_manager.log_emitted.emit(text.rstrip())
        # 同时写入原始输出
        return self._original.write(text)
    
    def flush(self) -> None:
        """刷新缓冲区"""
        self._original.flush()
    
    # 实现 TextIO 必需的属性和方法
    @property
    def encoding(self) -> str:
        return self._original.encoding
    
    @property  
    def errors(self) -> Optional[str]:
        return getattr(self._original, 'errors', None)
    
    def fileno(self) -> int:
        return self._original.fileno()
    
    def isatty(self) -> bool:
        return self._original.isatty()
    
    def readable(self) -> bool:
        return False
    
    def readline(self, limit: int = -1) -> str:
        return ""
    
    def readlines(self, hint: int = -1) -> list[str]:
        return []
    
    def read(self, n: int = -1) -> str:
        return ""
    
    def seek(self, offset: int, whence: int = 0) -> int:
        return 0
    
    def seekable(self) -> bool:
        return False
    
    def tell(self) -> int:
        return 0
    
    def truncate(self, size: Optional[int] = None) -> int:
        return 0
    
    def writable(self) -> bool:
        return True
    
    def writelines(self, lines: list[str]) -> None:
        for line in lines:
            self.write(line)
    
    def close(self) -> None:
        pass
    
    @property
    def closed(self) -> bool:
        return False


def get_logger() -> LogManager:
    """
    获取全局日志管理器实例
    
    Returns:
        LogManager: 全局唯一的日志管理器
    """
    return LogManager()


def setup_stdout_redirect() -> None:
    """
    设置标准输出重定向
    
    将 sys.stdout 和 sys.stderr 重定向到日志系统。
    调用此函数后，print() 的输出会自动显示在 GUI 日志面板中。
    """
    log_manager = get_logger()
    sys.stdout = StdoutRedirector(sys.__stdout__, log_manager)
    sys.stderr = StdoutRedirector(sys.__stderr__, log_manager)
