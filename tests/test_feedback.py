import json
from pathlib import Path

import pytest

from audiobook_harness.contracts import build_analysis_contracts
from audiobook_harness.feedback import compile_feedback, promote_rule
from audiobook_harness.review import finalize_review


def _manifest(project: Path) -> None:
    production = project / "production"
    production.mkdir()
    (production / "review-manifest.json").write_text(
        json.dumps(
            {
                "review_identity_sha256": "review-1",
                "items": [
                    {
                        "id": "ch1-0001",
                        "kind": "high_risk_unit",
                        "mandatory": True,
                        "audio_sha256": "audio-1",
                    }
                ],
            }
        )
    )


def test_rejection_requires_category_and_other_requires_note(tmp_path: Path):
    _manifest(tmp_path)
    with pytest.raises(ValueError, match="defect_category"):
        finalize_review(tmp_path, [{"id": "ch1-0001", "decision": "reject"}])
    with pytest.raises(ValueError, match="requires a note"):
        finalize_review(
            tmp_path,
            [
                {
                    "id": "ch1-0001",
                    "decision": "reject",
                    "defect_category": "other",
                }
            ],
        )


def test_finalized_feedback_is_hash_bound_and_deduplicated(tmp_path: Path):
    _manifest(tmp_path)
    decision = {
        "id": "ch1-0001",
        "decision": "reject",
        "defect_category": "pronunciation",
        "note": "Name is wrong.",
    }
    finalize_review(tmp_path, [decision])
    finalize_review(tmp_path, [decision])
    lines = (
        (tmp_path / "production/listener-feedback-ledger.jsonl")
        .read_text()
        .splitlines()
    )
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["audio_sha256"] == "audio-1"
    assert row["review_identity_sha256"] == "review-1"
    assert compile_feedback(tmp_path)["ok"]


def test_listener_default_preflight_records_provenance(tmp_path: Path):
    (tmp_path / "listener-derived-defaults.json").write_text(
        json.dumps(
            {
                "version": 1,
                "revision": 2,
                "rules": [
                    {
                        "id": "term.arc",
                        "promotion_state": "promoted",
                        "defect_category": "pronunciation",
                        "matcher": {"kind": "exact_term", "value": "ARC"},
                        "action": "say_ark",
                        "provenance": ["review-1"],
                    }
                ],
            }
        )
    )
    chapter = {
        "id": "ch1",
        "source": "source/ch1.txt",
        "text": "ARC arrived.",
        "units": [
            {
                "id": "ch1-0001",
                "text": "ARC arrived.",
                "source_span": [0, 12],
                "chapter_index": 1,
                "unit_index": 1,
                "global_sequence": 1,
            }
        ],
    }
    reports = build_analysis_contracts(tmp_path, [chapter], "en-gb")
    preflight = reports["listener-defaults-preflight.json"]
    assert preflight["defaults_revision"] == 2
    assert preflight["matches"][0]["rules"][0]["rule_id"] == "term.arc"


def test_promotion_requires_scope_verification_approval_and_regression(tmp_path: Path):
    rule = {
        "id": "pause.colon",
        "promotion_state": "candidate",
        "defect_category": "pause",
        "matcher": {"kind": "regex", "value": "Cause:"},
        "action": "semantic_pause",
        "evidence": {
            "distinct_occurrences": 3,
            "distinct_episodes": 1,
            "objective_verification_ok": True,
            "listener_follow_up_approved": True,
            "regression_ok": True,
        },
    }
    (tmp_path / "listener-derived-defaults.json").write_text(
        json.dumps({"version": 1, "revision": 0, "rules": [rule]})
    )
    promoted = promote_rule(tmp_path, "pause.colon")
    assert promoted["revision"] == 1
    assert promoted["rules"][0]["promotion_state"] == "promoted"
    promoted["rules"][0]["id"] = "pause.bad"
    promoted["rules"][0]["promotion_state"] = "candidate"
    promoted["rules"][0]["evidence"]["regression_ok"] = False
    (tmp_path / "listener-derived-defaults.json").write_text(json.dumps(promoted))
    with pytest.raises(ValueError, match="promotion policy"):
        promote_rule(tmp_path, "pause.bad")
