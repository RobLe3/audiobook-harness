"""Deterministic assembly-boundary measurement and repair primitives."""

from __future__ import annotations

import numpy as np


def boundary_discontinuity(left: np.ndarray, right: np.ndarray) -> dict[str, float]:
    if not len(left) or not len(right):
        return {"sample_jump": 1.0, "slope_jump": 1.0}
    sample_jump = abs(float(right[0]) - float(left[-1]))
    left_slope = float(left[-1] - left[-2]) if len(left) > 1 else 0.0
    right_slope = float(right[1] - right[0]) if len(right) > 1 else 0.0
    return {
        "sample_jump": round(sample_jump, 8),
        "slope_jump": round(abs(right_slope - left_slope), 8),
    }


def equal_power_crossfade(
    left: np.ndarray, right: np.ndarray, samples: int
) -> np.ndarray:
    """Join two mono arrays without changing samples outside the declared span."""

    count = min(max(0, samples), len(left), len(right))
    if count == 0:
        return np.concatenate((left, right)).astype(np.float32, copy=False)
    phase = np.linspace(0.0, np.pi / 2.0, count, dtype=np.float32)
    overlap = left[-count:] * np.cos(phase) + right[:count] * np.sin(phase)
    return np.concatenate((left[:-count], overlap, right[count:])).astype(
        np.float32, copy=False
    )
