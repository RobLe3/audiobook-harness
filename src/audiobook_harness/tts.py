from __future__ import annotations

import json
import shutil
import subprocess
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .project import load_project, project_paths, sha256, write_json
from .pronunciation import apply_to_phonemes, audit_lexicon, load_reviewed_lexicon
from .selection_integrity import audit_candidate_selection

SAMPLE_RATE = 24_000
VARIANTS = (("baseline", 0.0), ("slower", -0.01), ("faster", 0.01))
RETRY_VARIANTS = VARIANTS + (("retry_slower", -0.02), ("retry_faster", 0.02))


def model_paths(repo: Path) -> tuple[Path, Path]:
    root = repo / ".tools/kokoro/models"
    return root / "kokoro-v1.0.onnx", root / "voices-v1.0.bin"


def _source_hash(unit: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                k: unit.get(k)
                for k in ("id", "text", "source_sentence_indexes", "context_strategy")
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def generate(project: Path, repo: Path, *, failed_only: bool = False) -> dict[str, Any]:
    from kokoro_onnx import Kokoro

    paths, config = project_paths(project), load_project(project)
    analysis = json.loads((paths["production"] / "analysis.json").read_text())
    if not audit_lexicon(project)["ok"] or analysis.get(
        "contextual_dialogue_review_required"
    ):
        raise RuntimeError(
            "Generation is blocked until pronunciation and contextual-dialogue review pass."
        )
    prior = (
        json.loads((paths["production"] / "verification.json").read_text())
        if (paths["production"] / "verification.json").exists()
        else {}
    )
    failed = set(prior.get("failures", []))
    if failed_only and not failed:
        return {"ok": True, "message": "No failed takes require retry.", "takes": []}
    model, voices = model_paths(repo)
    if not model.is_file() or not voices.is_file():
        raise FileNotFoundError(
            "Kokoro model files are missing; run explicit model setup."
        )
    voice, speed, language = (
        str(config.get("voice", {}).get("id", "bm_george")),
        float(config.get("voice", {}).get("speed", 0.95)),
        str(config.get("language", "en-gb")),
    )
    engine, lexicon = Kokoro(str(model), str(voices)), load_reviewed_lexicon(project)
    candidates: list[dict[str, Any]] = []
    for chapter in analysis["chapters"]:
        for unit in chapter["units"]:
            unit_id, text = str(unit["id"]), str(unit["text"])
            if failed_only and unit_id not in failed:
                continue
            phonemes = apply_to_phonemes(
                text,
                engine.tokenizer.phonemize(text, language),
                lexicon,
                lambda value: engine.tokenizer.phonemize(value, language),
            )
            source_hash = _source_hash(unit)
            for name, delta in RETRY_VARIANTS if failed_only else VARIANTS:
                actual_speed = max(0.85, min(1.05, speed + delta))
                audio, rate = engine.create(
                    phonemes,
                    voice=voice,
                    speed=actual_speed,
                    lang=language,
                    trim=True,
                    is_phonemes=True,
                )
                if rate != SAMPLE_RATE:
                    raise RuntimeError(
                        f"Expected {SAMPLE_RATE} Hz output, received {rate}"
                    )
                candidate_identity = hashlib.sha256(
                    json.dumps(
                        {
                            "candidate": name,
                            "phonemes": phonemes,
                            "source_hash": source_hash,
                            "voice": voice,
                            "speed": actual_speed,
                        },
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()
                target = (
                    paths["assets"]
                    / "candidates"
                    / chapter["id"]
                    / unit_id
                    / f"{name}-{candidate_identity[:16]}.flac"
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                sf.write(
                    target,
                    np.asarray(audio, dtype=np.float32),
                    rate,
                    subtype="PCM_24",
                    format="FLAC",
                )
                candidates.append(
                    {
                        "id": unit_id,
                        "chapter": chapter["id"],
                        "candidate": name,
                        "text": text,
                        "phonemes": phonemes,
                        "voice": voice,
                        "speed": actual_speed,
                        "file": str(target.relative_to(project)),
                        "sha256": sha256(target),
                        "source_hash": source_hash,
                        "source_sentence_indexes": unit.get(
                            "source_sentence_indexes", []
                        ),
                        "context_strategy": unit.get(
                            "context_strategy", "complete_sentence"
                        ),
                        "contains_terse_dialogue": bool(
                            unit.get("contains_terse_dialogue", False)
                        ),
                    }
                )
    existing = (
        json.loads((paths["production"] / "candidates.json").read_text())
        if (paths["production"] / "candidates.json").exists()
        else {"candidates": []}
    )
    if failed_only:
        candidates = [
            row for row in existing["candidates"] if row["id"] not in failed
        ] + candidates
    report = {
        "version": 3,
        "offline": True,
        "sample_rate": SAMPLE_RATE,
        "candidate_policy": "bounded deterministic pace variants; retry adds two controlled pace alternatives; only verified candidates may be selected",
        "candidates": candidates,
    }
    write_json(paths["production"] / "candidates.json", report)
    write_json(
        paths["production"] / "generation.json", {"version": 2, "takes": candidates}
    )
    return report


def _package(
    project: Path, rows: list[dict[str, Any]], output: Path
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["chapter"]), []).append(row)
    outputs = []
    for chapter, takes in grouped.items():
        concat = project / "production" / f"{chapter}.ffconcat"
        concat.write_text(
            "ffconcat version 1.0\n"
            + "".join(f"file '../{row['file']}'\n" for row in takes)
        )
        files = []
        for suffix, codec, extra in (
            (".flac", "flac", []),
            (".m4a", "aac", ["-b:a", "256k"]),
            (".mp3", "libmp3lame", ["-b:a", "256k"]),
        ):
            target = output / f"{chapter}_Audiobook{suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat),
                    "-c:a",
                    codec,
                    *extra,
                    str(target),
                ],
                check=True,
            )
            files.append(
                {"file": str(target.relative_to(project)), "sha256": sha256(target)}
            )
        outputs.append({"chapter": chapter, "files": files})
    return outputs


def assemble(project: Path) -> dict[str, Any]:
    return stage(project, project_paths(project)["deliverables"], direct=True)


def stage(
    project: Path, output: Path | None = None, *, direct: bool = False
) -> dict[str, Any]:
    paths = project_paths(project)
    verification = json.loads((paths["production"] / "verification.json").read_text())
    if not verification.get("ok"):
        raise RuntimeError("Cannot package: verification is not successful")
    integrity = audit_candidate_selection(project, verification)
    if not integrity["ok"]:
        rules = ", ".join(str(row["rule"]) for row in integrity["errors"])
        raise RuntimeError(f"Cannot package: candidate selection integrity failed: {rules}")
    root = (output or project / "staging").resolve()
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    outputs = _package(project, list(verification["takes"]), root)
    report = {
        "version": 1,
        "state": "direct_release" if direct else "staged",
        "verification_sha256": sha256(paths["production"] / "verification.json"),
        "candidate_selection_integrity_sha256": sha256(
            paths["production"] / "candidate-selection-integrity.json"
        ),
        "outputs": outputs,
    }
    write_json(root / "stage-manifest.json", report)
    write_json(
        paths["production"]
        / ("release-manifest.json" if direct else "stage-manifest.json"),
        report,
    )
    return report


def promote(project: Path) -> dict[str, Any]:
    paths = project_paths(project)
    stage_root = project / "staging"
    manifest = json.loads((stage_root / "stage-manifest.json").read_text())
    verification = json.loads((paths["production"] / "verification.json").read_text())
    if not verification.get("ok") or manifest.get("verification_sha256") != sha256(
        paths["production"] / "verification.json"
    ):
        raise RuntimeError(
            "Cannot promote: staged batch is stale or verification failed"
        )
    replacement = project / "deliverables.next"
    shutil.rmtree(replacement, ignore_errors=True)
    shutil.copytree(stage_root, replacement)
    (replacement / "stage-manifest.json").unlink(missing_ok=True)
    shutil.rmtree(paths["deliverables"], ignore_errors=True)
    replacement.replace(paths["deliverables"])
    report = {**manifest, "state": "promoted"}
    write_json(paths["production"] / "release-manifest.json", report)
    return report
