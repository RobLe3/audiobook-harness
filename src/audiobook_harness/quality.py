from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from rapidfuzz.distance import Levenshtein

from .project import load_project, normalized_words, project_paths, sha256, write_json
from .pronunciation import asr_equivalences, audit_lexicon, load_reviewed_lexicon


def _transcribe(model: Any, audio: Path) -> str:
    result = model.transcribe(str(audio), fp16=False, verbose=False)
    return str(result.get("text", "")).strip()


def _mfa_command(repo: Path) -> str | None:
    bundled = repo / ".tools/mfa/bin/mfa"
    if bundled.is_file():
        return str(bundled)
    return shutil.which("mfa")


def _mfa_profile(config: dict[str, Any]) -> tuple[str, str]:
    """Return explicitly configured local MFA dictionary/acoustic identifiers.

    The public starter is English-only. Other languages are never guessed or
    downloaded by a verification run; users must install and name their local
    MFA models explicitly in project.yaml.
    """
    language = str(config.get("language", "en-gb"))
    mfa = config.get("mfa", {})
    if not isinstance(mfa, dict):
        raise ValueError("project.yaml mfa must be a mapping")
    if language.startswith("en"):
        return str(mfa.get("dictionary", "english_us_arpa")), str(
            mfa.get("acoustic_model", "english_us_arpa")
        )
    dictionary, acoustic = mfa.get("dictionary"), mfa.get("acoustic_model")
    if not dictionary or not acoustic:
        raise ValueError(
            "Non-English forced alignment requires mfa.dictionary and mfa.acoustic_model; "
            "install those models explicitly during setup."
        )
    return str(dictionary), str(acoustic)


def _mfa_environment(repo: Path) -> dict[str, str]:
    """Keep MFA models local to this repository for both setup and verification."""
    import os

    return {**os.environ, "MFA_ROOT_DIR": str(repo / ".tools" / "mfa-root")}


def _ffmpeg_wav(source: Path, destination: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for forced alignment")
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(destination),
        ],
        check=True,
    )


def _alignment_complete(
    aligned: Path, takes: list[dict[str, Any]]
) -> tuple[bool, list[str]]:
    """A successful MFA exit alone is insufficient: every take needs JSON evidence."""
    missing: list[str] = []
    for take in takes:
        candidate = aligned / f"{take['id']}.json"
        if not candidate.is_file():
            missing.append(str(take["id"]))
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            missing.append(str(take["id"]))
            continue
        if not isinstance(payload, (dict, list)):
            missing.append(str(take["id"]))
    return not missing, missing


def run_mfa_alignment(
    project: Path, repo: Path, takes: list[dict[str, Any]]
) -> dict[str, Any]:
    """Run local MFA against one generated sentence take per corpus entry.

    This creates private, reproducible evidence only. It never downloads a
    dictionary/model, calls a network service, or mutates global MFA state.
    """
    paths = project_paths(project)
    config = load_project(project)
    mfa = _mfa_command(repo)
    report: dict[str, Any] = {
        "required": True,
        "available": bool(mfa),
        "ok": False,
        "takes": len(takes),
    }
    if not mfa:
        report["failure"] = "mfa executable is missing"
        write_json(paths["production"] / "forced-alignment.json", report)
        return report
    try:
        dictionary, acoustic = _mfa_profile(config)
    except ValueError as exc:
        report["failure"] = str(exc)
        write_json(paths["production"] / "forced-alignment.json", report)
        return report

    corpus = paths["production"] / "mfa" / "corpus"
    aligned = paths["production"] / "mfa" / "aligned"
    runtime = paths["production"] / "mfa" / "runtime"
    shutil.rmtree(corpus, ignore_errors=True)
    shutil.rmtree(aligned, ignore_errors=True)
    corpus.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    for take in takes:
        source = project / str(take["file"])
        stem = corpus / str(take["id"])
        _ffmpeg_wav(source, stem.with_suffix(".wav"))
        stem.with_suffix(".lab").write_text(
            str(take["text"]).strip() + "\n", encoding="utf-8"
        )

    command = [
        mfa,
        "align",
        "--clean",
        "--single_speaker",
        "--output_format",
        "json",
        "--temporary_directory",
        str(runtime),
        str(corpus),
        dictionary,
        acoustic,
        str(aligned),
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, env=_mfa_environment(repo)
    )
    complete, missing = (
        _alignment_complete(aligned, takes)
        if completed.returncode == 0
        else (False, [str(t["id"]) for t in takes])
    )
    report.update(
        {
            "dictionary": dictionary,
            "acoustic_model": acoustic,
            "command": command,
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
            "aligned_directory": str(aligned.relative_to(project)),
            "missing_alignment": missing,
            "ok": completed.returncode == 0 and complete,
        }
    )
    write_json(paths["production"] / "forced-alignment.json", report)
    return report


def _normalized_asr(text: str, equivalences: list[tuple[str, str]]) -> list[str]:
    import re

    for observed, expected in equivalences:
        text = re.sub(
            r"(?<!\w)" + re.escape(observed) + r"(?!\w)",
            expected,
            text,
            flags=re.IGNORECASE,
        )
    return normalized_words(text)


def _acoustic_checks(mono: np.ndarray, rate: int, words: int) -> list[str]:
    failures: list[str] = []
    if not len(mono):
        return ["empty_audio"]
    if float(np.max(np.abs(mono))) >= 0.995:
        failures.append("clipping")
    duration = len(mono) / max(1, rate)
    if duration < 0.15 or duration > max(2.0, words * 1.25):
        failures.append("abnormal_duration")
    if words and duration / words > 1.6:
        failures.append("long_word_duration_risk")
    frame = max(1, int(rate * 0.02))
    usable = mono[: len(mono) - len(mono) % frame]
    if len(usable):
        quiet = np.sqrt(
            np.mean(usable.reshape(-1, frame) ** 2, axis=1) + 1e-12
        ) < 10 ** (-55 / 20)
        longest = current = 0
        for value in quiet:
            current = current + 1 if value else 0
            longest = max(longest, current)
        if longest * frame / rate > 2.0:
            failures.append("unexpected_silence")
    return failures


def verify(project: Path, repo: Path) -> dict[str, Any]:
    import whisper

    paths = project_paths(project)
    lexicon_report = audit_lexicon(project)
    candidates = json.loads((paths["production"] / "candidates.json").read_text())[
        "candidates"
    ]
    primary_path, secondary_path = (
        repo / ".tools/whisper/models/large-v3-turbo.pt",
        repo / ".tools/whisper/models/base.pt",
    )
    if not primary_path.exists() or not secondary_path.exists():
        raise FileNotFoundError(
            "Whisper primary/secondary models missing; run explicit model setup"
        )
    primary, secondary = (
        whisper.load_model(str(primary_path)),
        whisper.load_model(str(secondary_path)),
    )
    lexicon = load_reviewed_lexicon(project)
    equivalents = asr_equivalences(lexicon)
    old = (
        json.loads((paths["production"] / "verification.json").read_text())
        if (paths["production"] / "verification.json").exists()
        else {}
    )
    old_by_id = {str(row["id"]): row for row in old.get("takes", []) if row.get("ok")}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        grouped.setdefault(str(row["id"]), []).append(row)
    selected: list[dict[str, Any]] = []
    failures: list[str] = []
    for unit_id, options in grouped.items():
        attempts = []
        for take in options:
            audio_path = project / str(take["file"])
            audio, rate = sf.read(audio_path, dtype="float32")
            mono = np.mean(audio, axis=1) if getattr(audio, "ndim", 1) > 1 else audio
            expected = normalized_words(str(take["text"]))
            first = _normalized_asr(_transcribe(primary, audio_path), equivalents)
            second = _normalized_asr(_transcribe(secondary, audio_path), equivalents)
            first_error = Levenshtein.distance(expected, first) / max(1, len(expected))
            second_error = Levenshtein.distance(expected, second) / max(
                1, len(expected)
            )
            acoustic = _acoustic_checks(mono, rate, len(expected))
            attempt = {
                **take,
                "primary_text": " ".join(first),
                "secondary_text": " ".join(second),
                "primary_wer": round(first_error, 4),
                "secondary_wer": round(second_error, 4),
                "duration_seconds": len(mono) / rate,
                "acoustic_failures": acoustic,
                "ok": first_error <= 0.01 and second_error <= 0.01 and not acoustic,
            }
            attempts.append(attempt)
        passing = [row for row in attempts if row["ok"]]
        passing.sort(
            key=lambda row: (abs(float(row["speed"]) - 0.95), str(row["candidate"]))
        )
        if passing:
            selected.append(
                {
                    **passing[0],
                    "selection_reason": "closest verified deterministic candidate",
                }
            )
            continue
        previous = old_by_id.get(unit_id)
        if (
            previous
            and any(
                str(row.get("source_hash")) == str(previous.get("source_hash"))
                for row in options
            )
            and (project / str(previous["file"])).is_file()
            and sha256(project / str(previous["file"])) == previous.get("sha256")
        ):
            selected.append(
                {
                    **previous,
                    "retained_predecessor": True,
                    "selection_reason": "ambiguous replacement rejected; retained verified predecessor",
                }
            )
            continue
        failures.append(unit_id)
    alignment = (
        run_mfa_alignment(project, repo, selected)
        if selected
        else {"ok": False, "failure": "no verified takes"}
    )
    report = {
        "version": 3,
        "ok": lexicon_report["ok"] and not failures and alignment["ok"],
        "candidate_policy": "dual ASR, acoustic checks, alignment, and hash-bound selection",
        "lexicon": lexicon_report,
        "forced_alignment": alignment,
        "takes": selected,
        "failures": failures,
        "asr_phrase_equivalences": len(equivalents),
    }
    write_json(paths["production"] / "verification.json", report)
    return report
