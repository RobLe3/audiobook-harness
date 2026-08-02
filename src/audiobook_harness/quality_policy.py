"""Versioned semantics for objective quality-gate outcomes."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


POLICY_VERSION = 1


class QualityDisposition(StrEnum):
    PASS = "pass"
    AUTOMATIC_REPAIR = "automatic_repair"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


def classify_quality_report(report: dict[str, Any]) -> dict[str, Any]:
    """Classify machine evidence without granting subjective approval authority."""
    failures = [str(value) for value in report.get("failures", [])]
    lexicon = report.get("lexicon")
    alignment = report.get("forced_alignment")
    if report.get("ok") is True:
        disposition = QualityDisposition.PASS
        reason = "all objective quality gates passed"
    elif isinstance(lexicon, dict) and not lexicon.get("ok", False):
        disposition = QualityDisposition.REVIEW_REQUIRED
        reason = "reviewed pronunciation or spoken-form evidence is incomplete"
    elif (
        isinstance(alignment, dict) and not alignment.get("ok", False) and not failures
    ):
        disposition = QualityDisposition.BLOCKED
        reason = "forced-alignment evidence is unavailable or invalid"
    elif failures:
        disposition = QualityDisposition.AUTOMATIC_REPAIR
        reason = "failed units have candidate evidence for bounded repair"
    else:
        disposition = QualityDisposition.REVIEW_REQUIRED
        reason = "objective evidence is incomplete or ambiguous"
    return {
        "version": POLICY_VERSION,
        "disposition": disposition.value,
        "reason": reason,
        "objective_authority": disposition == QualityDisposition.PASS,
        "subjective_approval_required": disposition != QualityDisposition.PASS,
        "failed_units": failures,
    }
