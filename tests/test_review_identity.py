from audiobook_harness.review import carry_forward_decisions, review_item_identity


def test_review_decision_carries_only_across_identical_item_evidence():
    item = {"id": "u1", "kind": "high_risk_unit", "audio_sha256": "a"}
    item["review_item_identity_sha256"] = review_item_identity(item)
    old = {"items": [item]}
    decisions = {"decisions": [{"id": "u1", "decision": "approve"}]}
    assert len(carry_forward_decisions(old, decisions, {"items": [dict(item)]})) == 1
    changed = {**item, "audio_sha256": "b"}
    changed["review_item_identity_sha256"] = review_item_identity(changed)
    assert carry_forward_decisions(old, decisions, {"items": [changed]}) == []
