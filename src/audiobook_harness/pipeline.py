from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .project import write_json


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
