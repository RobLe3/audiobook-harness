"""Versioned semantics for objective quality-gate outcomes."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any


POLICY_VERSION = 1
POLICY_CONTRACT = {
    "version": POLICY_VERSION,
    "precedence": (
        "pronunciation_or_spoken_form_review",
        "alignment_block",
        "encoded_media_block",
        "nonrepairable_acoustic_block",
        "bounded_failed_unit_repair",
        "objective_pass",
        "incomplete_or_ambiguous_review",
    ),
    "subjective_listener_authority": "never_automatic",
}


class QualityDisposition(StrEnum):
    PASS = "pass"
    AUTOMATIC_REPAIR = "automatic_repair"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


def policy_identity() -> str:
    """Return the stable identity of the result-affecting policy contract."""
    payload = json.dumps(POLICY_CONTRACT, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_quality_report(report: dict[str, Any]) -> dict[str, Any]:
    """Classify machine evidence without granting subjective approval authority."""
    failures = [str(value) for value in report.get("failures", [])]
    lexicon = report.get("lexicon")
    alignment = report.get("forced_alignment")
    acoustic = report.get("acoustic")
    encoding = report.get("encoding")
    if isinstance(lexicon, dict) and not lexicon.get("ok", False):
        disposition = QualityDisposition.REVIEW_REQUIRED
        reason = "reviewed pronunciation or spoken-form evidence is incomplete"
    elif (
        isinstance(alignment, dict) and not alignment.get("ok", False) and not failures
    ):
        disposition = QualityDisposition.BLOCKED
        reason = "forced-alignment evidence is unavailable or invalid"
    elif isinstance(encoding, dict) and not encoding.get("ok", False):
        disposition = QualityDisposition.BLOCKED
        reason = "encoded-deliverable evidence is unavailable or invalid"
    elif (
        isinstance(acoustic, dict)
        and not acoustic.get("ok", False)
        and acoustic.get("repairable") is False
    ):
        disposition = QualityDisposition.BLOCKED
        reason = "acoustic evidence identifies a non-repairable release defect"
    elif failures:
        disposition = QualityDisposition.AUTOMATIC_REPAIR
        reason = "failed units have candidate evidence for bounded repair"
    elif report.get("ok") is True:
        disposition = QualityDisposition.PASS
        reason = "all objective quality gates passed"
    else:
        disposition = QualityDisposition.REVIEW_REQUIRED
        reason = "objective evidence is incomplete or ambiguous"
    return {
        "version": POLICY_VERSION,
        "policy_identity_sha256": policy_identity(),
        "disposition": disposition.value,
        "reason": reason,
        "objective_authority": disposition == QualityDisposition.PASS,
        "subjective_approval_required": disposition != QualityDisposition.PASS,
        "failed_units": failures,
    }
