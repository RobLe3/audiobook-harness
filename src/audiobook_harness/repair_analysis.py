"""Evidence-fused diagnosis and conservative post-generation repair routing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from . import __version__
from .project import write_json


@dataclass(frozen=True)
class RepairDiagnosis:
    unit: str
    categories: tuple[str, ...]
    owner_phase: int
    confidence: float
    signals: tuple[dict[str, Any], ...]
    recommended_strategy: str
    escalation: str


@dataclass(frozen=True)
class RepairStrategy:
    id: str
    owner_phase: int
    changes_speech: bool
    required_evidence: tuple[str, ...]
    maximum_attempts: int
    fallback: str


@dataclass(frozen=True)
class RepairOutcome:
    defect: str
    context: str
    strategies_attempted: tuple[str, ...]
    accepted_strategy: str | None
    listener_result: str
    objective_evidence_sha256: str


STRATEGIES = {
    row.id: row
    for row in (
        RepairStrategy(
            "reverify_cached_evidence",
            4,
            False,
            ("audio_hash",),
            1,
            "retain_predecessor",
        ),
        RepairStrategy(
            "retain_predecessor", 4, False, ("predecessor_hash",), 1, "focused_review"
        ),
        RepairStrategy(
            "assembly_boundary_repair",
            6,
            False,
            ("join_measurements",),
            1,
            "contextual_resynthesis",
        ),
        RepairStrategy(
            "bounded_pace_resynthesis",
            2,
            True,
            ("candidate_evidence", "untried_speed_variant"),
            1,
            "contextual_resynthesis",
        ),
        RepairStrategy(
            "performance_plan_variant",
            2,
            True,
            ("prosody_plan",),
            2,
            "contextual_resynthesis",
        ),
        RepairStrategy(
            "reviewed_pronunciation_repair",
            2,
            True,
            ("reviewed_lexicon",),
            1,
            "contextual_resynthesis",
        ),
        RepairStrategy(
            "contextual_resynthesis", 2, True, ("context_span",), 2, "semantic_rechunk"
        ),
        RepairStrategy(
            "semantic_rechunk",
            1,
            True,
            ("safe_phrase_boundaries",),
            1,
            "focused_review",
        ),
        RepairStrategy("focused_review", 4, False, ("review_pack",), 0, "blocked"),
    )
}


def _canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _robust_pace_baseline(evidence: dict[str, list[dict[str, Any]]]) -> float | None:
    values = [
        float(row["duration_seconds"]) / max(1, len(str(row.get("text", "")).split()))
        for rows in evidence.values()
        for row in rows
        if row.get("ok") and row.get("duration_seconds") is not None
    ]
    return median(values) if values else None


def _diagnose_unit(
    unit: str,
    attempts: list[dict[str, Any]],
    *,
    pace_baseline: float | None,
) -> RepairDiagnosis:
    categories: list[str] = []
    signals: list[dict[str, Any]] = []
    if not attempts:
        categories.append("missing_candidate_evidence")
        return RepairDiagnosis(
            unit, tuple(categories), 4, 1.0, (), "reverify_cached_evidence", "blocked"
        )
    primary = min((float(row.get("primary_wer", 1.0)) for row in attempts), default=1.0)
    secondary = min(
        (float(row.get("secondary_wer", 1.0)) for row in attempts), default=1.0
    )
    if primary > 0.01 or secondary > 0.01:
        categories.append("lexical_or_pronunciation")
        signals.append(
            {"kind": "dual_asr", "primary_wer": primary, "secondary_wer": secondary}
        )
    acoustic = sorted(
        {str(value) for row in attempts for value in row.get("acoustic_failures", [])}
    )
    if "unexpected_silence" in acoustic:
        categories.append("pause_realization")
    if {"abnormal_duration", "long_word_duration_risk"} & set(acoustic):
        categories.append("elongation_or_pace")
    if acoustic:
        signals.append({"kind": "acoustic", "failures": acoustic})
    pace_values = [
        float(row["duration_seconds"]) / max(1, len(str(row.get("text", "")).split()))
        for row in attempts
        if row.get("duration_seconds") is not None
    ]
    if pace_baseline is not None and pace_values:
        best = min(pace_values, key=lambda value: abs(value - pace_baseline))
        ratio = best / max(0.001, pace_baseline)
        signals.append(
            {
                "kind": "relative_pace",
                "seconds_per_word": best,
                "baseline": pace_baseline,
                "ratio": ratio,
            }
        )
        if ratio > 1.65 and "elongation_or_pace" not in categories:
            categories.append("elongation_or_pace")
    if not categories:
        categories.append("candidate_quality_ambiguous")
    if "lexical_or_pronunciation" in categories:
        strategy = "reviewed_pronunciation_repair"
    elif "pause_realization" in categories and "elongation_or_pace" not in categories:
        strategy = "performance_plan_variant"
    elif "elongation_or_pace" in categories:
        strategy = "bounded_pace_resynthesis"
    else:
        strategy = "contextual_resynthesis"
    confidence = min(1.0, 0.45 + 0.2 * len(categories) + 0.05 * len(signals))
    return RepairDiagnosis(
        unit,
        tuple(categories),
        STRATEGIES[strategy].owner_phase,
        round(confidence, 3),
        tuple(signals),
        strategy,
        STRATEGIES[strategy].fallback,
    )


def build_repair_artifacts(
    project: Path, verification: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write complete diagnosis and strategy plans, including a clean no-op case."""

    production = project / "production"
    evidence = {
        str(key): list(value) if isinstance(value, list) else []
        for key, value in verification.get("candidate_evidence", {}).items()
    }
    baseline = _robust_pace_baseline(evidence)
    diagnoses = [
        _diagnose_unit(str(unit), evidence.get(str(unit), []), pace_baseline=baseline)
        for unit in verification.get("failures", [])
    ]
    diagnosis = {
        "version": 1,
        "audiobook_harness_version": __version__,
        "scope": "post_generation_candidate_evidence",
        "pace_baseline_seconds_per_word": baseline,
        "diagnoses": [asdict(row) for row in diagnoses],
        "ok": not diagnoses,
    }
    diagnosis["identity_sha256"] = _canonical(diagnosis)
    plan_rows = []
    for row in diagnoses:
        strategy = STRATEGIES[row.recommended_strategy]
        chain = []
        seen: set[str] = set()
        current = strategy
        while current.id not in seen:
            seen.add(current.id)
            chain.append(current.id)
            if current.fallback not in STRATEGIES:
                break
            current = STRATEGIES[current.fallback]
        plan_rows.append(
            {
                "unit": row.unit,
                "diagnosis_categories": list(row.categories),
                "strategy": asdict(strategy),
                "strategy_ladder": chain,
                "diagnosis_identity_sha256": diagnosis["identity_sha256"],
                "success_contract": {
                    "requires_distinct_input_identity": strategy.changes_speech,
                    "rerun_from_phase": strategy.owner_phase,
                    "must_pass": [
                        "dual_asr",
                        "acoustic_checks",
                        "candidate_selection_integrity",
                        "forced_alignment",
                    ],
                    "automatic_acceptance_authority": False,
                },
                "status": "queued",
            }
        )
    plan = {
        "version": 1,
        "audiobook_harness_version": __version__,
        "repairs": plan_rows,
        "automatic_acceptance_authority": False,
        "ok": not plan_rows,
    }
    plan["identity_sha256"] = _canonical(plan)
    write_json(production / "repair-diagnosis.json", diagnosis)
    write_json(production / "repair-plan.json", plan)
    return diagnosis, plan


def append_repair_outcome(project: Path, outcome: RepairOutcome) -> Path:
    """Append a compact outcome without manuscript, audio, or personal data."""

    path = project / "production/repair-outcomes.jsonl"
    row = {
        "version": 1,
        **asdict(outcome),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    row["outcome_sha256"] = _canonical(
        {key: value for key, value in row.items() if key != "recorded_at"}
    )
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if row["outcome_sha256"] not in existing:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def strategy_priors(project: Path, defect: str) -> list[str]:
    """Rank historically accepted strategies without changing gate authority."""

    path = project / "production/repair-outcomes.jsonl"
    counts: dict[str, int] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            strategy = row.get("accepted_strategy")
            if (
                row.get("defect") == defect
                and strategy
                and row.get("listener_result") == "accepted"
            ):
                counts[str(strategy)] = counts.get(str(strategy), 0) + 1
    return [
        key
        for key, _value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def automatic_execution_mode(plan: dict[str, Any]) -> str:
    """Collapse a repair plan to one conservative executable mode."""

    strategies = {
        str(row.get("strategy", {}).get("id"))
        for row in plan.get("repairs", [])
        if isinstance(row, dict) and isinstance(row.get("strategy"), dict)
    }
    if not strategies:
        return "none"
    if strategies <= {"reverify_cached_evidence"}:
        return "reverify"
    if strategies <= {"bounded_pace_resynthesis"}:
        return "regenerate_failed_units"
    return "review_required"
