"""Bounded, evidence-led candidate strategy accounting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


MAXIMUM_CANDIDATES_PER_UNIT = 8


def applicable_strategy_families(row: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the distinct strategy families a unit has declared executable."""

    raw = row.get("applicable_strategy_families", ("native_micro_pace",))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raw = ("native_micro_pace",)
    return tuple(dict.fromkeys(str(value) for value in raw if str(value))) or (
        "native_micro_pace",
    )


def candidate_budget_by_unit(candidate_plan: Mapping[str, Any]) -> dict[str, int]:
    return {
        str(row.get("unit")): min(
            MAXIMUM_CANDIDATES_PER_UNIT,
            max(
                int(row.get("candidate_budget", 3)),
                len(applicable_strategy_families(row)),
            ),
        )
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
    plan_rows = {
        str(row.get("unit")): row
        for row in candidate_plan.get("units", [])
        if isinstance(row, Mapping) and row.get("unit")
    }
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
        declared = applicable_strategy_families(plan_rows[unit])
        infeasible = {
            str(row.get("family")): str(row.get("reason", "unspecified"))
            for row in plan_rows[unit].get("infeasible_strategy_families", [])
            if isinstance(row, Mapping) and row.get("family")
        }
        family_rows = []
        for family in declared:
            ids = families.get(family, [])
            status = (
                "attempted"
                if ids
                else "infeasible"
                if family in infeasible
                else "untried"
            )
            family_rows.append(
                {
                    "family": family,
                    "status": status,
                    "candidate_ids": ids,
                    **(
                        {"infeasible_reason": infeasible[family]}
                        if family in infeasible
                        else {}
                    ),
                }
            )
        # Retain unexpected legacy families as evidence, but do not let them
        # satisfy a declared family reservation.
        family_rows.extend(
            {
                "family": family,
                "status": "attempted_legacy",
                "candidate_ids": ids,
            }
            for family, ids in sorted(families.items())
            if family not in declared
        )
        untried = [row["family"] for row in family_rows if row["status"] == "untried"]
        budget_full = len(rows) >= budget
        exhausted = unit in failed and not untried and budget_full
        units.append(
            {
                "unit": unit,
                "maximum_unique_candidates": budget,
                "generated_unique_candidates": len(rows),
                "strategy_families": family_rows,
                "untried_eligible_families": untried,
                "verification": "rejected" if unit in failed else "pending_or_passed",
                "budget_full": budget_full,
                "exhausted": exhausted,
            }
        )
    return {
        "version": 2,
        "policy": (
            "One slot is reserved for every applicable strategy family before "
            "variants repeat. Budget fullness is not exhaustion while an eligible "
            "family remains untried; an unattempted family needs structured "
            "infeasibility evidence."
        ),
        "units": units,
    }


def untried_strategy_families(ledger: Mapping[str, Any]) -> dict[str, list[str]]:
    """Return failed units that must continue instead of entering review."""

    return {
        str(row.get("unit")): [
            str(value) for value in row.get("untried_eligible_families", [])
        ]
        for row in ledger.get("units", [])
        if isinstance(row, Mapping)
        and row.get("verification") == "rejected"
        and row.get("untried_eligible_families")
    }
