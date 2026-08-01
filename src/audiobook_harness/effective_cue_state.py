"""Single post-verification authority for cue-local evidence and next actions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .candidate_scheduler import untried_strategy_families
from .project import write_json


def _identity(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _failed_units(report: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("failures", "unresolved_cues", "unreviewed_findings"):
        rows = report.get(key, [])
        if isinstance(rows, int):
            continue
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            continue
        for row in rows:
            if isinstance(row, Mapping):
                unit = row.get("unit", row.get("cue"))
                if unit:
                    values.add(str(unit))
            elif row:
                values.add(str(row))
    return values


def build_effective_cue_state(
    project: Path,
    verification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile every cue-local gate before selection is treated as final."""

    production = project / "production"
    verification = dict(verification or _load(production / "verification.json"))
    ledger = _load(production / "candidate-strategy-ledger.json")
    gate_names = (
        "verification.json",
        "pronunciation-audit.json",
        "phoneme-duration-audit.json",
        "pause-economy-lint.json",
        "energy-lint.json",
        "expressive-realization.json",
    )
    reports = {name: _load(production / name) for name in gate_names}
    failures_by_gate = {name: _failed_units(report) for name, report in reports.items()}
    untried = untried_strategy_families(ledger)
    selected = {
        str(row.get("id")): row
        for row in verification.get("takes", [])
        if isinstance(row, Mapping) and row.get("id")
    }
    units = sorted(
        {
            *selected,
            *(str(value) for value in verification.get("failures", [])),
            *(
                str(row.get("unit"))
                for row in ledger.get("units", [])
                if isinstance(row, Mapping)
            ),
            *(unit for values in failures_by_gate.values() for unit in values),
        }
        - {"None", ""}
    )
    rows: list[dict[str, Any]] = []
    for unit in units:
        failed_gates = sorted(
            name for name, values in failures_by_gate.items() if unit in values
        )
        candidate = selected.get(unit)
        if unit in untried:
            state = "repairable"
            next_action = "attempt_untried_strategy_family"
            owner_phase = 2
        elif failed_gates:
            state = "repairable"
            next_action = "build_defect_specific_repair"
            owner_phase = 2
        elif candidate:
            state = "passed"
            next_action = "continue_downstream"
            owner_phase = 4
        else:
            state = "review_required"
            next_action = "build_focused_review"
            owner_phase = 4
        row = {
            "unit": unit,
            "state": state,
            "owner_phase": owner_phase,
            "next_action": next_action,
            "failed_gates": failed_gates,
            "untried_strategy_families": untried.get(unit, []),
            "selected_waveform": (
                {
                    "file": candidate.get("file"),
                    "sha256": candidate.get("sha256"),
                    "candidate": candidate.get("candidate"),
                    "provisional": state != "passed",
                }
                if candidate
                else None
            ),
        }
        row["evidence_identity_sha256"] = _identity(row)
        rows.append(row)
    report = {
        "version": 1,
        "audiobook_harness_version": __version__,
        "authority": "single_post_verification_cue_state",
        "units": rows,
        "ok": all(row["state"] == "passed" for row in rows),
    }
    report["identity_sha256"] = _identity(report)
    write_json(production / "effective-cue-state.json", report)
    return report
