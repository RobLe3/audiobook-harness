from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from audiobook_harness.advisory_quality import collect_advisory_scores
from audiobook_harness.boundary_repair import (
    boundary_discontinuity,
    equal_power_crossfade,
)
from audiobook_harness.repair_analysis import (
    RepairOutcome,
    append_repair_outcome,
    automatic_execution_mode,
    build_repair_artifacts,
    strategy_priors,
)


def test_repair_diagnosis_routes_dual_asr_failure_to_pronunciation(tmp_path: Path):
    project = tmp_path / "book"
    (project / "production").mkdir(parents=True)
    verification = {
        "failures": ["u1"],
        "candidate_evidence": {
            "u1": [
                {
                    "text": "A protected name",
                    "primary_wer": 0.2,
                    "secondary_wer": 0.15,
                    "duration_seconds": 1.2,
                    "acoustic_failures": [],
                }
            ]
        },
    }

    diagnosis, plan = build_repair_artifacts(project, verification)

    assert diagnosis["diagnoses"][0]["categories"] == ("lexical_or_pronunciation",)
    assert plan["repairs"][0]["strategy"]["id"] == "reviewed_pronunciation_repair"
    assert not plan["automatic_acceptance_authority"]


def test_repair_diagnosis_routes_duration_failure_to_contextual_retry(tmp_path: Path):
    project = tmp_path / "book"
    (project / "production").mkdir(parents=True)
    verification = {
        "failures": ["u2"],
        "candidate_evidence": {
            "u2": [
                {
                    "text": "he paused",
                    "primary_wer": 0.0,
                    "secondary_wer": 0.0,
                    "duration_seconds": 3.0,
                    "acoustic_failures": ["long_word_duration_risk"],
                }
            ]
        },
    }

    _diagnosis, plan = build_repair_artifacts(project, verification)

    assert plan["repairs"][0]["strategy"]["id"] == "bounded_pace_resynthesis"
    assert automatic_execution_mode(plan) == "regenerate_failed_units"


def test_clean_verification_writes_explicit_noop_plan(tmp_path: Path):
    project = tmp_path / "book"
    (project / "production").mkdir(parents=True)

    diagnosis, plan = build_repair_artifacts(
        project, {"ok": True, "failures": [], "candidate_evidence": {}}
    )

    assert diagnosis["ok"] and plan["ok"]
    assert plan["repairs"] == []
    assert automatic_execution_mode(plan) == "none"


def test_repair_outcomes_are_deduplicated_and_rank_accepted_strategy(tmp_path: Path):
    project = tmp_path / "book"
    outcome = RepairOutcome(
        defect="stretch_or_timing",
        context="high_risk_unit",
        strategies_attempted=("bounded_pace_resynthesis",),
        accepted_strategy="bounded_pace_resynthesis",
        listener_result="accepted",
        objective_evidence_sha256="evidence",
    )

    path = append_repair_outcome(project, outcome)
    append_repair_outcome(project, outcome)

    assert len(path.read_text(encoding="utf-8").splitlines()) == 1
    assert strategy_priors(project, "stretch_or_timing") == ["bounded_pace_resynthesis"]


def test_advisory_scorers_are_explicitly_unavailable_and_non_authoritative(
    tmp_path: Path,
):
    project = tmp_path / "book"
    (project / "production/advisory").mkdir(parents=True)
    (project / "production/advisory/ctc_alignment.json").write_text(
        json.dumps({"units": [{"unit": "u1", "score": 0.9}]}), encoding="utf-8"
    )

    report = collect_advisory_scores(project)

    assert report["ok"]
    assert not report["automatic_acceptance_authority"]
    ctc = next(row for row in report["scorers"] if row["scorer"] == "ctc_alignment")
    assert ctc["available"]
    assert ctc["authority"] == "candidate_ranking_and_review_priority_only"


def test_boundary_helpers_measure_and_repair_only_declared_span():
    left = np.array([0.0, 0.25, 0.5], dtype=np.float32)
    right = np.array([-0.5, -0.25, 0.0], dtype=np.float32)

    measurement = boundary_discontinuity(left, right)
    joined = equal_power_crossfade(left, right, 2)

    assert measurement["sample_jump"] == 1.0
    assert len(joined) == 4
    assert joined[0] == left[0]
    assert joined[-1] == right[-1]
