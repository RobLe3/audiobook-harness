import json
from pathlib import Path

from audiobook_harness.quality_policy import classify_quality_report


def test_quality_policy_pass_is_objective_only():
    result = classify_quality_report({"ok": True, "failures": []})
    assert result["disposition"] == "pass"
    assert result["objective_authority"] is True
    assert result["subjective_approval_required"] is False


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


def test_quality_policy_blocks_non_repairable_acoustic_defect():
    result = classify_quality_report(
        {"ok": False, "acoustic": {"ok": False, "repairable": False}}
    )
    assert result["disposition"] == "blocked"


def test_public_quality_fixture_corpus_matches_policy():
    path = Path(__file__).parent / "fixtures/quality-gates.json"
    corpus = json.loads(path.read_text(encoding="utf-8"))
    for case in corpus["cases"]:
        evidence = {"ok": case["expected"] == "pass", **case.get("evidence", {})}
        assert classify_quality_report(evidence)["disposition"] == case["expected"]
