import json
from pathlib import Path
from audiobook_harness.contracts import build_analysis_contracts
from audiobook_harness.migration import apply_upgrade, upgrade_plan
from audiobook_harness.review import finalize_review, review_is_approved


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


def test_upgrade_is_inventory_bound(tmp_path: Path):
    (tmp_path / "production").mkdir()
    plan = upgrade_plan(tmp_path)
    assert apply_upgrade(tmp_path, plan["inventory_sha256"])["ok"]
