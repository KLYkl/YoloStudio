import shutil
import subprocess
import uuid
from pathlib import Path

import core.train_handler as train_handler_module
from core.train_handler import TrainManager


def test_detect_conda_envs_decodes_utf8_output(monkeypatch) -> None:
    tmp_root = Path("D:/yolodo2.0") / f"conda-env-{uuid.uuid4().hex}"
    try:
        env_path = tmp_root / "envs" / "sample"
        env_path.mkdir(parents=True)
        python_path = env_path / "python.exe"
        python_path.write_text("", encoding="utf-8")

        calls = {}

        def fake_run(cmd, capture_output, text, timeout, shell):
            calls["text"] = text
            calls["shell"] = shell
            output = f"# conda environments:\nenv✓   {env_path}\n".encode("utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout=output, stderr=b"")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(train_handler_module.sys, "platform", "win32")

        handler = TrainManager()
        envs = handler.detect_conda_envs()

        assert calls == {"text": False, "shell": True}
        assert ("env✓", str(python_path)) in envs
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
