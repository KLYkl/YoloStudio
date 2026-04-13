import shutil
import uuid
from pathlib import Path
import tempfile

from PIL import Image

from core.data_handler import DataHandler, ModifyAction


def _create_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32), "white").save(path)


def test_modify_labels_without_label_dir_only_touches_image_matched_labels() -> None:
    tmp_root = Path(tempfile.gettempdir()) / f"modify-scope-{uuid.uuid4().hex}"
    try:
        image_dir = tmp_root / "images"
        labels_dir = tmp_root / "labels"
        converted_dir = tmp_root / "converted_labels_txt"
        labels_dir.mkdir(parents=True)
        converted_dir.mkdir(parents=True)

        _create_image(image_dir / "a.jpg")
        (labels_dir / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
        (converted_dir / "b.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

        handler = DataHandler()

        preview = handler.preview_modify_labels(
            tmp_root,
            ModifyAction.REMOVE,
            "0",
            image_dir=image_dir,
        )
        assert preview["total_label_files"] == 1
        assert preview["matched_files"] == 1
        assert preview["matched_annotations"] == 1

        modified = handler.modify_labels(
            tmp_root,
            ModifyAction.REMOVE,
            "0",
            backup=False,
            image_dir=image_dir,
        )

        assert modified == 1
        assert (labels_dir / "a.txt").read_text(encoding="utf-8") == ""
        assert (converted_dir / "b.txt").read_text(encoding="utf-8") == "0 0.5 0.5 0.2 0.2\n"
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
