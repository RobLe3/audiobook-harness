from __future__ import annotations

import json
import shutil
import subprocess
import hashlib
import importlib.metadata
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .project import load_project, project_paths, sha256, write_json
from .pronunciation import apply_to_phonemes, audit_lexicon, load_reviewed_lexicon
from .selection_integrity import audit_candidate_selection
from .context_protocol import protocol_for_unit

SAMPLE_RATE = 24_000
VARIANTS = (("baseline", 0.0), ("slower", -0.01), ("faster", 0.01))
RETRY_VARIANTS = VARIANTS + (("retry_slower", -0.02), ("retry_faster", 0.02))
SYNTHESIS_CONTRACT_VERSION = 2
STAGE_MARKER = ".audiobook-harness-stage.json"


def model_paths(repo: Path) -> tuple[Path, Path]:
    root = repo / ".tools/kokoro/models"
    return root / "kokoro-v1.0.onnx", root / "voices-v1.0.bin"


def _source_hash(unit: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                **{
                k: unit.get(k)
                for k in ("id", "text", "source_sentence_indexes", "context_strategy")
                },
                "context_protocol": protocol_for_unit(unit),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _candidate_identity(
    *,
    name: str,
    phonemes: str,
    source_hash: str,
    context_protocol: dict[str, Any],
    voice: str,
    speed: float,
    engine_identity: dict[str, Any],
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "candidate": name,
                "phonemes": phonemes,
                "source_hash": source_hash,
                "context_protocol": context_protocol,
                "voice": voice,
                "speed": speed,
                **engine_identity,
            },
            sort_keys=True,
        ).encode("utf-8")
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
    engine_identity = {
        "model_sha256": sha256(model),
        "voices_sha256": sha256(voices),
        "kokoro_onnx_version": importlib.metadata.version("kokoro-onnx"),
        "synthesis_contract_version": SYNTHESIS_CONTRACT_VERSION,
    }
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
            context_protocol = protocol_for_unit(unit)
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
                candidate_identity = _candidate_identity(
                    name=name,
                    phonemes=phonemes,
                    source_hash=source_hash,
                    context_protocol=context_protocol,
                    voice=voice,
                    speed=actual_speed,
                    engine_identity=engine_identity,
                )
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
                        **engine_identity,
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
        "version": 4,
        "offline": True,
        "sample_rate": SAMPLE_RATE,
        "candidate_policy": "bounded deterministic pace variants; retry adds two controlled pace alternatives; contextual terse dialogue is bound to a versioned adjacent-manuscript performance protocol; only verified candidates may be selected",
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
                {
                    "file": str(target.relative_to(output)),
                    "sha256": sha256(target),
                    "bytes": target.stat().st_size,
                }
            )
        outputs.append({"chapter": chapter, "files": files})
    return outputs


def _prepare_stage_directory(project: Path, output: Path | None) -> Path:
    requested = output or project / "staging"
    if requested.is_symlink():
        raise RuntimeError("Cannot stage into a symbolic link")
    root = requested.resolve()
    project = project.resolve()
    protected = {
        Path(root.anchor),
        Path.home().resolve(),
        project,
        *(path.resolve() for path in project_paths(project).values() if path != project_paths(project)["lexicon"]),
    }
    if root in protected or project.is_relative_to(root):
        raise RuntimeError(f"Unsafe staging output directory: {root}")
    marker = root / STAGE_MARKER
    if root.exists():
        children = list(root.iterdir())
        if children:
            try:
                ownership = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise RuntimeError(
                    "Refusing to replace a non-empty directory not owned by Audiobook Harness"
                ) from None
            if ownership.get("project") != str(project):
                raise RuntimeError("Staging directory belongs to a different project")
            shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    write_json(
        marker,
        {"version": 1, "owner": "audiobook-harness", "project": str(project)},
    )
    return root


def stage(project: Path, output: Path | None = None) -> dict[str, Any]:
    paths = project_paths(project)
    verification = json.loads((paths["production"] / "verification.json").read_text())
    if not verification.get("ok"):
        raise RuntimeError("Cannot package: verification is not successful")
    integrity = audit_candidate_selection(project, verification)
    if not integrity["ok"]:
        rules = ", ".join(str(row["rule"]) for row in integrity["errors"])
        raise RuntimeError(f"Cannot package: candidate selection integrity failed: {rules}")
    root = _prepare_stage_directory(project, output)
    outputs = _package(project, list(verification["takes"]), root)
    expected_files = sorted(
        str(row["file"]) for chapter in outputs for row in chapter["files"]
    )
    report = {
        "version": 2,
        "state": "staged",
        "verification_sha256": sha256(paths["production"] / "verification.json"),
        "candidate_selection_integrity_sha256": sha256(
            paths["production"] / "candidate-selection-integrity.json"
        ),
        "outputs": outputs,
        "expected_files": expected_files,
    }
    write_json(root / "stage-manifest.json", report)
    write_json(
        paths["production"] / "stage-manifest.json", report,
    )
    return report


def stage_manifest_is_valid(
    project: Path, stage_directory: Path | None = None
) -> bool:
    paths = project_paths(project)
    stage_root = (stage_directory or project / "staging").resolve()
    try:
        manifest = json.loads(
            (stage_root / "stage-manifest.json").read_text(encoding="utf-8")
        )
        production_manifest = json.loads(
            (paths["production"] / "stage-manifest.json").read_text(encoding="utf-8")
        )
        verification_hash = sha256(paths["production"] / "verification.json")
        integrity_hash = sha256(
            paths["production"] / "candidate-selection-integrity.json"
        )
    except (OSError, json.JSONDecodeError):
        return False
    if (
        manifest != production_manifest
        or manifest.get("verification_sha256") != verification_hash
        or manifest.get("candidate_selection_integrity_sha256") != integrity_hash
    ):
        return False
    expected = manifest.get("expected_files")
    if not isinstance(expected, list) or not expected:
        return False
    expected_names = sorted(str(value) for value in expected)
    actual = sorted(
        str(path.relative_to(stage_root))
        for path in stage_root.rglob("*")
        if path.is_file() and path.name not in {STAGE_MARKER, "stage-manifest.json"}
    )
    if actual != expected_names:
        return False
    rows = {
        str(row.get("file")): row
        for chapter in manifest.get("outputs", [])
        for row in chapter.get("files", [])
    }
    return set(rows) == set(expected_names) and all(
        (stage_root / name).is_file()
        and (stage_root / name).stat().st_size == rows[name].get("bytes")
        and sha256(stage_root / name) == rows[name].get("sha256")
        for name in expected_names
    )


def promote(project: Path, stage_directory: Path | None = None) -> dict[str, Any]:
    paths = project_paths(project)
    stage_root = (stage_directory or project / "staging").resolve()
    manifest = json.loads((stage_root / "stage-manifest.json").read_text())
    verification = json.loads((paths["production"] / "verification.json").read_text())
    if not verification.get("ok") or manifest.get("verification_sha256") != sha256(
        paths["production"] / "verification.json"
    ):
        raise RuntimeError(
            "Cannot promote: staged batch is stale or verification failed"
        )
    integrity = audit_candidate_selection(project, verification)
    integrity_path = paths["production"] / "candidate-selection-integrity.json"
    if (
        not integrity["ok"]
        or manifest.get("candidate_selection_integrity_sha256") != sha256(integrity_path)
    ):
        raise RuntimeError("Cannot promote: candidate-selection integrity changed")
    if not stage_manifest_is_valid(project, stage_root):
        raise RuntimeError("Cannot promote: staged file set or media hashes changed")
    expected = manifest["expected_files"]
    rows = {
        str(row["file"]): row
        for chapter in manifest.get("outputs", [])
        for row in chapter.get("files", [])
    }
    for relative in expected:
        path = stage_root / str(relative)
        row = rows.get(str(relative), {})
        if (
            not path.is_file()
            or path.stat().st_size != row.get("bytes")
            or sha256(path) != row.get("sha256")
        ):
            raise RuntimeError(f"Cannot promote: staged media changed: {relative}")
    replacement = project / "deliverables.next"
    shutil.rmtree(replacement, ignore_errors=True)
    replacement.mkdir(parents=True)
    for relative in expected:
        source = stage_root / str(relative)
        target = replacement / str(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha256(target) != rows[str(relative)]["sha256"]:
            raise RuntimeError(f"Cannot promote: copied media hash mismatch: {relative}")
    shutil.rmtree(paths["deliverables"], ignore_errors=True)
    replacement.replace(paths["deliverables"])
    report = {**manifest, "state": "promoted", "promoted_files": expected}
    write_json(paths["deliverables"] / "promotion-receipt.json", report)
    write_json(paths["production"] / "release-manifest.json", report)
    return report
