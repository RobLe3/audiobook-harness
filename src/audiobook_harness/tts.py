from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .project import load_project, project_paths, sha256, write_json
from .pronunciation import apply_to_phonemes, audit_lexicon, load_reviewed_lexicon

SAMPLE_RATE = 24_000


def model_paths(repo: Path) -> tuple[Path, Path]:
    model_root = repo / ".tools/kokoro/models"
    return model_root / "kokoro-v1.0.onnx", model_root / "voices-v1.0.bin"


def generate(project: Path, repo: Path) -> dict[str, Any]:
    from kokoro_onnx import Kokoro

    paths = project_paths(project)
    config = load_project(project)
    analysis = json.loads((paths["production"] / "analysis.json").read_text(encoding="utf-8"))
    lexicon_audit = audit_lexicon(project)
    if not lexicon_audit["ok"]:
        raise RuntimeError(
            "Generation is blocked until pronunciation-sensitive vocabulary is reviewed; "
            "see production/pronunciation-audit.json"
        )
    lexicon = load_reviewed_lexicon(project)
    model, voices = model_paths(repo)
    if not model.is_file() or not voices.is_file():
        raise FileNotFoundError("Kokoro model files are missing; run scripts/setup.py --download-models")
    voice = str(config.get("voice", {}).get("id", "bm_george"))
    speed = float(config.get("voice", {}).get("speed", 0.95))
    language = str(config.get("language", "en-gb"))
    engine = Kokoro(str(model), str(voices))
    rows: list[dict[str, Any]] = []
    for chapter in analysis["chapters"]:
        for unit in chapter["units"]:
            text = str(unit["text"])
            phonemes = engine.tokenizer.phonemize(text, language)
            phonemes = apply_to_phonemes(
                text, phonemes, lexicon, lambda value: engine.tokenizer.phonemize(value, language)
            )
            audio, rate = engine.create(phonemes, voice=voice, speed=speed, lang=language, trim=True, is_phonemes=True)
            if rate != SAMPLE_RATE:
                raise RuntimeError(f"Expected Kokoro {SAMPLE_RATE} Hz output, received {rate}")
            target = paths["assets"] / chapter["id"] / f"{unit['id']}.flac"
            target.parent.mkdir(parents=True, exist_ok=True)
            sf.write(target, np.asarray(audio, dtype=np.float32), rate, subtype="PCM_24", format="FLAC")
            rows.append({"id": unit["id"], "chapter": chapter["id"], "text": text, "phonemes": phonemes, "voice": voice, "speed": speed, "file": str(target.relative_to(project)), "sha256": sha256(target)})
    report = {"version": 1, "offline": True, "sample_rate": SAMPLE_RATE, "takes": rows}
    write_json(paths["production"] / "generation.json", report)
    return report


def assemble(project: Path) -> dict[str, Any]:
    """Join already-verified takes and create lossless master plus M4A/MP3."""
    paths = project_paths(project)
    verification = json.loads((paths["production"] / "verification.json").read_text(encoding="utf-8"))
    if not verification.get("ok"):
        raise RuntimeError("Cannot release: verification is not successful")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in verification["takes"]:
        grouped.setdefault(str(row["chapter"]), []).append(row)
    outputs = []
    for chapter, rows in grouped.items():
        concat = paths["production"] / f"{chapter}.ffconcat"
        concat.write_text("ffconcat version 1.0\n" + "".join(f"file '../{row['file']}'\n" for row in rows), encoding="utf-8")
        master = paths["deliverables"] / f"{chapter}_Audiobook.flac"; master.parent.mkdir(parents=True, exist_ok=True)
        for suffix, codec, extra in ((".flac", "flac", []), (".m4a", "aac", ["-b:a", "256k"]), (".mp3", "libmp3lame", ["-b:a", "256k"])):
            target = master.with_suffix(suffix)
            command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:a", codec, *extra, str(target)]
            if shutil.which("ffmpeg") is None:
                raise RuntimeError("ffmpeg is required for release")
            __import__("subprocess").run(command, check=True)
        chapter_outputs = []
        for suffix in (".flac", ".m4a", ".mp3"):
            target = master.with_suffix(suffix)
            chapter_outputs.append({"file": str(target.relative_to(project)), "sha256": sha256(target)})
        outputs.append({"chapter": chapter, "files": chapter_outputs})
    report = {"version": 2, "release_rule": "only verified, hash-recorded take files may be packaged", "outputs": outputs}
    write_json(paths["production"] / "release-manifest.json", report)
    return report
