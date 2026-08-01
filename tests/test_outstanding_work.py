from audiobook_harness.outstanding_work import reconcile_outstanding_work


def test_missing_evidence_outranks_review() -> None:
    report = reconcile_outstanding_work(
        [
            {
                "episode": "chapter-8",
                "missing_evidence": ["alignment.json"],
                "cue_states": [{"unit": "u1", "state": "review_required"}],
                "owner_phase": 4,
            }
        ]
    )
    assert report["items"][0]["state"] == "verification_pending"
    assert report["automatic_work_remaining"] is True


def test_dependency_prevents_premature_resume() -> None:
    report = reconcile_outstanding_work(
        [
            {
                "episode": "chapter-9",
                "missing_evidence": ["master.json"],
                "unresolved_dependencies": ["chapter-8-name"],
            }
        ]
    )
    assert report["items"][0]["state"] == "waiting_dependency"
    assert report["automatic_work_remaining"] is False


def test_repairable_unit_is_machine_work() -> None:
    report = reconcile_outstanding_work(
        [
            {
                "episode": "chapter-1",
                "cue_states": [{"unit": "u1", "state": "repairable"}],
            }
        ]
    )
    assert report["items"][0]["action"] == "execute_bounded_repair"
