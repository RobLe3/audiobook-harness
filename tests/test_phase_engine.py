import errno
import json
from pathlib import Path

import pytest

import audiobook_harness.phase_engine as phase_engine
from audiobook_harness.phase_engine import (
    PhaseExecutionError,
    classify_failure,
    execute_phase,
)
from audiobook_harness.pipeline import (
    PHASES,
    Phase,
    PhaseIdentityError,
    phase_input_identity,
    validate_phase_implementation_dependencies,
)
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
    write_phase_receipt(tmp_path, step=2, input_identity="old", artifacts=[artifact])
    write_phase_receipt(tmp_path, step=3, input_identity="old", artifacts=[artifact])
    phase = Phase(2, "test", (1,), ("owned.json",))

    def crash() -> None:
        artifact.write_text('{"version":"partial"}')
        raise RuntimeError("crash")

    with pytest.raises(PhaseExecutionError):
        execute_phase(tmp_path, phase=phase, input_identity="new", action=crash)
    assert json.loads(artifact.read_text())["version"] == "approved"
    assert not (production / "phase-receipts/step-2.json").exists()
    assert not (production / "phase-receipts/step-3.json").exists()


def test_receipt_write_failure_rolls_back_owned_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    production = tmp_path / "production"
    production.mkdir()
    artifact = production / "owned.json"
    artifact.write_text('{"version":"approved"}')
    phase = Phase(2, "test", (1,), ("owned.json",))

    def fail_receipt(*args: object, **kwargs: object) -> None:
        raise OSError("simulated receipt write interruption")

    monkeypatch.setattr(phase_engine, "write_phase_receipt", fail_receipt)
    with pytest.raises(PhaseExecutionError) as raised:
        execute_phase(
            tmp_path,
            phase=phase,
            input_identity="new",
            action=lambda: artifact.write_text('{"version":"partial"}'),
        )
    assert raised.value.result.status == "implementation_failure"
    assert json.loads(artifact.read_text()) == {"version": "approved"}
    assert not (production / "phase-receipts/step-2.json").exists()


def test_status_write_failure_cannot_leave_a_success_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Receipt-last ordering prevents a half-committed success claim."""
    production = tmp_path / "production"
    production.mkdir()
    artifact = production / "owned.json"
    artifact.write_text('{"version":"approved"}')
    phase = Phase(2, "test", (1,), ("owned.json",))
    original_write_json = phase_engine.write_json

    def fail_only_success_status(path: Path, value: object) -> None:
        if (
            path.name == "phase-result.json"
            and getattr(value, "get", lambda *_: None)("status") == "passed"
        ):
            raise OSError("simulated status interruption")
        original_write_json(path, value)

    monkeypatch.setattr(phase_engine, "write_json", fail_only_success_status)
    with pytest.raises(PhaseExecutionError) as raised:
        execute_phase(
            tmp_path,
            phase=phase,
            input_identity="new",
            action=lambda: artifact.write_text('{"version":"partial"}'),
        )
    assert raised.value.result.status == "implementation_failure"
    assert json.loads(artifact.read_text()) == {"version": "approved"}
    assert not (production / "phase-receipts/step-2.json").exists()
    assert json.loads((production / "phase-result.json").read_text())["status"] == (
        "implementation_failure"
    )


def test_event_write_failure_cannot_leave_a_success_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    production = tmp_path / "production"
    production.mkdir()
    artifact = production / "owned.json"
    artifact.write_text('{"version":"approved"}')
    phase = Phase(2, "test", (1,), ("owned.json",))

    def fail_event(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "simulated journal disk full")

    monkeypatch.setattr(phase_engine, "append_event", fail_event)
    with pytest.raises(PhaseExecutionError) as raised:
        execute_phase(
            tmp_path,
            phase=phase,
            input_identity="new",
            action=lambda: artifact.write_text('{"version":"partial"}'),
        )
    assert raised.value.result.status == "implementation_failure"
    assert json.loads(artifact.read_text()) == {"version": "approved"}
    assert not (production / "phase-receipts/step-2.json").exists()


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


def test_missing_declared_implementation_dependency_fails_closed(
    tmp_path: Path,
) -> None:
    phase = Phase(1, "analysis", (), (), (), ("missing.py",))
    with pytest.raises(PhaseIdentityError, match="does not exist"):
        validate_phase_implementation_dependencies(tmp_path, phases=(phase,))


def test_duplicate_and_escape_dependencies_fail_closed(tmp_path: Path) -> None:
    package = tmp_path / "src/audiobook_harness"
    package.mkdir(parents=True)
    (package / "analysis.py").write_text("x")
    duplicate = Phase(1, "analysis", (), (), (), ("analysis.py", "analysis.py"))
    with pytest.raises(PhaseIdentityError, match="duplicate"):
        validate_phase_implementation_dependencies(tmp_path, phases=(duplicate,))
    escape = Phase(1, "analysis", (), (), (), ("../outside.py",))
    with pytest.raises(PhaseIdentityError, match="escapes"):
        validate_phase_implementation_dependencies(tmp_path, phases=(escape,))


def test_missing_selector_fails_closed(tmp_path: Path) -> None:
    package = tmp_path / "src/audiobook_harness"
    package.mkdir(parents=True)
    (package / "analysis.py").write_text("def present():\n    return None\n")
    phase = Phase(1, "analysis", (), (), (), ("analysis.py#missing",))
    with pytest.raises(PhaseIdentityError, match="selector is missing"):
        validate_phase_implementation_dependencies(tmp_path, phases=(phase,))


def test_absolute_and_symlink_dependencies_fail_closed(tmp_path: Path) -> None:
    package = tmp_path / "src/audiobook_harness"
    package.mkdir(parents=True)
    target = tmp_path / "implementation.py"
    target.write_text("implementation")
    absolute = Phase(1, "analysis", (), (), (), (str(target),))
    with pytest.raises(PhaseIdentityError, match="safe package-relative"):
        validate_phase_implementation_dependencies(tmp_path, phases=(absolute,))
    (package / "link.py").symlink_to(target)
    symlink = Phase(1, "analysis", (), (), (), ("link.py",))
    with pytest.raises(PhaseIdentityError, match="must not be a symlink"):
        validate_phase_implementation_dependencies(tmp_path, phases=(symlink,))


def test_dependency_order_does_not_change_identity(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    project = tmp_path / "project"
    package = repo / "src/audiobook_harness"
    source = project / "source"
    package.mkdir(parents=True)
    source.mkdir(parents=True)
    (project / "project.yaml").write_text("title: Test")
    (source / "chapter.txt").write_text("Text.")
    (package / "a.py").write_text("a")
    (package / "b.py").write_text("b")
    first = Phase(1, "analysis", (), (), (), ("a.py", "b.py"))
    second = Phase(1, "analysis", (), (), (), ("b.py", "a.py"))
    assert phase_input_identity(project, repo, first) == phase_input_identity(
        project, repo, second
    )


def test_phase_identity_uses_logical_paths_not_checkout_location(
    tmp_path: Path,
) -> None:
    phase = Phase(1, "analysis", (), (), (), ("analysis.py",))
    identities = []
    for name in ("checkout-a", "checkout-b"):
        root = tmp_path / name
        repo = root / "repo"
        project = root / "project"
        (repo / "src/audiobook_harness").mkdir(parents=True)
        (project / "source").mkdir(parents=True)
        (project / "project.yaml").write_text("title: Test")
        (project / "source/chapter.txt").write_text("Text.")
        (repo / "src/audiobook_harness/analysis.py").write_text("analysis")
        identities.append(phase_input_identity(project, repo, phase))
    assert identities[0] == identities[1]


def test_artifact_contract_rejects_duplicates_and_traversal(tmp_path: Path) -> None:
    package = tmp_path / "src/audiobook_harness"
    package.mkdir(parents=True)
    (package / "analysis.py").write_text("analysis")
    duplicate = Phase(
        1, "analysis", (), ("analysis.json", "analysis.json"), (), ("analysis.py",)
    )
    with pytest.raises(PhaseIdentityError, match="artifact"):
        validate_phase_implementation_dependencies(tmp_path, phases=(duplicate,))
    traversal = Phase(1, "analysis", (), ("../analysis.json",), (), ("analysis.py",))
    with pytest.raises(PhaseIdentityError, match="artifact"):
        validate_phase_implementation_dependencies(tmp_path, phases=(traversal,))


def test_repository_phase_dependency_graph_is_complete() -> None:
    validate_phase_implementation_dependencies(Path(__file__).parents[1], phases=PHASES)
