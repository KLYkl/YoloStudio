import shutil
import sys
import types
import uuid
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

if "PySide6" not in sys.modules:
    qtcore = types.ModuleType("PySide6.QtCore")

    class _SignalInstance:
        def emit(self, *args, **kwargs) -> None:
            return None

    class _QThread:
        def __init__(self, parent=None) -> None:
            self._parent = parent

    def _signal(*args, **kwargs):
        return _SignalInstance()

    qtcore.QThread = _QThread
    qtcore.Signal = _signal

    pyside6 = types.ModuleType("PySide6")
    pyside6.QtCore = qtcore

    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qtcore

from core.data_handler import DataHandler, VideoExtractConfig


def _create_video(path: Path, frames: list, fps: float = 2.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    height, width = frames[0].shape[:2]

    writer = None
    for codec in ("MJPG", "XVID", "mp4v"):
        writer = cv2.VideoWriter(
            str(path),
            cv2.VideoWriter_fourcc(*codec),
            fps,
            (width, height),
        )
        if writer.isOpened():
            break

    if writer is None or not writer.isOpened():
        raise RuntimeError("无法创建测试视频")

    try:
        for frame in frames:
            writer.write(frame)
    finally:
        writer.release()

    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("测试视频写入失败")


def _solid_frame(color: tuple[int, int, int], size: tuple[int, int] = (32, 32)):
    return np.full((size[1], size[0], 3), color, dtype=np.uint8)


def test_scan_videos_counts_root_and_subdirs() -> None:
    tmp_root = Path("D:/yolodo2.0") / f"video-scan-{uuid.uuid4().hex}"
    try:
        video_dir = tmp_root / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        (video_dir / "a.avi").write_bytes(b"fake")
        (video_dir / "ignore.txt").write_text("x", encoding="utf-8")
        (video_dir / "sub" / "b.mp4").parent.mkdir(parents=True, exist_ok=True)
        (video_dir / "sub" / "b.mp4").write_bytes(b"fake")
        (video_dir / "_hidden" / "c.mkv").parent.mkdir(parents=True, exist_ok=True)
        (video_dir / "_hidden" / "c.mkv").write_bytes(b"fake")

        handler = DataHandler()
        stats = handler.scan_videos(video_dir)

        assert stats == {".": 1, "sub": 1}
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


@pytest.mark.parametrize(
    ("mode", "config_kwargs"),
    [
        ("interval", {"frame_interval": 2}),
        ("time", {"time_interval": 1.0}),
    ],
)
def test_extract_video_frames_supports_interval_and_time_modes(
    mode: str,
    config_kwargs: dict,
) -> None:
    tmp_root = Path("D:/yolodo2.0") / f"video-extract-{mode}-{uuid.uuid4().hex}"
    try:
        video_path = tmp_root / "sample.avi"
        output_dir = tmp_root / "frames"
        frames = [
            _solid_frame((0, 0, 255)),
            _solid_frame((0, 255, 0)),
            _solid_frame((255, 0, 0)),
            _solid_frame((0, 255, 255)),
            _solid_frame((255, 255, 0)),
            _solid_frame((255, 0, 255)),
        ]
        _create_video(video_path, frames, fps=2.0)

        handler = DataHandler()
        config = VideoExtractConfig(
            mode=mode,
            enable_dedup=False,
            output_dir=output_dir,
            **config_kwargs,
        )

        result = handler.extract_video_frames(video_path, config)

        saved_frames = sorted(output_dir.glob("*.jpg"))
        assert result.total_frames == 6
        assert result.extracted == 3
        assert result.dedup_removed == 0
        assert result.final_count == 3
        assert result.video_stats == {"sample.avi": 3}
        assert len(saved_frames) == 3
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_extract_video_frames_supports_scene_mode() -> None:
    tmp_root = Path("D:/yolodo2.0") / f"video-scene-{uuid.uuid4().hex}"
    try:
        video_path = tmp_root / "scene.avi"
        output_dir = tmp_root / "frames"
        frames = [
            _solid_frame((0, 0, 255)),
            _solid_frame((0, 0, 255)),
            _solid_frame((0, 255, 0)),
            _solid_frame((0, 255, 0)),
            _solid_frame((255, 0, 0)),
            _solid_frame((255, 0, 0)),
        ]
        _create_video(video_path, frames, fps=2.0)

        handler = DataHandler()
        config = VideoExtractConfig(
            mode="scene",
            scene_threshold=0.1,
            min_scene_gap=1,
            enable_dedup=False,
            output_dir=output_dir,
        )

        result = handler.extract_video_frames(video_path, config)

        assert result.extracted == 3
        assert result.final_count == 3
        assert len(list(output_dir.glob("*.jpg"))) == 3
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_extract_video_frames_deduplicates_identical_frames() -> None:
    pytest.importorskip("imagehash")

    tmp_root = Path("D:/yolodo2.0") / f"video-dedup-{uuid.uuid4().hex}"
    try:
        video_path = tmp_root / "dup.avi"
        output_dir = tmp_root / "frames"
        frames = [_solid_frame((64, 64, 64)) for _ in range(4)]
        _create_video(video_path, frames, fps=2.0)

        handler = DataHandler()
        config = VideoExtractConfig(
            mode="interval",
            frame_interval=1,
            enable_dedup=True,
            dedup_threshold=0,
            output_dir=output_dir,
        )

        result = handler.extract_video_frames(video_path, config)

        assert result.extracted == 4
        assert result.dedup_removed == 3
        assert result.final_count == 1
        assert len(list(output_dir.glob("*.jpg"))) == 1
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
