from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .project import write_json
from .run_journal import phase_receipt_is_valid, valid_phase_repair_receipt


@dataclass(frozen=True)
class Phase:
    number: int
    name: str
    depends_on: tuple[int, ...]
    required_artifacts: tuple[str, ...]


PHASES = (
    Phase(
        1,
        "analysis",
        (),
        (
            "analysis.json",
            "manuscript-structure.json",
            "spoken-forms.json",
            "dialogue-speaker-map.json",
            "discourse-prosody-map.json",
            "speaker-energy-map.json",
            "tts-risk-map.json",
            "performance-units.json",
        ),
    ),
    Phase(2, "synthesis", (1,), ("candidates.json", "candidate-plan.json")),
    Phase(3, "candidate_realization", (2,), ("generation.json",)),
    Phase(
        4,
        "cue_qa",
        (3,),
        (
            "verification.json",
            "forced-alignment.json",
            "candidate-selection-integrity.json",
            "candidate-strategy-ledger.json",
            "quality-measurements.json",
        ),
    ),
    Phase(5, "pre_mix_gate", (4,), ("release-contract.json",)),
    Phase(6, "assembly", (5,), ("assembly-manifest.json",)),
    Phase(
        7,
        "post_mix_qa",
        (6,),
        ("full-file-fidelity.json", "review-manifest.json"),
    ),
    Phase(
        8,
        "package",
        (7,),
        ("encoded-deliverable-quality.json", "stage-manifest.json"),
    ),
)


def execution_start_phase(phase: int | None) -> int | None:
    """Map an evidence phase to the earliest phase of its atomic local action."""

    if phase is None or phase <= 1:
        return phase
    if phase <= 3:
        return 2
    if phase == 4:
        return 4
    return 5


def pipeline_contract() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": 1,
        "audiobook_harness_version": __version__,
        "phases": [asdict(phase) for phase in PHASES],
    }
    payload["identity_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def audit_pipeline(project: Path) -> dict[str, Any]:
    production = project / "production"
    phases = []
    contiguous = True
    for phase in PHASES:
        missing = [
            name
            for name in phase.required_artifacts
            if not (production / name).is_file()
        ]
        complete = contiguous and not missing
        contiguous = complete
        phases.append(
            {
                "number": phase.number,
                "name": phase.name,
                "complete": complete,
                "missing": missing,
            }
        )
    report = {
        **pipeline_contract(),
        "phase_status": phases,
        "resume_from_phase": next(
            (row["number"] for row in phases if not row["complete"]), None
        ),
        "ok": all(row["complete"] for row in phases),
    }
    write_json(production / "pipeline-audit.json", report)
    return report


def resume_plan(project: Path, *, input_identity: str) -> dict[str, Any]:
    """Plan one eight-phase resume using receipts and an optional repair scope."""

    repair = valid_phase_repair_receipt(project, current_input_identity=input_identity)
    owner = int(repair["owner_phase"]) if repair else None
    base_identity = str(repair["base_input_identity"]) if repair else input_identity
    rows = []
    blocked = False
    for phase in PHASES:
        identity = (
            base_identity
            if owner is not None and phase.number < owner
            else input_identity
        )
        reusable = (
            not blocked
            and (owner is None or phase.number < owner)
            and phase_receipt_is_valid(
                project, step=phase.number, input_identity=identity
            )
        )
        if not reusable:
            blocked = True
        rows.append(
            {
                "phase": phase.number,
                "name": phase.name,
                "action": "REUSE" if reusable else "RUN",
                "reason": (
                    "hash-bound phase receipt is current"
                    if reusable
                    else "phase-scoped repair owns this phase"
                    if owner == phase.number
                    else "first incomplete or dependent phase"
                ),
            }
        )
    start = next((row["phase"] for row in rows if row["action"] == "RUN"), None)
    effective_start = execution_start_phase(start)
    if effective_start is not None and effective_start != start:
        for row in rows:
            if effective_start <= int(row["phase"]) < int(start):
                row["action"] = "RUN"
                row["reason"] = "atomic production action also owns this phase"
    return {
        "version": 1,
        "input_identity": input_identity,
        "repair": repair,
        "phases": rows,
        "start_phase": effective_start,
    }
