"""Transactional, typed execution for one local audiobook phase."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .pipeline import Phase
from .project import write_json
from .run_journal import (
    append_event,
    invalidate_phase_receipts_from,
    write_phase_receipt,
)


@dataclass(frozen=True)
class PhaseResult:
    status: str
    owner_phase: int
    failure_code: str | None = None
    affected_units: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    recommended_action: str = "none"
    retryable: bool = False
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "passed"


class PhaseExecutionError(RuntimeError):
    def __init__(self, result: PhaseResult):
        super().__init__(result.detail or result.failure_code or result.status)
        self.result = result


def classify_failure(phase: Phase, error: BaseException) -> PhaseResult:
    if isinstance(error, PhaseExecutionError):
        return error.result
    if isinstance(error, (TimeoutError, InterruptedError)):
        return PhaseResult(
            "transient_failure",
            phase.number,
            failure_code=type(error).__name__,
            recommended_action="retry_same_phase",
            retryable=True,
            detail=str(error),
        )
    if isinstance(error, ValueError) and (
        "pronunciation" in str(error).casefold()
        or "lexicon phonemes" in str(error).casefold()
    ):
        return PhaseResult(
            "repairable_failure",
            phase.number,
            failure_code="pronunciation_span_unresolved",
            recommended_action="review_pronunciation_or_context_span",
            detail=str(error),
        )
    if isinstance(error, (FileNotFoundError, ValueError)):
        code = "phase_input_or_contract_invalid"
    else:
        code = "unhandled_tool_failure"
    return PhaseResult(
        "implementation_failure",
        phase.number,
        failure_code=code,
        recommended_action="correct_harness_phase",
        detail=f"{type(error).__name__}: {error}",
    )


def _validate_outputs(project: Path, phase: Phase) -> None:
    production = project / "production"
    missing = [
        name for name in phase.required_artifacts if not (production / name).is_file()
    ]
    if missing:
        raise PhaseExecutionError(
            PhaseResult(
                "implementation_failure",
                phase.number,
                failure_code="phase_output_contract_failure",
                evidence=tuple(missing),
                recommended_action="correct_harness_phase",
                detail=f"Phase completed without owned outputs: {missing}",
            )
        )
    for artifact, field in phase.success_predicates:
        try:
            value = json.loads((production / artifact).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PhaseExecutionError(
                PhaseResult(
                    "implementation_failure",
                    phase.number,
                    failure_code="malformed_gate_result",
                    evidence=(artifact,),
                    recommended_action="correct_harness_phase",
                    detail=str(error),
                )
            ) from error
        if not isinstance(value, dict) or value.get(field) is not True:
            raise PhaseExecutionError(
                PhaseResult(
                    "repairable_failure",
                    phase.number,
                    failure_code="quality_gate_rejected",
                    evidence=(artifact,),
                    recommended_action="apply_registered_phase_repair",
                    retryable=True,
                    detail=f"{artifact}.{field} is not true",
                )
            )


def execute_phase(
    project: Path,
    *,
    phase: Phase,
    input_identity: str,
    action: Callable[[], Any],
) -> tuple[Any, PhaseResult]:
    """Run one phase with rollback, semantic validation, and receipt-last commit."""
    production = project / "production"
    production.mkdir(parents=True, exist_ok=True)
    owned = [production / name for name in phase.required_artifacts]
    backup_root = Path(
        tempfile.mkdtemp(prefix=f"phase-{phase.number}-", dir=production)
    )
    existed: dict[Path, Path] = {}
    for path in owned:
        if path.is_file():
            backup = backup_root / path.name
            shutil.copy2(path, backup)
            existed[path] = backup
    invalidate_phase_receipts_from(project, step=phase.number)
    journal = production / "phase-events.jsonl"
    append_event(
        journal,
        {
            "event": "phase_started",
            "phase": phase.number,
            "name": phase.name,
            "input_identity": input_identity,
        },
    )
    try:
        value = action()
        _validate_outputs(project, phase)
        result = PhaseResult(
            "passed",
            phase.number,
            evidence=tuple(f"production/{name}" for name in phase.required_artifacts),
        )
        write_phase_receipt(
            project,
            step=phase.number,
            input_identity=input_identity,
            artifacts=owned,
            success_predicates=phase.success_predicates,
        )
        write_json(production / "phase-result.json", asdict(result))
        append_event(
            journal,
            {
                "event": "phase_committed",
                "phase": phase.number,
                "input_identity": input_identity,
                "result": asdict(result),
            },
        )
        return value, result
    except BaseException as error:
        result = classify_failure(phase, error)
        if result.status not in {"repairable_failure", "review_required"}:
            for path in owned:
                path.unlink(missing_ok=True)
                if path in existed:
                    shutil.copy2(existed[path], path)
        write_json(production / "phase-result.json", asdict(result))
        append_event(
            journal,
            {
                "event": "phase_failed",
                "phase": phase.number,
                "input_identity": input_identity,
                "result": asdict(result),
            },
        )
        raise PhaseExecutionError(result) from error
    finally:
        shutil.rmtree(backup_root, ignore_errors=True)
