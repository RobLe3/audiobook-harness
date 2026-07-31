from pathlib import Path

from audiobook_harness.resilience import (
    GateDisposition,
    GateResult,
    repair_ticket,
    validate_phase_commit,
)
from audiobook_harness.review import carry_forward_findings


def test_success_cannot_commit_without_owned_outputs(tmp_path: Path) -> None:
    result = GateResult(
        gate="candidate_reassembly",
        disposition=GateDisposition.PASS,
        owner_phase=3,
        evidence_fingerprint="evidence",
        attempt_id="attempt-1",
        input_identity="inputs",
    )
    committed = validate_phase_commit(
        result=result,
        owned_artifacts=(tmp_path / "effective-delivery.json",),
        attempt_id="attempt-1",
    )
    assert committed.disposition == GateDisposition.PHASE_CONTRACT_FAILURE
    assert committed.owner_phase == 3


def test_repair_ticket_is_stable_and_input_bound() -> None:
    result = GateResult(
        gate="candidate_quality",
        disposition=GateDisposition.REPAIR_ARTIFACT,
        owner_phase=2,
        evidence_fingerprint="evidence",
        affected_units=("c0040b",),
        remaining_attempts=1,
        input_identity="inputs",
    )
    first = repair_ticket(
        result, action="contextual_rechunk", expected_input_delta="chunk-plan"
    )
    second = repair_ticket(
        result, action="contextual_rechunk", expected_input_delta="chunk-plan"
    )
    assert first == second
    assert first.input_identity == "inputs"


def test_rejected_finding_survives_waveform_change_but_not_approval() -> None:
    old_manifest = {
        "items": [
            {
                "id": "c1",
                "kind": "high_risk_unit",
                "published_text": "He paused.",
                "spoken_text": "He paused.",
                "audio_sha256": "old",
            }
        ]
    }
    new_manifest = {
        "items": [
            {
                "id": "c1",
                "kind": "high_risk_unit",
                "published_text": "He paused.",
                "spoken_text": "He paused.",
                "audio_sha256": "new",
            }
        ]
    }
    decisions = {
        "decisions": [
            {
                "id": "c1",
                "decision": "reject",
                "defect_category": "stretch_or_timing",
                "comment": "verb is stretched",
            }
        ]
    }
    findings = carry_forward_findings(old_manifest, decisions, new_manifest)
    assert [row["id"] for row in findings] == ["c1"]
    assert findings[0]["requires_new_waveform_review"] is True
