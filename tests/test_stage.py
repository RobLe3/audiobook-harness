import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from audiobook_harness import cli
from audiobook_harness.project import scaffold, sha256
from audiobook_harness.review import build_review, finalize_review
from audiobook_harness.resilience import production_input_identity
from audiobook_harness.run_journal import write_phase_receipt
from audiobook_harness.status import render_status, write_run_status
from audiobook_harness import tts
from audiobook_harness.tts import (
    STAGE_MARKER,
    _prepare_stage_directory,
    promote,
    stage_manifest_is_valid,
    _validated_ordered_takes,
)


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


def _verified_stage(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    verification_path = project / "production/verification.json"
    verification_path.parent.mkdir(exist_ok=True)
    verification_path.write_text(json.dumps({"ok": True, "takes": []}))
    integrity_path = project / "production/candidate-selection-integrity.json"
    integrity_path.write_text('{"ok":true}')
    monkeypatch.setattr(
        tts, "audit_candidate_selection", lambda project, verification: {"ok": True}
    )
    stage = project / "staging"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir()
    media = stage / "chapter-01_Audiobook.m4a"
    media.write_text("verified")
    (stage / STAGE_MARKER).write_text("{}")
    manifest = {
        "version": 2,
        "verification_sha256": sha256(verification_path),
        "candidate_selection_integrity_sha256": sha256(integrity_path),
        "expected_files": [media.name],
        "outputs": [
            {
                "chapter": "chapter-01",
                "files": [
                    {
                        "file": media.name,
                        "sha256": sha256(media),
                        "bytes": media.stat().st_size,
                    }
                ],
            }
        ],
    }
    (stage / "stage-manifest.json").write_text(json.dumps(manifest))
    (project / "production/stage-manifest.json").write_text(json.dumps(manifest))
    review = build_review(project, stage)
    finalize_review(
        project, [{"id": row["id"], "decision": "approve"} for row in review["items"]]
    )
    return stage, media


def test_promotion_requires_current_verified_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    _verified_stage(project, monkeypatch)
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


def test_promotion_rejects_modified_and_unexpected_media(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    stage, media = _verified_stage(project, monkeypatch)
    media.write_text("modified")
    assert not stage_manifest_is_valid(project)
    with pytest.raises(RuntimeError, match="changed"):
        promote(project)
    stage, _ = _verified_stage(project, monkeypatch)
    (stage / "unexpected.txt").write_text("unexpected")
    with pytest.raises(RuntimeError, match="file set"):
        promote(project)


def test_staging_refuses_unrelated_nonempty_and_dangerous_directories(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("keep")
    with pytest.raises(RuntimeError, match="Refusing"):
        _prepare_stage_directory(project, unrelated)
    with pytest.raises(RuntimeError, match="Unsafe"):
        _prepare_stage_directory(project, project)
    assert (unrelated / "keep.txt").read_text() == "keep"


def test_staging_replaces_only_same_project_owned_directory(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    stage = _prepare_stage_directory(project, project / "staging")
    (stage / "old.bin").write_bytes(b"old")
    stage = _prepare_stage_directory(project, stage)
    assert not (stage / "old.bin").exists()
    assert (stage / STAGE_MARKER).is_file()


def test_legacy_release_command_refuses_direct_publication(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    result = subprocess.run(
        [sys.executable, "-m", "audiobook_harness.cli", "release", str(project)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "no longer writes directly" in result.stderr
    assert not (project / "deliverables").exists()


def test_repaired_middle_unit_is_restored_to_manuscript_order(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    production = project / "production"
    production.mkdir(exist_ok=True)
    units = [
        {
            "id": f"chapter-01-{index:04d}",
            "chapter_index": 1,
            "unit_index": index,
            "global_sequence": index,
        }
        for index in range(1, 4)
    ]
    (production / "analysis.json").write_text(
        json.dumps({"chapters": [{"units": units}]})
    )
    repaired_append_order = [units[0], units[2], units[1]]
    ordered = _validated_ordered_takes(project, repaired_append_order)
    assert [row["unit_index"] for row in ordered] == [1, 2, 3]


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
    write_phase_receipt(project, step=1, input_identity=identity, artifacts=[analysis])

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
