import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from audiobook_harness.project_lock import lock_path, project_writer_lock


def test_project_writer_lock_rejects_live_owner(tmp_path: Path):
    project = tmp_path / "book"
    path = lock_path(project)
    path.mkdir(parents=True)
    (path / "owner.json").write_text(json.dumps({"pid": os.getpid()}))
    with pytest.raises(RuntimeError, match="active writer lock"):
        with project_writer_lock(project):
            pass


def test_project_writer_lock_removes_stale_owner(tmp_path: Path):
    project = tmp_path / "book"
    path = lock_path(project)
    path.mkdir(parents=True)
    (path / "owner.json").write_text(json.dumps({"pid": 99999999}))
    with project_writer_lock(project):
        assert (
            json.loads((lock_path(project) / "owner.json").read_text())["pid"]
            == os.getpid()
        )
    assert not lock_path(project).exists()


def test_project_writer_lock_rejects_a_second_process(tmp_path: Path):
    project = tmp_path / "book"
    with project_writer_lock(project):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from pathlib import Path\n"
                    "from audiobook_harness.project_lock import project_writer_lock\n"
                    f"with project_writer_lock(Path({str(project)!r})): pass"
                ),
            ],
            capture_output=True,
            text=True,
        )
    assert result.returncode != 0
    assert "locked" in result.stderr.lower()
