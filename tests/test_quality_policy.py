import json
from pathlib import Path

import numpy as np

from audiobook_harness.quality_policy import (
    ACOUSTIC_THRESHOLDS,
    classify_quality_report,
    policy_identity,
)


def test_quality_policy_pass_is_objective_only():
    result = classify_quality_report({"ok": True, "failures": []})
    assert result["disposition"] == "pass"
    assert result["objective_authority"] is True
    assert result["subjective_approval_required"] is False
    assert result["policy_identity_sha256"] == policy_identity()


def test_quality_policy_identity_is_stable_for_equivalent_reports():
    assert (
        classify_quality_report({"ok": False, "failures": ["u1"]})[
            "policy_identity_sha256"
        ]
        == policy_identity()
    )


def test_acoustic_thresholds_are_bound_into_the_policy_contract():
    assert ACOUSTIC_THRESHOLDS["clipping_peak"] == 0.995
    assert ACOUSTIC_THRESHOLDS["maximum_internal_silence_seconds"] == 2.0


def test_quality_policy_routes_failed_units_to_bounded_repair():
    result = classify_quality_report(
        {"ok": False, "failures": ["chapter-01-u001"], "lexicon": {"ok": True}}
    )
    assert result["disposition"] == "automatic_repair"
    assert result["objective_authority"] is False


def test_quality_policy_routes_pronunciation_review_to_human():
    result = classify_quality_report(
        {"ok": False, "failures": [], "lexicon": {"ok": False}}
    )
    assert result["disposition"] == "review_required"
    assert result["subjective_approval_required"] is True


def test_quality_policy_blocks_missing_alignment():
    result = classify_quality_report(
        {
            "ok": False,
            "failures": [],
            "lexicon": {"ok": True},
            "forced_alignment": {"ok": False},
        }
    )
    assert result["disposition"] == "blocked"


def test_quality_policy_blocks_invalid_encoded_deliverable():
    result = classify_quality_report({"ok": False, "encoding": {"ok": False}})
    assert result["disposition"] == "blocked"


def test_explicit_failed_evidence_overrides_an_inconsistent_pass_flag():
    result = classify_quality_report({"ok": True, "encoding": {"ok": False}})
    assert result["disposition"] == "blocked"


def test_quality_policy_blocks_non_repairable_acoustic_defect():
    result = classify_quality_report(
        {"ok": False, "acoustic": {"ok": False, "repairable": False}}
    )
    assert result["disposition"] == "blocked"


def test_public_quality_fixture_corpus_matches_policy():
    path = Path(__file__).parent / "fixtures/quality-gates.json"
    corpus = json.loads(path.read_text(encoding="utf-8"))
    for case in corpus["cases"]:
        assert case["category"]
        evidence = {"ok": case["expected"] == "pass", **case.get("evidence", {})}
        assert classify_quality_report(evidence)["disposition"] == case["expected"]


def _signal_from_corpus_case(case: dict[str, object]) -> np.ndarray:
    signal = case["signal"]
    assert isinstance(signal, dict)
    rate = int(case["sample_rate"])
    samples = int(rate * float(signal["duration_seconds"]))
    kind = signal["kind"]
    amplitude = float(signal.get("amplitude", 0.0))
    if kind == "constant":
        return np.full(samples, amplitude, dtype=np.float32)
    if kind == "spike":
        value = np.full(samples, amplitude, dtype=np.float32)
        value[0] = float(signal["spike_amplitude"])
        return value
    if kind == "silence":
        return np.zeros(samples, dtype=np.float32)
    if kind == "noise":
        return (
            np.random.default_rng(int(signal["seed"]))
            .uniform(-amplitude, amplitude, samples)
            .astype(np.float32)
        )
    raise AssertionError(f"unknown corpus signal kind: {kind}")


def test_public_signal_corpus_is_deterministic_and_exercises_acoustic_policy():
    from audiobook_harness.quality import _acoustic_checks

    path = Path(__file__).parent / "fixtures/quality-gates.json"
    corpus = json.loads(path.read_text(encoding="utf-8"))
    for case in corpus["signal_cases"]:
        first = _signal_from_corpus_case(case)
        second = _signal_from_corpus_case(case)
        assert np.array_equal(first, second)
        assert (
            _acoustic_checks(first, int(case["sample_rate"]), int(case["words"]))
            == (case["expected_acoustic_failures"])
        )
