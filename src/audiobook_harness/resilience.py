"""Evidence-bound recovery helpers for unattended local production."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from .project import sha256


class GateDisposition(StrEnum):
    PASS = "pass"
    RETRY_TRANSIENT = "retry_transient"
    REPAIR_ARTIFACT = "repair_artifact"
    REVIEW_REQUIRED = "review_required"
    BLOCKED_EVIDENCE = "blocked_evidence"
    FATAL_TOOL_FAILURE = "fatal_tool_failure"
    BLOCKED_UNKNOWN = "blocked_unknown"
    PHASE_CONTRACT_FAILURE = "phase_contract_failure"


@dataclass(frozen=True)
class GateResult:
    gate: str
    disposition: GateDisposition
    owner_phase: int
    evidence_fingerprint: str
    affected_units: tuple[str, ...] = ()
    invalidated_artifacts: tuple[str, ...] = ()
    next_action: str = "none"
    remaining_attempts: int = 0
    detail: str = ""
    attempt_id: str = ""
    input_identity: str = ""
    evidence_paths: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def blocks_series(self) -> bool:
        return self.disposition == GateDisposition.FATAL_TOOL_FAILURE

    @property
    def blocks_chapter(self) -> bool:
        return self.disposition not in {
            GateDisposition.PASS,
            GateDisposition.RETRY_TRANSIENT,
            GateDisposition.REPAIR_ARTIFACT,
        }


@dataclass(frozen=True)
class RepairTicket:
    """One bounded repair whose execution must change its owning phase input."""

    repair_id: str
    gate: str
    owner_phase: int
    affected_units: tuple[str, ...]
    action: str
    input_identity: str
    expected_input_delta: str
    evidence_fingerprint: str = ""
    attempt_id: str = ""
    implementation_fingerprint: str = ""
    status: str = "queued"
    remaining_attempts: int = 1
    fallback: GateDisposition = GateDisposition.REVIEW_REQUIRED

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def repair_ticket(
    result: GateResult,
    *,
    action: str,
    expected_input_delta: str,
    implementation_fingerprint: str = "",
) -> RepairTicket:
    """Create a stable repair ticket from current-attempt gate evidence."""

    value = {
        "gate": result.gate,
        "owner_phase": result.owner_phase,
        "affected_units": sorted(result.affected_units),
        "action": action,
        "input_identity": result.input_identity,
        "evidence_fingerprint": result.evidence_fingerprint,
        "implementation_fingerprint": implementation_fingerprint,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return RepairTicket(
        repair_id=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        gate=result.gate,
        owner_phase=result.owner_phase,
        affected_units=result.affected_units,
        action=action,
        input_identity=result.input_identity,
        expected_input_delta=expected_input_delta,
        evidence_fingerprint=result.evidence_fingerprint,
        attempt_id=result.attempt_id,
        implementation_fingerprint=implementation_fingerprint,
        remaining_attempts=max(0, result.remaining_attempts),
    )


def reopen_ticket_after_harness_correction(
    ticket: RepairTicket,
    result: GateResult,
    *,
    implementation_fingerprint: str,
) -> RepairTicket | None:
    """Reopen an exhausted repair once for a distinct tested implementation."""

    if ticket.status != "exhausted":
        return None
    if ticket.implementation_fingerprint == implementation_fingerprint:
        return None
    return repair_ticket(
        result,
        action=ticket.action,
        expected_input_delta="tested harness implementation changed",
        implementation_fingerprint=implementation_fingerprint,
    )


def validate_phase_commit(
    *,
    result: GateResult,
    owned_artifacts: tuple[Path, ...],
    attempt_id: str,
) -> GateResult:
    """Refuse a success receipt unless every declared phase output exists."""

    if result.disposition != GateDisposition.PASS:
        return result
    missing = tuple(str(path) for path in owned_artifacts if not path.is_file())
    if not missing:
        return result
    fingerprint = hashlib.sha256(
        json.dumps(
            {"attempt_id": attempt_id, "missing": sorted(missing)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return GateResult(
        gate="phase_output_contract",
        disposition=GateDisposition.PHASE_CONTRACT_FAILURE,
        owner_phase=result.owner_phase,
        evidence_fingerprint=fingerprint,
        affected_units=result.affected_units,
        invalidated_artifacts=missing,
        next_action="correct_harness_phase",
        detail="The phase reported success without committing every owned artifact.",
        attempt_id=attempt_id,
        input_identity=result.input_identity,
    )


def production_input_identity(project: Path, repo: Path) -> str:
    """Fingerprint authored inputs and the local harness implementation."""
    files = [
        project / "project.yaml",
        project / "lexicon.json",
        repo / "models.lock.json",
        repo / "pyproject.toml",
        *sorted((project / "source").glob("*.txt")),
        *sorted((repo / "src/audiobook_harness").glob("*.py")),
    ]
    rows = [
        {
            "path": (
                f"project/{path.relative_to(project)}"
                if path.is_relative_to(project)
                else f"harness/{path.relative_to(repo)}"
            ),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in files
        if path.is_file()
    ]
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def candidate_failure_signature(failures: list[str], input_identity: str) -> str:
    value = {
        "classification": "candidate_quality_rejection",
        "action": "regenerate_failed_units",
        "failed_units": sorted({str(item) for item in failures}),
        "input_identity": input_identity,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def terminal_signatures(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    signatures: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("signature"):
            signatures.add(str(row["signature"]))
    return signatures


def decide_candidate_retry(
    failures: list[str],
    *,
    input_identity: str,
    previous_signatures: set[str],
    remaining_budget: int,
) -> dict[str, Any]:
    """Retry failed units only when this exact failure has not proved terminal."""
    signature = candidate_failure_signature(failures, input_identity)
    if not failures:
        return {
            "retry": False,
            "reason": "no_failed_candidate_units",
            "signature": signature,
        }
    if remaining_budget <= 0:
        return {
            "retry": False,
            "reason": "retry_budget_exhausted",
            "signature": signature,
        }
    if signature in previous_signatures:
        return {
            "retry": False,
            "reason": "identical_failure_already_terminal_for_same_inputs",
            "signature": signature,
        }
    return {
        "retry": True,
        "reason": "bounded_failed_unit_regeneration",
        "signature": signature,
        "action": "regenerate_failed_units",
    }


def append_terminal_failure(
    path: Path,
    *,
    signature: str,
    input_identity: str,
    failures: list[str],
    reason: str,
) -> None:
    """Remember a repeated rejection without storing manuscript or audio."""
    row = {
        "version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "classification": "candidate_quality_rejection",
        "signature": signature,
        "input_identity": input_identity,
        "failed_unit_ids": sorted({str(item) for item in failures}),
        "reason": reason,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
