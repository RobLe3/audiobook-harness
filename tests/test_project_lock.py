import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from audiobook_harness.project import scaffold
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


def test_project_writer_lock_does_not_remove_a_replaced_lease(tmp_path: Path):
    project = tmp_path / "book"
    with project_writer_lock(project):
        (lock_path(project) / "owner.json").write_text(
            json.dumps({"pid": os.getpid(), "token": "replacement"})
        )
    assert lock_path(project).is_dir()
    assert (
        json.loads((lock_path(project) / "owner.json").read_text())["token"]
        == "replacement"
    )


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


@pytest.mark.parametrize("command", ("stage", "promote"))
def test_live_production_writer_blocks_direct_packaging_commands(
    tmp_path: Path, command: str
):
    """A packaging command must fail before it can inspect or mutate media."""
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    with project_writer_lock(project):
        result = subprocess.run(
            [sys.executable, "-m", "audiobook_harness.cli", command, str(project)],
            capture_output=True,
            text=True,
        )
    assert result.returncode != 0
    assert "locked" in result.stderr.lower()
    assert not (project / "staging").exists()
    assert not (project / "deliverables").exists()
