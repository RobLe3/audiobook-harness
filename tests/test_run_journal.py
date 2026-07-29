from pathlib import Path

from audiobook_harness.run_journal import (
    phase_receipt_is_valid,
    receipt_is_valid,
    write_phase_receipt,
    write_stage_receipt,
)


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
        tmp_path / "receipt.json", run_id="run", chapter_id="01", quality_report=report, media=media, dependency_fingerprint="identity-a"
    )
    assert receipt_is_valid(receipt, run_id="run", chapter_id="01", stage=stage,
                            quality_report=report, expected_names={item.name for item in media}, dependency_fingerprint="identity-a")
    (stage / "chapter.mp3").write_bytes(b"changed")
    assert not receipt_is_valid(receipt, run_id="run", chapter_id="01", stage=stage,
                                quality_report=report, expected_names={item.name for item in media}, dependency_fingerprint="identity-a")


def test_stage_receipt_rejects_dependency_drift(tmp_path: Path):
    stage = tmp_path / "stage"
    stage.mkdir()
    report = tmp_path / "quality.json"
    report.write_text("{}")
    media = stage / "chapter.m4a"
    media.write_bytes(b"verified")
    receipt = write_stage_receipt(
        tmp_path / "receipt.json", run_id="run", chapter_id="01",
        quality_report=report, media=[media], dependency_fingerprint="inputs-a",
    )
    assert receipt_is_valid(receipt, run_id="run", chapter_id="01", stage=stage,
                            quality_report=report, expected_names={media.name},
                            dependency_fingerprint="inputs-a")
    assert not receipt_is_valid(receipt, run_id="run", chapter_id="01", stage=stage,
                                quality_report=report, expected_names={media.name},
                                dependency_fingerprint="inputs-b")


def test_phase_receipt_reuses_only_matching_inputs_and_bytes(tmp_path: Path):
    project = tmp_path / "book"
    artifact = project / "production/analysis.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"ok":true}', encoding="utf-8")
    write_phase_receipt(
        project, step=1, input_identity="inputs-a", artifacts=[artifact]
    )
    assert phase_receipt_is_valid(
        project, step=1, input_identity="inputs-a"
    )
    assert not phase_receipt_is_valid(
        project, step=1, input_identity="inputs-b"
    )
    artifact.write_text('{"ok":false}', encoding="utf-8")
    assert not phase_receipt_is_valid(
        project, step=1, input_identity="inputs-a"
    )


def test_missing_phase_receipt_does_not_invalidate_earlier_receipt(tmp_path: Path):
    project = tmp_path / "book"
    artifact = project / "production/analysis.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")
    write_phase_receipt(
        project, step=1, input_identity="inputs", artifacts=[artifact]
    )
    assert phase_receipt_is_valid(project, step=1, input_identity="inputs")
    assert not phase_receipt_is_valid(project, step=2, input_identity="inputs")
