import json
from pathlib import Path

from audiobook_harness.parity import feature_parity
from audiobook_harness.pipeline import PHASES, audit_pipeline, pipeline_contract


def test_pipeline_contract_declares_contiguous_eight_phase_graph():
    contract = pipeline_contract()
    assert contract["audiobook_harness_version"] == "0.4.4"
    assert [row["number"] for row in contract["phases"]] == list(range(1, 9))
    assert [phase.number for phase in PHASES] == list(range(1, 9))


def test_pipeline_audit_resumes_at_first_incomplete_phase(tmp_path: Path):
    production = tmp_path / "production"
    production.mkdir()
    for artifact in PHASES[0].required_artifacts:
        (production / artifact).write_text("{}")
    report = audit_pipeline(tmp_path)
    assert report["phase_status"][0]["complete"]
    assert report["resume_from_phase"] == 2


def test_feature_parity_is_evidence_based_not_declared(tmp_path: Path):
    production = tmp_path / "production"
    production.mkdir()
    (tmp_path / "project.yaml").write_text("title: Example\n")
    report = feature_parity(tmp_path)
    assert not report["ok"]
    first = report["capabilities"][0]
    (production / first["required_artifacts"][0]).write_text(json.dumps({"ok": True}))
    changed = feature_parity(tmp_path)
    assert changed["passing_required_capabilities"] == 1
