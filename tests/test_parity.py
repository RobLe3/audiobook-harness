import json
from pathlib import Path

from audiobook_harness.parity import feature_parity
from audiobook_harness.pipeline import (
    PHASES,
    audit_pipeline,
    pipeline_contract,
    resume_plan,
)
from audiobook_harness.run_journal import (
    write_phase_receipt,
    write_phase_repair_receipt,
)


def test_pipeline_contract_declares_contiguous_eight_phase_graph():
    contract = pipeline_contract()
    assert contract["audiobook_harness_version"] == "0.5.5"
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


def test_phase_scoped_repair_keeps_only_valid_predecessors(tmp_path: Path):
    production = tmp_path / "production"
    production.mkdir()
    for step in (1, 2, 3):
        artifact = production / f"step-{step}.json"
        artifact.write_text('{"ok": true}')
        write_phase_receipt(
            tmp_path, step=step, input_identity="old", artifacts=[artifact]
        )
    dependency = tmp_path / "changed.py"
    dependency.write_text("fixed")
    evidence = production / "repair-evidence.json"
    evidence.write_text('{"ok": true}')
    write_phase_repair_receipt(
        tmp_path,
        owner_phase=4,
        base_input_identity="old",
        current_input_identity="new",
        changed_dependencies=[dependency],
        evidence=[evidence],
    )
    plan = resume_plan(tmp_path, input_identity="new")
    assert plan["start_phase"] == 4
    assert [row["action"] for row in plan["phases"][:4]] == [
        "REUSE",
        "REUSE",
        "REUSE",
        "RUN",
    ]
