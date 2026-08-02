from pathlib import Path

import pytest

from audiobook_harness.run_journal import (
    invalidate_phase_receipts_from,
    phase_receipt_is_valid,
    receipt_is_valid,
    write_phase_receipt,
    write_stage_receipt,
    valid_phase_repair_receipt,
    write_phase_repair_receipt,
)


def test_phase_failure_invalidates_current_and_downstream_only(tmp_path: Path):
    artifact = tmp_path / "production/artifact.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"ok": true}')
    for step in range(1, 5):
        write_phase_receipt(
            tmp_path, step=step, input_identity="inputs", artifacts=[artifact]
        )
    invalidate_phase_receipts_from(tmp_path, step=3)
    assert phase_receipt_is_valid(tmp_path, step=1, input_identity="inputs")
    assert phase_receipt_is_valid(tmp_path, step=2, input_identity="inputs")
    assert not phase_receipt_is_valid(tmp_path, step=3, input_identity="inputs")
    assert not phase_receipt_is_valid(tmp_path, step=4, input_identity="inputs")


def test_stage_receipt_rejects_changed_output(tmp_path: Path):
    stage = tmp_path / "stage"
    stage.mkdir()
    report = tmp_path / "quality.json"
    report.write_text("{}")
    media = []
    for name in ("chapter.m4a", "chapter.mp3", "chapter.mp4"):
        path = stage / name
        path.write_bytes(name.encode())
        media.append(path)
    receipt = write_stage_receipt(
        tmp_path / "receipt.json",
        run_id="run",
        chapter_id="01",
        quality_report=report,
        media=media,
        dependency_fingerprint="identity-a",
    )
    assert receipt_is_valid(
        receipt,
        run_id="run",
        chapter_id="01",
        stage=stage,
        quality_report=report,
        expected_names={item.name for item in media},
        dependency_fingerprint="identity-a",
    )
    (stage / "chapter.mp3").write_bytes(b"changed")
    assert not receipt_is_valid(
        receipt,
        run_id="run",
        chapter_id="01",
        stage=stage,
        quality_report=report,
        expected_names={item.name for item in media},
        dependency_fingerprint="identity-a",
    )


def test_stage_receipt_rejects_dependency_drift(tmp_path: Path):
    stage = tmp_path / "stage"
    stage.mkdir()
    report = tmp_path / "quality.json"
    report.write_text("{}")
    media = stage / "chapter.m4a"
    media.write_bytes(b"verified")
    receipt = write_stage_receipt(
        tmp_path / "receipt.json",
        run_id="run",
        chapter_id="01",
        quality_report=report,
        media=[media],
        dependency_fingerprint="inputs-a",
    )
    assert receipt_is_valid(
        receipt,
        run_id="run",
        chapter_id="01",
        stage=stage,
        quality_report=report,
        expected_names={media.name},
        dependency_fingerprint="inputs-a",
    )
    assert not receipt_is_valid(
        receipt,
        run_id="run",
        chapter_id="01",
        stage=stage,
        quality_report=report,
        expected_names={media.name},
        dependency_fingerprint="inputs-b",
    )


def test_phase_receipt_reuses_only_matching_inputs_and_bytes(tmp_path: Path):
    project = tmp_path / "book"
    artifact = project / "production/analysis.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"ok":true}', encoding="utf-8")
    write_phase_receipt(
        project, step=1, input_identity="inputs-a", artifacts=[artifact]
    )
    assert phase_receipt_is_valid(project, step=1, input_identity="inputs-a")
    assert not phase_receipt_is_valid(project, step=1, input_identity="inputs-b")
    artifact.write_text('{"ok":false}', encoding="utf-8")
    assert not phase_receipt_is_valid(project, step=1, input_identity="inputs-a")


def test_missing_phase_receipt_does_not_invalidate_earlier_receipt(tmp_path: Path):
    project = tmp_path / "book"
    artifact = project / "production/analysis.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")
    write_phase_receipt(project, step=1, input_identity="inputs", artifacts=[artifact])
    assert phase_receipt_is_valid(project, step=1, input_identity="inputs")
    assert not phase_receipt_is_valid(project, step=2, input_identity="inputs")


def test_corrupt_phase_receipt_is_never_reusable(tmp_path: Path):
    project = tmp_path / "book"
    artifact = project / "production/analysis.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")
    write_phase_receipt(project, step=1, input_identity="inputs", artifacts=[artifact])
    receipt = project / "production/phase-receipts/step-1.json"
    receipt.write_text('{"step":1,"artifacts":[{"path":"../../outside"}]}')
    assert not phase_receipt_is_valid(project, step=1, input_identity="inputs")


def test_duplicate_stage_media_names_are_rejected(tmp_path: Path):
    stage = tmp_path / "stage"
    stage.mkdir()
    report = tmp_path / "quality.json"
    report.write_text("{}")
    media = stage / "chapter.m4a"
    media.write_bytes(b"verified")
    with pytest.raises(ValueError, match="duplicate media name"):
        write_stage_receipt(
            tmp_path / "receipt.json",
            run_id="run",
            chapter_id="01",
            quality_report=report,
            media=[media, media],
            dependency_fingerprint="inputs",
        )


def test_stage_receipt_rejects_media_from_multiple_directories(tmp_path: Path):
    report = tmp_path / "quality.json"
    report.write_text("{}")
    primary = tmp_path / "stage/chapter.m4a"
    primary.parent.mkdir()
    primary.write_bytes(b"verified")
    other = tmp_path / "other/chapter.mp3"
    other.parent.mkdir()
    other.write_bytes(b"verified")
    with pytest.raises(ValueError, match="one direct stage directory"):
        write_stage_receipt(
            tmp_path / "receipt.json",
            run_id="run",
            chapter_id="01",
            quality_report=report,
            media=[primary, other],
        )


def test_phase_repair_receipt_is_objective_and_hash_bound(tmp_path: Path):
    project = tmp_path
    dependency = tmp_path / "repair.py"
    dependency.write_text("fixed")
    evidence = tmp_path / "production/evidence.json"
    evidence.parent.mkdir()
    evidence.write_text('{"ok": true}')
    write_phase_repair_receipt(
        project,
        owner_phase=4,
        base_input_identity="old",
        current_input_identity="new",
        changed_dependencies=[dependency],
        evidence=[evidence],
    )
    assert valid_phase_repair_receipt(project, current_input_identity="new") is not None
    dependency.write_text("drifted")
    assert valid_phase_repair_receipt(project, current_input_identity="new") is None


def test_phase_repair_rejects_failed_evidence(tmp_path: Path):
    dependency = tmp_path / "repair.py"
    dependency.write_text("fixed")
    evidence = tmp_path / "production/evidence.json"
    evidence.parent.mkdir()
    evidence.write_text('{"ok": false}')
    import pytest

    with pytest.raises(ValueError, match="not objectively passing"):
        write_phase_repair_receipt(
            tmp_path,
            owner_phase=4,
            base_input_identity="old",
            current_input_identity="new",
            changed_dependencies=[dependency],
            evidence=[evidence],
        )
