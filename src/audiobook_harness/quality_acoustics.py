"""Pure acoustic gate calculations, isolated from ASR and report orchestration."""

from __future__ import annotations

import numpy as np

from .quality_policy import ACOUSTIC_THRESHOLDS


def acoustic_failures(mono: np.ndarray, rate: int, words: int) -> list[str]:
    failures: list[str] = []
    if not len(mono):
        return ["empty_audio"]
    if float(np.max(np.abs(mono))) >= ACOUSTIC_THRESHOLDS["clipping_peak"]:
        failures.append("clipping")
    duration = len(mono) / max(1, rate)
    if duration < ACOUSTIC_THRESHOLDS["minimum_duration_seconds"] or duration > max(
        ACOUSTIC_THRESHOLDS["maximum_duration_seconds_floor"],
        words * ACOUSTIC_THRESHOLDS["maximum_duration_seconds_per_word"],
    ):
        failures.append("abnormal_duration")
    if (
        words
        and duration / words > ACOUSTIC_THRESHOLDS["maximum_word_duration_seconds"]
    ):
        failures.append("long_word_duration_risk")
    frame = max(1, int(rate * ACOUSTIC_THRESHOLDS["silence_frame_seconds"]))
    usable = mono[: len(mono) - len(mono) % frame]
    if len(usable):
        quiet = np.sqrt(
            np.mean(usable.reshape(-1, frame) ** 2, axis=1) + 1e-12
        ) < 10 ** (ACOUSTIC_THRESHOLDS["silence_rms_dbfs"] / 20)
        longest = current = 0
        for value in quiet:
            current = current + 1 if value else 0
            longest = max(longest, current)
        if (
            longest * frame / rate
            > ACOUSTIC_THRESHOLDS["maximum_internal_silence_seconds"]
        ):
            failures.append("unexpected_silence")
    return failures
