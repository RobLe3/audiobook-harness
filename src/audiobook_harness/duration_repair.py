"""Optional, bounded span-local duration repair for review candidates."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .boundary_repair import equal_power_crossfade


MINIMUM_TIME_RATIO = 0.88
CONTEXT_PADDING_MS = 20
CROSSFADE_MS = 10


def localized_duration_repair_plan(
    *,
    start_seconds: float,
    end_seconds: float,
    target_duration_seconds: float,
    prominence_protected: bool,
    duration_correction_eligible: bool,
) -> dict[str, Any]:
    current = end_seconds - start_seconds
    ratio = target_duration_seconds / current if current > 0 else 0.0
    eligible = (
        duration_correction_eligible
        and not prominence_protected
        and 0 < target_duration_seconds < current
        and MINIMUM_TIME_RATIO <= ratio < 1.0
    )
    return {
        "eligible": eligible,
        "current_duration_seconds": round(current, 6),
        "target_duration_seconds": round(target_duration_seconds, 6),
        "time_ratio": round(ratio, 6),
        "maximum_compression": round(1.0 - MINIMUM_TIME_RATIO, 6),
        "context_padding_ms": CONTEXT_PADDING_MS,
        "crossfade_ms": CROSSFADE_MS,
        "reason": (
            "bounded_low_information_span"
            if eligible
            else "requires_contextual_resynthesis"
        ),
        "automatic_release_authority": False,
    }


def render_localized_duration_candidate(
    audio: np.ndarray,
    sample_rate: int,
    *,
    start_seconds: float,
    end_seconds: float,
    target_duration_seconds: float,
    rubberband_binary: str | Path | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Compress one aligned span with an external, fingerprinted offline tool."""

    plan = localized_duration_repair_plan(
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        target_duration_seconds=target_duration_seconds,
        prominence_protected=False,
        duration_correction_eligible=True,
    )
    if not plan["eligible"]:
        raise ValueError("span exceeds the conservative local-duration repair limit")
    binary = Path(rubberband_binary) if rubberband_binary else None
    if binary is None:
        located = shutil.which("rubberband")
        binary = Path(located) if located else None
    if binary is None or not binary.is_file():
        raise FileNotFoundError("rubberband is unavailable; use contextual resynthesis")
    source = np.asarray(audio, dtype=np.float32)
    if source.ndim != 1:
        raise ValueError("localized duration repair currently requires mono PCM")
    start = max(0, round(start_seconds * sample_rate))
    end = min(len(source), round(end_seconds * sample_rate))
    padding = round(CONTEXT_PADDING_MS * sample_rate / 1000)
    edit_start = max(0, start - padding)
    edit_end = min(len(source), end + padding)
    segment = source[edit_start:edit_end]
    target_samples = (
        round(target_duration_seconds * sample_rate)
        + (start - edit_start)
        + (edit_end - end)
    )
    time_ratio = target_samples / len(segment)
    with tempfile.TemporaryDirectory(prefix="audiobook-duration-") as tmp:
        source_path = Path(tmp) / "source.wav"
        target_path = Path(tmp) / "target.wav"
        sf.write(source_path, segment, sample_rate, subtype="PCM_24")
        subprocess.run(
            [
                str(binary),
                "-3",
                "-t",
                f"{time_ratio:.9f}",
                str(source_path),
                str(target_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        replacement, rendered_rate = sf.read(target_path, dtype="float32")
    if rendered_rate != sample_rate:
        raise RuntimeError("localized duration tool changed sample rate")
    fade = min(
        round(CROSSFADE_MS * sample_rate / 1000),
        len(source[:edit_start]),
        len(source[edit_end:]),
        len(replacement) // 3,
    )
    joined = equal_power_crossfade(source[:edit_start], replacement, fade)
    joined = equal_power_crossfade(joined, source[edit_end:], fade)
    evidence = {
        **plan,
        "tool": str(binary),
        "tool_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "edited_source_span_samples": [edit_start, edit_end],
        "preserved_prefix_sha256": hashlib.sha256(
            source[:edit_start].tobytes()
        ).hexdigest(),
        "preserved_suffix_sha256": hashlib.sha256(
            source[edit_end:].tobytes()
        ).hexdigest(),
        "output_duration_seconds": round(len(joined) / sample_rate, 6),
    }
    return np.asarray(joined, dtype=np.float32), evidence
