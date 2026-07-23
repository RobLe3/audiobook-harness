from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from rapidfuzz.distance import Levenshtein

from .project import normalized_words, project_paths, sha256, write_json
from .pronunciation import audit_lexicon


def _transcribe(model: Any, audio: Path) -> str:
    result = model.transcribe(str(audio), fp16=False, verbose=False)
    return str(result.get("text", "")).strip()


def verify(project: Path, repo: Path) -> dict[str, Any]:
    import whisper

    paths = project_paths(project)
    lexicon_report = audit_lexicon(project)
    generation = json.loads((paths["production"] / "generation.json").read_text(encoding="utf-8"))
    whisper_root = repo / ".tools/whisper/models"
    primary_path, secondary_path = whisper_root / "large-v3-turbo.pt", whisper_root / "base.pt"
    if not primary_path.exists() or not secondary_path.exists():
        raise FileNotFoundError("Whisper primary/secondary models missing; run explicit model setup")
    primary, secondary = whisper.load_model(str(primary_path)), whisper.load_model(str(secondary_path))
    rows = []; failures = []
    for take in generation["takes"]:
        audio_path = project / str(take["file"])
        audio, rate = sf.read(audio_path, dtype="float32")
        mono = np.mean(audio, axis=1) if getattr(audio, "ndim", 1) > 1 else audio
        expected = normalized_words(str(take["text"]))
        first, second = normalized_words(_transcribe(primary, audio_path)), normalized_words(_transcribe(secondary, audio_path))
        first_error = Levenshtein.distance(expected, first) / max(1, len(expected))
        second_error = Levenshtein.distance(expected, second) / max(1, len(expected))
        peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
        duration = len(mono) / rate if rate else 0.0
        ok = first_error <= 0.01 and second_error <= 0.01 and peak < 0.995 and 0.15 <= duration <= max(2.0, len(expected) * 1.25)
        row = {**take, "primary_text": " ".join(first), "secondary_text": " ".join(second), "primary_wer": round(first_error, 4), "secondary_wer": round(second_error, 4), "peak": peak, "duration_seconds": duration, "ok": ok}
        rows.append(row)
        if not ok: failures.append(take["id"])
    # MFA is required by professional mode; validate its executable/config now.
    mfa = shutil.which("mfa") or str(repo / ".tools/mfa/bin/mfa")
    mfa_available = Path(mfa).exists() or shutil.which("mfa") is not None
    report = {"version": 1, "ok": lexicon_report["ok"] and not failures and mfa_available, "lexicon": lexicon_report, "mfa_available": mfa_available, "takes": rows, "failures": failures}
    write_json(paths["production"] / "verification.json", report)
    return report
