"""Bounded, evidence-led candidate strategy accounting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def candidate_budget_by_unit(candidate_plan: Mapping[str, Any]) -> dict[str, int]:
    return {
        str(row.get("unit")): int(row.get("candidate_budget", 3))
        for row in candidate_plan.get("units", [])
        if isinstance(row, Mapping) and row.get("unit")
    }


def build_candidate_strategy_ledger(
    candidate_plan: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    *,
    failures: Sequence[str] = (),
) -> dict[str, Any]:
    budgets = candidate_budget_by_unit(candidate_plan)
    failed = {str(value) for value in failures}
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in candidates:
        grouped.setdefault(str(row.get("id", "")), []).append(row)
    units = []
    for unit, budget in sorted(budgets.items()):
        rows = grouped.get(unit, [])
        families: dict[str, list[str]] = {}
        for row in rows:
            families.setdefault(
                str(row.get("strategy_family", "native_micro_pace")), []
            ).append(str(row.get("candidate", "")))
        units.append(
            {
                "unit": unit,
                "maximum_unique_candidates": budget,
                "generated_unique_candidates": len(rows),
                "strategy_families": [
                    {"family": family, "candidate_ids": ids}
                    for family, ids in sorted(families.items())
                ],
                "verification": "rejected" if unit in failed else "pending_or_passed",
                "exhausted": len(rows) >= budget,
            }
        )
    return {
        "version": 1,
        "policy": (
            "Only unique, eligible waveform candidates consume budget. A retry "
            "adds untried strategies to existing hash-valid candidates."
        ),
        "units": units,
    }
