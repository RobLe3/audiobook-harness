"""Versioned evidence contract for contextual terse-dialogue performances."""

from __future__ import annotations

from typing import Any


CONTEXTUAL_PERFORMANCE_PROTOCOL = "adjacent_manuscript_context_single_performance_v1"


def protocol_for_unit(unit: dict[str, Any]) -> str | None:
    """Return the release protocol only when a unit contains terse dialogue."""
    if bool(unit.get("contains_terse_dialogue")):
        return CONTEXTUAL_PERFORMANCE_PROTOCOL
    return None


def candidate_protocol_error(candidate: dict[str, Any]) -> str | None:
    """Reject stale contextual candidates before they can be packaged."""
    if not bool(candidate.get("contains_terse_dialogue")):
        return None
    if candidate.get("context_protocol") != CONTEXTUAL_PERFORMANCE_PROTOCOL:
        return "stale_contextual_performance_protocol"
    if candidate.get("context_strategy") != "adjacent_manuscript_context":
        return "invalid_contextual_performance_strategy"
    return None
