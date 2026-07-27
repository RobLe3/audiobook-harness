import json
from pathlib import Path

import pytest

from audiobook_harness import cli
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


def test_terminal_status_is_explicitly_historical(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    write_run_status(
        project,
        state="failed",
        phase="verify",
        steps=[{"name": "verify", "state": "running"}],
        error={"type": "RuntimeError", "message": "example"},
    )
    progress = render_status(project).read_text()
    assert "completed historical snapshot, not a live command" in progress
    assert "**Production owner:** `terminal`" in progress


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


def test_produce_repairs_failed_units_once_then_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    calls: list[tuple[str, bool]] = []
    verifications = iter(
        [
            {"ok": False, "failures": ["chapter-01-u001"]},
            {"ok": True, "failures": [], "takes": []},
        ]
    )
    monkeypatch.setattr(cli, "analyze", lambda value: {"ok": True})

    def fake_generate(value: Path, repo: Path, *, failed_only: bool = False):
        calls.append(("generate", failed_only))
        return {"ok": True}

    monkeypatch.setattr(cli, "generate", fake_generate)
    monkeypatch.setattr(
        cli,
        "verify",
        lambda value, repo, *, performance_profile: next(verifications),
    )
    monkeypatch.setattr(cli, "stage", lambda value, output: {"state": "staged"})
    result = cli.produce(
        project,
        output=None,
        performance_profile="auto",
        maximum_candidate_retries=1,
    )
    assert result["ok"]
    assert result["candidate_retries"] == 1
    assert calls == [("generate", False), ("generate", True)]
    status = json.loads((project / "production/run-status.json").read_text())
    assert status["state"] == "complete"
    assert all(row["state"] == "complete" for row in status["steps"])
