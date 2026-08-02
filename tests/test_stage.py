import json
import errno
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import numpy as np
import soundfile as sf

from audiobook_harness import cli
from audiobook_harness.project import scaffold, sha256
from audiobook_harness.review import build_review, finalize_review
from audiobook_harness.run_journal import phase_receipt_is_valid, write_phase_receipt
from audiobook_harness.status import render_status, write_run_status
from audiobook_harness import tts
from audiobook_harness.tts import (
    STAGE_MARKER,
    _prepare_stage_directory,
    promote,
    stage_manifest_is_valid,
    _validated_ordered_takes,
    _package,
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


def test_assembly_inserts_planned_pause_and_protected_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project = tmp_path / "book"
    (project / "production").mkdir(parents=True)
    source = project / "assets/candidates/ch1/u1/take.flac"
    source.parent.mkdir(parents=True)
    sf.write(source, np.ones(2400, dtype=np.float32) * 0.1, 24000)
    (project / "project.yaml").write_text("outputs: [flac]\n")
    (project / "production/analysis.json").write_text(
        json.dumps(
            {
                "chapters": [
                    {
                        "units": [
                            {
                                "id": "u1",
                                "chapter_index": 1,
                                "unit_index": 1,
                                "global_sequence": 1,
                            }
                        ]
                    }
                ]
            }
        )
    )
    (project / "production/discourse-prosody-map.json").write_text(
        json.dumps({"units": [{"unit": "u1", "pause_target_ms": 400}]})
    )

    def fake_run(command, **kwargs):
        shutil.copy2(command[command.index("-i") + 1], command[-1])
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = project / "staging"
    output.mkdir()
    _package(
        project,
        [
            {
                "id": "u1",
                "chapter": "ch1",
                "chapter_index": 1,
                "unit_index": 1,
                "global_sequence": 1,
                "file": str(source.relative_to(project)),
                "sha256": sha256(source),
            }
        ],
        output,
    )
    manifest = json.loads((project / "production/assembly-manifest.json").read_text())
    assert manifest["chapters"][0]["units"][0]["pause_after_ms"] == 1500
    assert manifest["chapters"][0]["duration_seconds"] >= 1.59


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
    assert review["version"] == 3
    assert review["audiobook_harness_version"] == "0.5.4"
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


def test_promotion_rejects_manifest_path_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    _verified_stage(project, monkeypatch)
    stage_manifest = project / "staging/stage-manifest.json"
    value = json.loads(stage_manifest.read_text())
    value["expected_files"] = ["../outside.m4a"]
    stage_manifest.write_text(json.dumps(value))
    with pytest.raises(RuntimeError, match="file set or media hashes"):
        promote(project)


def test_promotion_failure_restores_previous_deliverables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    _verified_stage(project, monkeypatch)
    deliverables = project / "deliverables"
    deliverables.mkdir()
    (deliverables / "previous.m4a").write_text("known-good")

    original_replace = Path.replace

    def fail_install(self: Path, target: Path):
        if self.name == "deliverables.next":
            raise OSError("simulated promotion interruption")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_install)
    with pytest.raises(OSError, match="promotion interruption"):
        promote(project)
    assert (deliverables / "previous.m4a").read_text() == "known-good"
    assert not (project / "deliverables.next").exists()


def test_promotion_receipt_failure_restores_previous_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    _verified_stage(project, monkeypatch)
    deliverables = project / "deliverables"
    deliverables.mkdir()
    (deliverables / "previous.m4a").write_text("known-good")
    release_manifest = project / "production/release-manifest.json"
    release_manifest.write_text('{"state":"previous"}')
    original_write_json = tts.write_json

    def fail_release(path: Path, value: object) -> None:
        if path.name == "release-manifest.json":
            raise OSError("simulated receipt interruption")
        original_write_json(path, value)

    monkeypatch.setattr(tts, "write_json", fail_release)
    with pytest.raises(OSError, match="receipt interruption"):
        promote(project)
    assert (deliverables / "previous.m4a").read_text() == "known-good"
    assert json.loads(release_manifest.read_text()) == {"state": "previous"}


def test_promotion_copy_failure_restores_previous_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    _verified_stage(project, monkeypatch)
    deliverables = project / "deliverables"
    deliverables.mkdir()
    (deliverables / "previous.m4a").write_text("known-good")
    original_copy = tts.shutil.copy2

    def fail_copy(source: Path, destination: Path, *args: object, **kwargs: object):
        if destination.parent.name == "deliverables.next":
            raise OSError("simulated media-copy interruption")
        return original_copy(source, destination, *args, **kwargs)

    monkeypatch.setattr(tts.shutil, "copy2", fail_copy)
    with pytest.raises(OSError, match="media-copy interruption"):
        promote(project)
    assert (deliverables / "previous.m4a").read_text() == "known-good"
    assert not (project / "deliverables.next").exists()


@pytest.mark.parametrize(
    "error",
    [
        PermissionError("simulated permission denied"),
        OSError(errno.ENOSPC, "disk full"),
    ],
)
def test_promotion_copy_storage_failures_restore_previous_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError
):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    _verified_stage(project, monkeypatch)
    deliverables = project / "deliverables"
    deliverables.mkdir()
    (deliverables / "previous.m4a").write_text("known-good")

    def fail_copy(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(tts.shutil, "copy2", fail_copy)
    with pytest.raises(type(error)):
        promote(project)
    assert (deliverables / "previous.m4a").read_text() == "known-good"
    assert not (project / "deliverables.next").exists()


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


def test_staging_refuses_a_symbolic_linked_output_path(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    target = tmp_path / "actual-stage"
    target.mkdir()
    linked = tmp_path / "linked-stage"
    linked.symlink_to(target, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symbolic link"):
        tts.stage(project, linked)
    assert list(target.iterdir()) == []


def test_staging_refuses_a_symbolic_linked_ownership_marker(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    stage = project / "staging"
    stage.mkdir()
    outside = tmp_path / "outside-marker.json"
    outside.write_text(json.dumps({"project": str(project.resolve())}))
    (stage / STAGE_MARKER).symlink_to(outside)

    with pytest.raises(RuntimeError, match="not owned"):
        _prepare_stage_directory(project, stage)
    assert outside.is_file()
    assert (stage / STAGE_MARKER).is_symlink()


def test_staging_replaces_only_same_project_owned_directory(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    stage = _prepare_stage_directory(project, project / "staging")
    (stage / "old.bin").write_bytes(b"old")
    stage = _prepare_stage_directory(project, stage)
    assert not (stage / "old.bin").exists()
    assert (stage / STAGE_MARKER).is_file()


def test_staging_failure_restores_previous_owned_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    target = project / "staging"
    target.mkdir()
    (target / STAGE_MARKER).write_text(json.dumps({"project": str(project.resolve())}))
    (target / "previous.txt").write_text("known-good")

    monkeypatch.setattr(tts, "_stage_into", lambda _project, _output, **_kwargs: {})

    original_replace = Path.replace

    def fail_install(self: Path, destination: Path):
        if self.name.startswith(".staging.phase-8-"):
            raise OSError("simulated staging interruption")
        return original_replace(self, destination)

    monkeypatch.setattr(Path, "replace", fail_install)
    with pytest.raises(OSError, match="staging interruption"):
        tts.stage(project, target)
    assert (target / "previous.txt").read_text() == "known-good"


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


def test_produce_repeats_distinct_repairs_then_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    calls: list[tuple[str, bool]] = []
    verifications = iter(
        [
            {"ok": False, "failures": ["chapter-01-u001"]},
            {"ok": False, "failures": ["chapter-01-u002"]},
            {"ok": True, "failures": [], "takes": []},
        ]
    )

    def fake_analyze(value: Path):
        for name in cli.PHASES[0].required_artifacts:
            (value / "production" / name).write_text('{"ok":true}')
        return {"ok": True}

    monkeypatch.setattr(cli, "analyze", fake_analyze)

    def fake_generate(value: Path, repo: Path, *, failed_only: bool = False):
        calls.append(("generate", failed_only))
        (value / "production/candidates.json").write_text('{"candidates":[]}')
        (value / "production/generation.json").write_text('{"takes":[],"ok":true}')
        (value / "production/candidate-plan.json").write_text('{"ok":true}')
        (value / "production/pronunciation-context-preflight.json").write_text(
            '{"ok":true}'
        )
        return {"ok": True}

    monkeypatch.setattr(cli, "generate", fake_generate)

    def fake_verify(value: Path, repo: Path, *, performance_profile: str):
        result = next(verifications)
        (value / "production/verification.json").write_text(json.dumps(result))
        (value / "production/forced-alignment.json").write_text('{"ok":true}')
        (value / "production/candidate-selection-integrity.json").write_text(
            '{"ok":true}'
        )
        (value / "production/candidate-strategy-ledger.json").write_text(
            '{"version":1,"units":[]}'
        )
        (value / "production/quality-measurements.json").write_text('{"ok":true}')
        for name in cli.PHASES[3].required_artifacts:
            path = value / "production" / name
            if not path.exists():
                path.write_text('{"ok":true}')
        if not result.get("ok"):
            (value / "production/repair-plan.json").write_text(
                json.dumps(
                    {
                        "ok": False,
                        "repairs": [
                            {
                                "unit": "chapter-01-u001",
                                "strategy": {"id": "bounded_pace_resynthesis"},
                            }
                        ],
                    }
                )
            )
        return result

    monkeypatch.setattr(cli, "verify", fake_verify)

    monkeypatch.setattr(
        cli,
        "realize_generation_manifest",
        lambda value: json.loads((value / "production/generation.json").read_text()),
    )

    def fake_phase(value: Path, phase: int):
        for name in cli.PHASES[phase - 1].required_artifacts:
            (value / "production" / name).write_text('{"ok":true}')
        return {"ok": True}

    monkeypatch.setattr(
        cli, "prepare_release_contract", lambda value: fake_phase(value, 5)
    )
    monkeypatch.setattr(cli, "assemble_selected", lambda value: fake_phase(value, 6))
    monkeypatch.setattr(cli, "post_mix_quality", lambda value: fake_phase(value, 7))

    def fake_stage(
        value: Path, output: Path | None, *, reuse_verified_phases: bool = False
    ):
        result = {"state": "staged"}
        fake_phase(value, 8)
        (value / "production/stage-manifest.json").write_text(json.dumps(result))
        return result

    monkeypatch.setattr(cli, "stage", fake_stage)
    result = cli.produce(
        project,
        output=None,
        performance_profile="auto",
        maximum_candidate_retries=2,
    )
    assert result["ok"]
    assert result["candidate_retries"] == 2
    assert calls == [("generate", False), ("generate", True), ("generate", True)]
    for phase in cli.PHASES:
        assert phase_receipt_is_valid(
            project,
            step=phase.number,
            input_identity=cli.phase_input_identity(project, cli.REPO, phase),
        )
    status = json.loads((project / "production/run-status.json").read_text())
    assert status["state"] == "complete"
    assert all(row["state"] == "complete" for row in status["steps"])
    iterations = (
        (project / "production/convergence-iterations.jsonl").read_text().splitlines()
    )
    assert len(iterations) == 2
    assert json.loads(iterations[-1])["state"] == "objective_pass"


def test_produce_resume_dry_run_starts_at_first_missing_phase(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    analysis = project / "production/analysis.json"
    analysis.parent.mkdir(parents=True, exist_ok=True)
    analysis.write_text('{"ok":true}', encoding="utf-8")
    identity = cli.phase_input_identity(project, cli.REPO, cli.PHASES[0])
    for name in cli.PHASES[0].required_artifacts:
        (project / "production" / name).write_text('{"ok":true}')
    write_phase_receipt(
        project,
        step=1,
        input_identity=identity,
        artifacts=[
            project / "production" / name for name in cli.PHASES[0].required_artifacts
        ],
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


def test_failed_phase8_build_preserves_previous_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from audiobook_harness import tts

    project = tmp_path / "book"
    project.mkdir()
    target = project / "staging"
    target.mkdir()
    (target / tts.STAGE_MARKER).write_text(
        json.dumps({"project": str(project.resolve())})
    )
    (target / "approved.m4a").write_bytes(b"approved")

    def fail_into(value: Path, output: Path, *, reuse_verified_phases: bool):
        output.mkdir(parents=True)
        (output / "partial.m4a").write_bytes(b"partial")
        raise RuntimeError("encoder failed")

    monkeypatch.setattr(tts, "_stage_into", fail_into)
    with pytest.raises(RuntimeError, match="encoder failed"):
        tts.stage(project, target, reuse_verified_phases=True)
    assert (target / "approved.m4a").read_bytes() == b"approved"
    assert not (target / "partial.m4a").exists()
