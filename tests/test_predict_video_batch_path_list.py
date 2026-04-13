import shutil
import sys
import types
import uuid
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if "PySide6" not in sys.modules:
    qtcore = types.ModuleType("PySide6.QtCore")

    class _SignalInstance:
        def connect(self, *args, **kwargs) -> None:
            return None

        def emit(self, *args, **kwargs) -> None:
            return None

    class _QObject:
        def __init__(self, parent=None) -> None:
            self._parent = parent

    class _QThread:
        def __init__(self, parent=None) -> None:
            self._parent = parent

        def isRunning(self) -> bool:
            return False

    def _signal(*args, **kwargs):
        return _SignalInstance()

    def _slot(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    qtcore.QObject = _QObject
    qtcore.QThread = _QThread
    qtcore.Signal = _signal
    qtcore.Slot = _slot

    pyside6 = types.ModuleType("PySide6")
    pyside6.QtCore = qtcore

    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qtcore

from core.predict_handler._video_batch import VideoBatchProcessor


def test_video_batch_generates_detected_and_empty_lists() -> None:
    tmp_root = Path(tempfile.gettempdir()) / f"video-batch-list-{uuid.uuid4().hex}"
    try:
        output_dir = tmp_root / "output"
        video_a = tmp_root / "videos" / "a.mp4"
        video_b = tmp_root / "videos" / "b.mp4"
        video_a.parent.mkdir(parents=True, exist_ok=True)
        video_a.write_bytes(b"a")
        video_b.write_bytes(b"b")

        processor = VideoBatchProcessor()
        processor._output_dir = output_dir
        processor._output_dir.mkdir(parents=True, exist_ok=True)
        processor._video_list = [video_a, video_b]
        processor._video_stats = {
            video_a: {"detection_count/检测数量": 2},
            video_b: {"detection_count/检测数量": 0},
        }
        processor._video_detection_summary = {
            video_a: {
                "max_confidence": 0.875,
                "class_names": ["truck", "person"],
            }
        }

        processor._generate_path_lists()

        detected_text = (output_dir / "detected.txt").read_text(encoding="utf-8")
        empty_text = (output_dir / "empty.txt").read_text(encoding="utf-8")

        assert "# 有检测结果的视频列表" in detected_text
        assert f"{video_a} | 0.8750 | truck, person" in detected_text
        assert "# 无检测结果的视频列表" in empty_text
        assert str(video_b) in empty_text
        assert str(video_a) not in empty_text
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
