import json
from pathlib import Path

import pytest

from audiobook_harness.phase_engine import (
    PhaseExecutionError,
    classify_failure,
    execute_phase,
)
from audiobook_harness.pipeline import Phase, phase_input_identity
from audiobook_harness.run_journal import phase_receipt_is_valid, write_phase_receipt


def test_phase_commits_receipt_only_after_semantic_success(tmp_path: Path) -> None:
    phase = Phase(1, "test", (), ("gate.json",), (("gate.json", "ok"),))
    production = tmp_path / "production"
    production.mkdir()

    execute_phase(
        tmp_path,
        phase=phase,
        input_identity="input",
        action=lambda: (production / "gate.json").write_text('{"ok":true}'),
    )
    assert phase_receipt_is_valid(tmp_path, step=1, input_identity="input")


def test_failed_gate_keeps_evidence_but_has_no_success_receipt(tmp_path: Path) -> None:
    phase = Phase(1, "test", (), ("gate.json",), (("gate.json", "ok"),))
    production = tmp_path / "production"
    production.mkdir()
    with pytest.raises(PhaseExecutionError) as raised:
        execute_phase(
            tmp_path,
            phase=phase,
            input_identity="input",
            action=lambda: (production / "gate.json").write_text('{"ok":false}'),
        )
    assert raised.value.result.status == "repairable_failure"
    assert json.loads((production / "gate.json").read_text())["ok"] is False
    assert not phase_receipt_is_valid(tmp_path, step=1, input_identity="input")


def test_implementation_crash_restores_predecessor_and_invalidates_downstream(
    tmp_path: Path,
) -> None:
    production = tmp_path / "production"
    production.mkdir()
    artifact = production / "owned.json"
    artifact.write_text('{"version":"approved"}')
    write_phase_receipt(
        tmp_path, step=2, input_identity="old", artifacts=[artifact]
    )
    write_phase_receipt(
        tmp_path, step=3, input_identity="old", artifacts=[artifact]
    )
    phase = Phase(2, "test", (1,), ("owned.json",))

    def crash() -> None:
        artifact.write_text('{"version":"partial"}')
        raise RuntimeError("crash")

    with pytest.raises(PhaseExecutionError):
        execute_phase(tmp_path, phase=phase, input_identity="new", action=crash)
    assert json.loads(artifact.read_text())["version"] == "approved"
    assert not (production / "phase-receipts/step-2.json").exists()
    assert not (production / "phase-receipts/step-3.json").exists()


def test_failure_classification_is_typed() -> None:
    phase = Phase(2, "synthesis", (1,), ("candidates.json",))
    transient = classify_failure(phase, TimeoutError("slow tool"))
    pronunciation = classify_failure(
        phase, ValueError("Reviewed pronunciation context preflight failed")
    )
    assert transient.status == "transient_failure" and transient.retryable
    assert pronunciation.failure_code == "pronunciation_span_unresolved"


def test_phase_identity_changes_only_for_declared_implementation_dependency(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    project = tmp_path / "project"
    package = repo / "src/audiobook_harness"
    source = project / "source"
    package.mkdir(parents=True)
    source.mkdir(parents=True)
    (project / "project.yaml").write_text("title: Test")
    (source / "chapter.txt").write_text("Text.")
    (package / "analysis.py").write_text("analysis-v1")
    (package / "pronunciation.py").write_text("pronunciation-v1")
    analysis = Phase(1, "analysis", (), ("analysis.json",), (), ("analysis.py",))
    synthesis = Phase(
        2, "synthesis", (1,), ("candidates.json",), (), ("pronunciation.py",)
    )
    first_analysis = phase_input_identity(project, repo, analysis)
    first_synthesis = phase_input_identity(project, repo, synthesis)
    (package / "pronunciation.py").write_text("pronunciation-v2")
    assert phase_input_identity(project, repo, analysis) == first_analysis
    assert phase_input_identity(project, repo, synthesis) != first_synthesis
