from audiobook_harness.candidate_scheduler import (
    build_candidate_strategy_ledger,
    candidate_budget_by_unit,
    untried_strategy_families,
)


def test_candidate_budget_is_loaded_from_analysis_contract():
    plan = {
        "units": [
            {"unit": "u1", "candidate_budget": 4},
            {"unit": "u2", "candidate_budget": 3},
        ]
    }
    assert candidate_budget_by_unit(plan) == {"u1": 4, "u2": 3}


def test_retry_ledger_counts_unique_retained_candidates():
    plan = {"units": [{"unit": "u1", "candidate_budget": 4}]}
    candidates = [
        {
            "id": "u1",
            "candidate": "baseline",
            "strategy_family": "native_micro_pace",
        },
        {
            "id": "u1",
            "candidate": "retry_faster",
            "strategy_family": "native_micro_pace",
        },
    ]
    ledger = build_candidate_strategy_ledger(plan, candidates, failures=["u1"])
    row = ledger["units"][0]
    assert row["generated_unique_candidates"] == 2
    assert row["exhausted"] is False
    assert row["verification"] == "rejected"


def test_full_budget_cannot_hide_untried_family():
    plan = {
        "units": [
            {
                "unit": "u1",
                "candidate_budget": 2,
                "applicable_strategy_families": [
                    "reviewed_pronunciation",
                    "native_micro_pace",
                ],
            }
        ]
    }
    candidates = [
        {
            "id": "u1",
            "candidate": "a",
            "strategy_family": "native_micro_pace",
        },
        {
            "id": "u1",
            "candidate": "b",
            "strategy_family": "native_micro_pace",
        },
    ]

    ledger = build_candidate_strategy_ledger(plan, candidates, failures=["u1"])

    assert ledger["units"][0]["budget_full"]
    assert not ledger["units"][0]["exhausted"]
    assert untried_strategy_families(ledger) == {"u1": ["reviewed_pronunciation"]}
