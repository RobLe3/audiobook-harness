from pathlib import Path

from audiobook_harness.run_journal import receipt_is_valid, write_stage_receipt


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
        tmp_path / "receipt.json", run_id="run", chapter_id="01", quality_report=report, media=media
    )
    assert receipt_is_valid(receipt, run_id="run", chapter_id="01", stage=stage,
                            quality_report=report, expected_names={item.name for item in media})
    (stage / "chapter.mp3").write_bytes(b"changed")
    assert not receipt_is_valid(receipt, run_id="run", chapter_id="01", stage=stage,
                                quality_report=report, expected_names={item.name for item in media})
