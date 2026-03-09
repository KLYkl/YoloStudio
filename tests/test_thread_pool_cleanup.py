import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from core.thread_pool import Worker, _ACTIVE_WORKERS
from ui.train_widget import TrainWidget


class _RaisingSignal:
    def emit(self, *_args, **_kwargs) -> None:
        raise RuntimeError("Signal source has been deleted")


class _PassiveSignal:
    def __init__(self) -> None:
        self.calls = []

    def emit(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))


class _StubSignals:
    def __init__(self) -> None:
        self.started = _RaisingSignal()
        self.finished = _PassiveSignal()
        self.error = _PassiveSignal()
        self.progress = _PassiveSignal()

    def deleteLater(self) -> None:
        pass


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_worker_run_ignores_deleted_started_signal() -> None:
    worker = Worker(lambda: "ok")
    worker.signals = _StubSignals()
    _ACTIVE_WORKERS.add(worker)

    worker.run()

    assert worker not in _ACTIVE_WORKERS


def test_train_widget_close_cancels_scan_worker(monkeypatch) -> None:
    _app()
    monkeypatch.setattr(TrainWidget, "_scan_envs", lambda self: None)

    widget = TrainWidget()
    worker = Worker(lambda: "ok")
    widget._scan_worker = worker

    widget.close()

    assert worker.is_cancelled() is True
    assert widget._scan_worker is None
