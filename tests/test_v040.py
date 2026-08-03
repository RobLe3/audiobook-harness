import json
from pathlib import Path
from audiobook_harness.contracts import build_analysis_contracts
from audiobook_harness.migration import apply_upgrade, upgrade_plan
from audiobook_harness.review import finalize_review, review_is_approved, review_status


def test_contracts_preserve_structure_and_separate_spoken_forms(tmp_path: Path):
    chapter = {
        "id": "ch1",
        "source": "source/ch1.txt",
        "text": "Chapter One\n\nHello.\n\n***\n\nAt 12:30.",
        "units": [
            {
                "id": "ch1-0001",
                "text": "Hello.",
                "source_span": [13, 19],
                "chapter_index": 1,
                "unit_index": 1,
                "global_sequence": 1,
            }
        ],
    }
    reports = build_analysis_contracts(tmp_path, [chapter], "en-gb")
    assert reports["manuscript-structure.json"]["chapters"][0]["paragraphs"]
    assert reports["prosody-plan.json"]["defaults_ms"]["chapter_tail"] == 1500
    assert reports["discourse-prosody-map.json"]["units"]
    assert reports["speaker-energy-map.json"]["units"]
    assert reports["candidate-plan.json"]["units"]


def test_review_requires_exact_manifest_identity(tmp_path: Path):
    production = tmp_path / "production"
    production.mkdir()
    manifest = {
        "review_identity_sha256": "abc",
        "items": [{"id": "chapter:one", "mandatory": True}],
    }
    (production / "review-manifest.json").write_text(json.dumps(manifest))
    assert finalize_review(tmp_path, [{"id": "chapter:one", "decision": "approve"}])[
        "ok"
    ]
    assert review_is_approved(tmp_path)
    manifest["review_identity_sha256"] = "changed"
    (production / "review-manifest.json").write_text(json.dumps(manifest))
    assert not review_is_approved(tmp_path)


def test_review_status_disables_review_when_generation_failed(tmp_path: Path):
    production = tmp_path / "production"
    production.mkdir()
    (production / "review-manifest.json").write_text(
        json.dumps({"review_identity_sha256": "new"})
    )
    (production / "review-decisions.json").write_text(
        json.dumps({"ok": True, "review_identity_sha256": "old"})
    )
    (production / "run-status.json").write_text(
        json.dumps({"state": "failed", "phase": "cue_qa"})
    )
    status = review_status(tmp_path)
    assert status["reviewer_action"]["code"] == "diagnostic_unavailable"
    assert status["convergence"]["iterations"] == 0


def test_review_status_uses_structured_phase_failure(tmp_path: Path):
    production = tmp_path / "production"
    production.mkdir()
    (production / "run-status.json").write_text(
        json.dumps({"state": "failed", "phase": "synthesis"})
    )
    (production / "phase-events.jsonl").write_text(
        json.dumps(
            {
                "event": "phase_failed",
                "result": {
                    "status": "implementation_failure",
                    "owner_phase": 2,
                    "failure_code": "unhandled_tool_failure",
                },
            }
        )
        + "\n"
    )
    status = review_status(tmp_path)
    assert status["reviewer_action"]["code"] == "harness_correction_required"
    assert status["phase_result"]["owner_phase"] == 2
    assert status["state_authority"] == "append_only_phase_journal"
    assert not status["reviewer_action"]["enabled"]


def test_finalized_rejection_is_correction_work_not_an_unavailable_review(
    tmp_path: Path,
):
    production = tmp_path / "production"
    production.mkdir()
    manifest = {
        "review_identity_sha256": "current",
        "items": [{"id": "c1", "mandatory": True, "audio_sha256": "audio"}],
    }
    (production / "review-manifest.json").write_text(json.dumps(manifest))
    report = finalize_review(
        tmp_path,
        [
            {
                "id": "c1",
                "decision": "reject",
                "defect_category": "stretch_or_timing",
            }
        ],
    )
    assert report["feedback"]["ok"]
    status = review_status(tmp_path)
    assert status["reviewer_action"]["code"] == "corrections_queued"
    assert not status["reviewer_action"]["enabled"]
    assert status["listener_review_complete"]
    assert not status["correction_work_complete"]
    assert not status["publication_eligible"]
    assert status["review_items"] == [
        {
            "id": "c1",
            "decision_state": "feedback_received",
            "remediation_state": "pending",
            "review_required": False,
            "review_item_identity_sha256": None,
        }
    ]


def test_upgrade_is_inventory_bound(tmp_path: Path):
    (tmp_path / "production").mkdir()
    plan = upgrade_plan(tmp_path)
    assert apply_upgrade(tmp_path, plan["inventory_sha256"])["ok"]
