import json
from pathlib import Path

import pytest

from audiobook_harness import cli
from audiobook_harness.project import scaffold, sha256
from audiobook_harness.resilience import production_input_identity
from audiobook_harness.run_journal import write_phase_receipt
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
    def fake_analyze(value: Path):
        (value / "production/analysis.json").write_text('{"ok":true}')
        return {"ok": True}

    monkeypatch.setattr(cli, "analyze", fake_analyze)

    def fake_generate(value: Path, repo: Path, *, failed_only: bool = False):
        calls.append(("generate", failed_only))
        (value / "production/candidates.json").write_text('{"candidates":[]}')
        (value / "production/generation.json").write_text('{"takes":[]}')
        return {"ok": True}

    monkeypatch.setattr(cli, "generate", fake_generate)
    def fake_verify(value: Path, repo: Path, *, performance_profile: str):
        result = next(verifications)
        (value / "production/verification.json").write_text(json.dumps(result))
        (value / "production/forced-alignment.json").write_text('{"ok":true}')
        return result

    monkeypatch.setattr(cli, "verify", fake_verify)

    def fake_stage(value: Path, output: Path | None):
        result = {"state": "staged"}
        (value / "production/stage-manifest.json").write_text(json.dumps(result))
        return result

    monkeypatch.setattr(cli, "stage", fake_stage)
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


def test_produce_resume_dry_run_starts_at_first_missing_phase(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    analysis = project / "production/analysis.json"
    analysis.parent.mkdir(parents=True, exist_ok=True)
    analysis.write_text('{"ok":true}', encoding="utf-8")
    identity = production_input_identity(project, cli.REPO)
    write_phase_receipt(
        project, step=1, input_identity=identity, artifacts=[analysis]
    )

    result = cli.produce(
        project,
        output=None,
        performance_profile="auto",
        maximum_candidate_retries=1,
        resume=True,
        dry_run=True,
    )

    assert result["phases"][0]["action"] == "REUSE"
    assert all(row["action"] == "RUN" for row in result["phases"][1:])
