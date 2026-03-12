"""
thread_pool.py - 后台任务管理器
============================================

职责:
    - 封装 QRunnable，提供统一的后台任务接口
    - 通过 Signal 报告任务进度、结果和错误
    - 使用 QThreadPool 管理任务队列

架构要点:
    - Worker 类封装可执行任务
    - WorkerSignals 定义通信信号 (不能直接在 QRunnable 上定义)
    - 支持任务取消功能

使用方式:
    def my_task(progress_callback):
        for i in range(100):
            # 执行工作...
            progress_callback.emit(i)
        return "任务完成"
    
    worker = Worker(my_task)
    worker.signals.finished.connect(on_finished)
    worker.signals.error.connect(on_error)
    QThreadPool.globalInstance().start(worker)
"""

from __future__ import annotations

import traceback
from typing import Any, Callable, Optional, Tuple

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


_ACTIVE_WORKERS: set["Worker"] = set()


class WorkerSignals(QObject):
    """
    Worker 专用信号容器
    
    由于 QRunnable 不能直接定义 Signal，需要通过组合模式持有 QObject 子类。
    
    Signals:
        started: 任务开始执行时发射
        finished: 任务成功完成时发射，携带返回值
        error: 任务发生异常时发射，携带 (异常类型, 异常值, 堆栈跟踪)
        progress: 任务进度更新时发射，携带进度值 (0-100)
    """
    
    started = Signal()
    finished = Signal(object)
    error = Signal(tuple)  # (exc_type, exc_value, traceback_str)
    progress = Signal(int)


class Worker(QRunnable):
    """
    可执行的后台任务封装
    
    将任意函数包装为可在 QThreadPool 中执行的任务。
    
    Attributes:
        signals: WorkerSignals 实例，用于通信
    
    Example:
        def heavy_task(data, progress_callback):
            for i, item in enumerate(data):
                # 处理数据...
                progress_callback.emit(int(i / len(data) * 100))
            return "处理完成"
        
        worker = Worker(heavy_task, my_data)
        worker.signals.finished.connect(lambda result: print(result))
        QThreadPool.globalInstance().start(worker)
    """
    
    def __init__(
        self, 
        fn: Callable[..., Any], 
        *args: Any, 
        **kwargs: Any
    ) -> None:
        """
        初始化 Worker
        
        Args:
            fn: 要在后台执行的函数
            *args: 传递给函数的位置参数
            **kwargs: 传递给函数的关键字参数
        
        Note:
            如果 fn 的第一个参数名为 progress_callback，
            将自动注入 signals.progress.emit 作为回调函数。
        """
        super().__init__()
        
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        
        # 禁用自动删除，防止任务完成后对象被立即销毁导致信号丢失
        self.setAutoDelete(False)
        
        # 取消标志
        self._is_cancelled = False
    
    def cancel(self) -> None:
        """
        请求取消任务
        
        Note:
            这只是设置取消标志，任务函数需要主动检查 is_cancelled() 来响应取消请求。
        """
        self._is_cancelled = True
    
    def is_cancelled(self) -> bool:
        """检查任务是否已被请求取消"""
        return self._is_cancelled
    
    @Slot()
    def run(self) -> None:
        """Run the worker and guard late Qt object teardown."""
        if self._is_cancelled:
            _ACTIVE_WORKERS.discard(self)
            return

        try:
            self.signals.started.emit()
        except RuntimeError:
            _ACTIVE_WORKERS.discard(self)
            return

        try:
            import inspect

            sig = inspect.signature(self.fn)
            if "progress_callback" in sig.parameters:
                result = self.fn(
                    *self.args,
                    progress_callback=self.signals.progress,
                    **self.kwargs,
                )
            else:
                result = self.fn(*self.args, **self.kwargs)

            if self._is_cancelled:
                _ACTIVE_WORKERS.discard(self)
                return

            try:
                self.signals.finished.emit(result)
            except RuntimeError:
                _ACTIVE_WORKERS.discard(self)

        except Exception as e:
            if self._is_cancelled:
                _ACTIVE_WORKERS.discard(self)
                return

            tb_str = traceback.format_exc()
            try:
                self.signals.error.emit((type(e), e, tb_str))
            except RuntimeError:
                _ACTIVE_WORKERS.discard(self)

def run_in_thread(
    fn: Callable[..., Any],
    *args: Any,
    on_finished: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Tuple], None]] = None,
    on_progress: Optional[Callable[[int], None]] = None,
    **kwargs: Any
) -> Worker:
    """
    便捷函数: 在后台线程执行任务
    
    这是创建 Worker 并提交到线程池的快捷方式。
    
    Args:
        fn: 要执行的函数
        *args: 传递给函数的位置参数
        on_finished: 任务完成时的回调
        on_error: 任务出错时的回调
        on_progress: 进度更新时的回调
        **kwargs: 传递给函数的关键字参数
    
    Returns:
        Worker: 创建的 Worker 实例 (可用于取消任务)
    """
    from PySide6.QtCore import Qt
    
    worker = Worker(fn, *args, **kwargs)
    
    # 禁用自动删除，防止任务完成时信号未处理就被删除
    worker.setAutoDelete(False)
    
    # Keep a strong reference until Qt processes the final callback.
    _ACTIVE_WORKERS.add(worker)

    # Keep the worker alive until Qt delivers the final callback.
    def cleanup(*_args: Any) -> None:
        _ACTIVE_WORKERS.discard(worker)
        try:
            worker.signals.deleteLater()
        except RuntimeError:
            pass
    worker.signals.finished.connect(cleanup, Qt.ConnectionType.QueuedConnection)
    worker.signals.error.connect(cleanup, Qt.ConnectionType.QueuedConnection)
    
    # 使用 QueuedConnection 确保信号在主线程中被处理
    if on_finished:
        worker.signals.finished.connect(on_finished, Qt.ConnectionType.QueuedConnection)
    if on_error:
        worker.signals.error.connect(on_error, Qt.ConnectionType.QueuedConnection)
    if on_progress:
        worker.signals.progress.connect(on_progress, Qt.ConnectionType.QueuedConnection)
    
    # 提交到全局线程池
    QThreadPool.globalInstance().start(worker)
    
    return worker

