import shutil
import threading
import time
import uuid
from pathlib import Path
import tempfile

from core.data_handler import DataHandler, ModifyAction


def test_modify_labels_uses_stable_class_mapping_snapshot() -> None:
    tmp_root = Path(tempfile.gettempdir()) / f"class-mapping-{uuid.uuid4().hex}"
    try:
        labels_dir = tmp_root / "labels"
        labels_dir.mkdir(parents=True)

        (tmp_root / "classes1.txt").write_text("cat\ndog\n", encoding="utf-8")
        (tmp_root / "classes2.txt").write_text("x\ny\n", encoding="utf-8")

        for name in ["a", "b", "c"]:
            (labels_dir / f"{name}.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

        handler = DataHandler()
        original_prepare = handler._prepare_modified_txt
        calls = {"count": 0}

        def slow_prepare(*args, **kwargs):
            calls["count"] += 1
            result = original_prepare(*args, **kwargs)
            if calls["count"] == 1:
                time.sleep(0.3)
            return result

        handler._prepare_modified_txt = slow_prepare

        result = {}

        def worker():
            result["count"] = handler.modify_labels(
                labels_dir,
                ModifyAction.REPLACE,
                "cat",
                "dog",
                backup=False,
                classes_txt=tmp_root / "classes1.txt",
            )

        thread = threading.Thread(target=worker)
        thread.start()
        time.sleep(0.15)
        handler.load_classes_txt(tmp_root / "classes2.txt")
        thread.join()

        assert result["count"] == 3
        for name in ["a", "b", "c"]:
            assert (labels_dir / f"{name}.txt").read_text(encoding="utf-8").startswith("1 ")
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
