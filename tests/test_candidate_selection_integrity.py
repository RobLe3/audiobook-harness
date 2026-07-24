import json
from pathlib import Path

from audiobook_harness.project import scaffold, sha256
from audiobook_harness.selection_integrity import audit_candidate_selection


def _project_with_selection(tmp_path: Path) -> Path:
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    candidate = project / "assets/generated/candidates/chapter-01/u-0001/baseline-proof.flac"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"verified candidate bytes")
    row = {
        "id": "u-0001",
        "candidate": "baseline",
        "file": str(candidate.relative_to(project)),
        "sha256": sha256(candidate),
        "source_hash": "source-proof",
    }
    manifest = project / "production/candidates.json"
    manifest.parent.mkdir(exist_ok=True)
    manifest.write_text(json.dumps({"candidates": [row]}), encoding="utf-8")
    verification = {
        "ok": True,
        "candidate_manifest_sha256": sha256(manifest),
        "takes": [row],
    }
    (project / "production/verification.json").write_text(
        json.dumps(verification), encoding="utf-8"
    )
    return project


def test_current_candidate_selection_is_accepted(tmp_path: Path):
    project = _project_with_selection(tmp_path)
    assert audit_candidate_selection(project)["ok"] is True


def test_rewritten_selected_audio_is_rejected(tmp_path: Path):
    project = _project_with_selection(tmp_path)
    candidate = project / "assets/generated/candidates/chapter-01/u-0001/baseline-proof.flac"
    candidate.write_bytes(b"different candidate bytes")
    report = audit_candidate_selection(project)
    assert report["ok"] is False
    assert report["errors"][0]["rule"] == "selected_audio_hash_mismatch"


def test_changed_candidate_manifest_is_rejected(tmp_path: Path):
    project = _project_with_selection(tmp_path)
    manifest = project / "production/candidates.json"
    manifest.write_text(json.dumps({"candidates": []}), encoding="utf-8")
    report = audit_candidate_selection(project)
    assert report["ok"] is False
    assert any(
        row["rule"] == "candidate_manifest_hash_mismatch" for row in report["errors"]
    )
