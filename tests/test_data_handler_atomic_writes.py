import shutil
import uuid
from pathlib import Path

import core.data_handler as data_handler_module
from core.data_handler import DataHandler, ModifyAction


def test_modify_labels_creates_unique_backup_files() -> None:
    tmp_root = Path("D:/yolodo2.0") / f"atomic-backup-{uuid.uuid4().hex}"
    try:
        labels_dir = tmp_root / "labels"
        labels_dir.mkdir(parents=True)

        label_path = labels_dir / "a.txt"
        label_path.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
        existing_backup = labels_dir / "a.txt.bak"
        existing_backup.write_text("older backup\n", encoding="utf-8")

        handler = DataHandler()
        modified = handler.modify_labels(labels_dir, ModifyAction.REMOVE, "0", backup=True)

        assert modified == 1
        assert existing_backup.read_text(encoding="utf-8") == "older backup\n"
        assert (labels_dir / "a.txt.bak.1").read_text(encoding="utf-8") == "0 0.5 0.5 0.2 0.2\n"
        assert label_path.read_text(encoding="utf-8") == ""
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_atomic_text_write_preserves_original_file_on_replace_failure() -> None:
    tmp_root = Path("D:/yolodo2.0") / f"atomic-write-{uuid.uuid4().hex}"
    try:
        labels_dir = tmp_root / "labels"
        labels_dir.mkdir(parents=True)

        label_path = labels_dir / "a.txt"
        label_path.write_text("original\n", encoding="utf-8")

        handler = DataHandler()
        original_replace = data_handler_module.os.replace

        def failing_replace(src: str, dst: str) -> None:
            raise OSError("replace failed")

        data_handler_module.os.replace = failing_replace
        try:
            try:
                handler._write_lines_atomic(label_path, ["changed\n"])
            except OSError:
                pass
        finally:
            data_handler_module.os.replace = original_replace

        assert label_path.read_text(encoding="utf-8") == "original\n"
        assert list(labels_dir.glob("*.tmp")) == []
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
