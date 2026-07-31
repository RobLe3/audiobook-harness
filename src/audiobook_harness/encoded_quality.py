from __future__ import annotations

from typing import Any


CODEC_FRAME_SAMPLES = {"aac": 1024, "mp3": 1152}


def codec_frame_tolerance_seconds(codec: object, sample_rate: object) -> float:
    rate = int(sample_rate or 0)
    samples = CODEC_FRAME_SAMPLES.get(str(codec or "").casefold(), 1)
    return samples / rate if rate > 0 else 0.0


def encoded_tail_result(
    *,
    master_tail_seconds: float,
    encoded_tail_seconds: float | None,
    codec: object,
    sample_rate: object,
) -> dict[str, Any]:
    """Compare decoded silence with the authored PCM tail.

    The PCM assembly remains authoritative. AAC and MP3 may report one frame
    of encoder delay or padding, which is recorded rather than mistaken for a
    content or mastering defect.
    """

    tolerance = codec_frame_tolerance_seconds(codec, sample_rate)
    delta = (
        None
        if encoded_tail_seconds is None
        else float(encoded_tail_seconds) - float(master_tail_seconds)
    )
    ok = delta is not None and abs(delta) <= tolerance
    return {
        "master_tail_seconds": float(master_tail_seconds),
        "encoded_tail_seconds": encoded_tail_seconds,
        "codec_frame_tolerance_seconds": round(tolerance, 9),
        "tail_delta_seconds": round(delta, 9) if delta is not None else None,
        "tail_status": (
            "within_codec_frame_tolerance"
            if ok and delta
            else "matches_pcm_policy"
            if ok
            else "outside_codec_frame_tolerance"
        ),
        "ok": ok,
    }
