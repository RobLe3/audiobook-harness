from audiobook_harness.cli import exit_code_for_error
from audiobook_harness.phase_engine import PhaseExecutionError, PhaseResult


def test_exit_code_categories_are_stable():
    assert exit_code_for_error(FileNotFoundError("tool")) == 3
    assert exit_code_for_error(ValueError("bad input")) == 2
    assert exit_code_for_error(RuntimeError("hash mismatch")) == 5
    assert exit_code_for_error(RuntimeError("review approval missing")) == 6


def test_phase_quality_failure_has_quality_exit_code():
    error = PhaseExecutionError(
        PhaseResult("repairable_failure", 4, detail="quality gate rejected")
    )
    assert exit_code_for_error(error) == 4
