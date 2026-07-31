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
