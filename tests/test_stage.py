import json
from pathlib import Path

import pytest

from audiobook_harness.project import scaffold, sha256
from audiobook_harness.status import render_status, write_run_status
from audiobook_harness.tts import promote


def test_status_writes_machine_and_readable_progress(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    write_run_status(
        project,
        state="running",
        phase="verify",
        steps=[
            {"name": "analyze", "state": "complete"},
            {"name": "verify", "state": "running"},
        ],
    )
    assert (project / "production/run-status.json").is_file()
    assert "verify" in render_status(project).read_text()


def test_promotion_requires_current_verified_stage(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    verification = {"ok": True, "takes": []}
    verification_path = project / "production/verification.json"
    verification_path.parent.mkdir(exist_ok=True)
    verification_path.write_text(json.dumps(verification))
    stage = project / "staging"
    stage.mkdir()
    (stage / "chapter-01_Audiobook.m4a").write_text("verified")
    (stage / "stage-manifest.json").write_text(
        json.dumps({"verification_sha256": sha256(verification_path), "outputs": []})
    )
    result = promote(project)
    assert result["state"] == "promoted"
    assert (project / "deliverables/chapter-01_Audiobook.m4a").read_text() == "verified"


def test_promotion_rejects_stale_verification(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    verification_path = project / "production/verification.json"
    verification_path.parent.mkdir(exist_ok=True)
    verification_path.write_text(json.dumps({"ok": True, "takes": []}))
    stage = project / "staging"
    stage.mkdir()
    (stage / "stage-manifest.json").write_text(
        json.dumps({"verification_sha256": "stale", "outputs": []})
    )
    with pytest.raises(RuntimeError, match="stale"):
        promote(project)
