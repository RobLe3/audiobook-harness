from pathlib import Path

from audiobook_harness.convergence import (
    append_iteration,
    convergence_summary,
    read_iterations,
)


def test_iteration_receipts_are_durable_and_summary_preserves_history(tmp_path: Path):
    project = tmp_path / "book"
    append_iteration(
        project,
        {
            "iteration": 1,
            "state": "automatic_work",
            "findings": 4,
            "objective_score": 0.6,
            "evidence_fingerprint": "a",
            "strategy": "bounded_pace_resynthesis",
            "stop_reason": None,
        },
    )
    append_iteration(
        project,
        {
            "iteration": 2,
            "state": "review_required",
            "findings": 1,
            "objective_score": 0.9,
            "evidence_fingerprint": "b",
            "strategy": "focused_review",
            "stop_reason": "safe_repair_strategy_requires_review",
        },
    )
    rows = read_iterations(project)
    assert len(rows) == 2
    assert all(row.get("iteration_identity_sha256") for row in rows)
    summary = convergence_summary(project)
    assert summary["iterations"] == 2
    assert summary["findings_trajectory"] == [4, 1]
    assert summary["objective_scores"] == [0.6, 0.9]
    assert summary["stop_reason"] == "safe_repair_strategy_requires_review"
    assert summary["plateau"] is False


def test_summary_detects_evidence_plateau(tmp_path: Path):
    project = tmp_path / "book"
    for iteration in (1, 2):
        append_iteration(
            project,
            {
                "iteration": iteration,
                "state": "blocked",
                "findings": 2,
                "objective_score": None,
                "evidence_fingerprint": "same",
                "strategy": "bounded_pace_resynthesis",
                "stop_reason": "identical_failure_already_terminal_for_same_inputs",
            },
        )
    assert convergence_summary(project)["plateau"] is True
