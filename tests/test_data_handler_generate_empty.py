import shutil
import uuid
from pathlib import Path
import tempfile

from PIL import Image

from core.data_handler import DataHandler, LabelFormat


def _create_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), "white").save(path)


def test_generate_missing_labels_writes_to_explicit_label_dir() -> None:
    tmp_root = Path(tempfile.gettempdir()) / f"generate-empty-{uuid.uuid4().hex}"
    try:
        image_dir = tmp_root / "images"
        label_dir = tmp_root / "custom_labels"
        label_dir.mkdir(parents=True)

        _create_image(image_dir / "a.jpg")
        _create_image(image_dir / "b.jpg")
        (label_dir / "a.txt").write_text("", encoding="utf-8")

        handler = DataHandler()

        preview = handler.preview_generate_missing_labels(image_dir, label_dir=label_dir)
        assert preview == {"total_images": 2, "missing_labels": 1}

        created = handler.generate_missing_labels(
            image_dir,
            LabelFormat.TXT,
            label_dir=label_dir,
        )

        assert created == 1
        assert (label_dir / "b.txt").exists()
        assert not (tmp_root / "labels" / "b.txt").exists()
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
