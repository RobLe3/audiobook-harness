"""Immutable clean-take and derived-render lineage contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def take_identity(*, clean_audio_sha256: str, synthesis: dict[str, Any]) -> str:
    """Identify the performed speech independently of later channel rendering."""

    return canonical_sha256(
        {
            "contract": "audiobook-clean-take-v1",
            "clean_audio_sha256": clean_audio_sha256,
            "synthesis": synthesis,
        }
    )


def render_identity(
    *,
    take_id: str,
    processed_audio_sha256: str,
    processor: dict[str, Any],
) -> str:
    """Identify one derived render of an immutable clean performance."""

    return canonical_sha256(
        {
            "contract": "audiobook-derived-render-v1",
            "take_id": take_id,
            "processed_audio_sha256": processed_audio_sha256,
            "processor": processor,
        }
    )


def pcm_lineage_metrics(
    expected: np.ndarray,
    observed: np.ndarray,
    *,
    edge_guard_samples: int = 0,
) -> dict[str, float | int | bool]:
    """Measure deterministic legacy replay without treating similarity as approval."""

    expected = np.asarray(expected, dtype=np.float64).reshape(-1)
    observed = np.asarray(observed, dtype=np.float64).reshape(-1)
    same_length = len(expected) == len(observed)
    if not same_length or not len(expected):
        return {
            "same_length": same_length,
            "sample_count": len(observed),
            "correlation": 0.0,
            "mean_absolute_error": float("inf"),
            "maximum_absolute_error": float("inf"),
        }
    guard = min(max(0, edge_guard_samples), max(0, len(expected) // 2 - 1))
    stop = len(expected) - guard if guard else len(expected)
    reference = expected[guard:stop]
    candidate = observed[guard:stop]
    error = np.abs(reference - candidate)
    correlation = (
        float(np.corrcoef(reference, candidate)[0, 1])
        if np.std(reference) and np.std(candidate)
        else float(np.array_equal(reference, candidate))
    )
    return {
        "same_length": True,
        "sample_count": len(expected),
        "edge_guard_samples": guard,
        "correlation": correlation,
        "mean_absolute_error": float(np.mean(error)),
        "maximum_absolute_error": float(np.max(error)),
    }


def legacy_lineage_passes(
    metrics: dict[str, float | int | bool],
    *,
    minimum_correlation: float,
    maximum_mean_error: float,
    maximum_peak_error: float,
) -> bool:
    """Apply an explicit migration policy; callers must record all thresholds."""

    return bool(
        metrics.get("same_length")
        and float(metrics.get("correlation", 0.0)) >= minimum_correlation
        and float(metrics.get("mean_absolute_error", float("inf")))
        <= maximum_mean_error
        and float(metrics.get("maximum_absolute_error", float("inf")))
        <= maximum_peak_error
    )
