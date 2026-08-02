from __future__ import annotations

import json
import gc
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf
from rapidfuzz.distance import Levenshtein

from . import __version__
from .measurements import build_quality_measurements
from .candidate_scheduler import build_candidate_strategy_ledger
from .effective_cue_state import build_effective_cue_state
from .project import load_project, normalized_words, project_paths, sha256, write_json
from .pronunciation import (
    asr_equivalences,
    audit_lexicon,
    load_reviewed_lexicon,
    reviewed_phrase_equivalence,
)
from .selection_integrity import audit_candidate_selection
from .advisory_quality import collect_advisory_scores
from .repair_analysis import build_repair_artifacts
from .quality_policy import classify_quality_report
from .quality_acoustics import acoustic_failures
from .asr_cache import evidence_key, load as load_asr_cache, save as save_asr_cache
from .performance import resolve_profile


ASR_DEVICE = "cpu"
PRIMARY_DECODE = {"fp16": False, "verbose": False, "word_timestamps": False}
SECONDARY_DECODE = {"fp16": False, "verbose": False, "word_timestamps": False}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cached_transcripts(
    whisper: Any,
    *,
    project: Path,
    candidates: list[dict[str, Any]],
    checkpoint: Path,
    decode: dict[str, object],
    cache: dict[str, Any],
    model_label: str = "asr",
    progress: Callable[[str, str, bool], None] | None = None,
) -> tuple[dict[str, str], int, int]:
    """Return local CPU transcripts, loading a model only when evidence misses."""
    model_sha256 = sha256(checkpoint)
    entries = cache["entries"]
    texts: dict[str, str] = {}
    pending: list[tuple[dict[str, Any], str, str]] = []
    hits = 0
    for take in candidates:
        relative = str(take["file"])
        audio_path = project / relative
        audio_sha256 = str(take.get("sha256") or sha256(audio_path))
        key = evidence_key(
            audio_sha256=audio_sha256,
            model_sha256=model_sha256,
            decode=decode,
            device=ASR_DEVICE,
        )
        cached = entries.get(key)
        if isinstance(cached, dict) and isinstance(cached.get("text"), str):
            texts[relative] = str(cached["text"])
            hits += 1
            if progress is not None:
                progress(model_label, relative, True)
        else:
            pending.append((take, audio_sha256, key))
    if not pending:
        return texts, hits, 0
    model = whisper.load_model(str(checkpoint), device=ASR_DEVICE)
    for take, audio_sha256, key in pending:
        relative = str(take["file"])
        result = model.transcribe(str(project / relative), **decode)
        text = str(result.get("text", "")).strip()
        texts[relative] = text
        entries[key] = {
            "audio_sha256": audio_sha256,
            "model_sha256": model_sha256,
            "decode": decode,
            "device": ASR_DEVICE,
            "text": text,
        }
        save_asr_cache(project / "production" / "asr-evidence-cache.json", cache)
        if progress is not None:
            progress(model_label, relative, False)
    misses = len(pending)
    del model
    gc.collect()
    return texts, hits, misses


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
    """Require complete, plausible word-tier evidence for every selected take."""
    failed: list[str] = []
    for take in takes:
        candidate = aligned / f"{take['id']}.json"
        if not candidate.is_file():
            failed.append(str(take["id"]))
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failed.append(str(take["id"]))
            continue
        entries: object = None
        if isinstance(payload, dict):
            tiers = payload.get("tiers")
            if isinstance(tiers, dict):
                words = tiers.get("words")
                entries = words.get("entries") if isinstance(words, dict) else words
            entries = entries if entries is not None else payload.get("words")
        elif isinstance(payload, list):
            entries = payload
        if not isinstance(entries, list) or not entries:
            failed.append(str(take["id"]))
            continue
        intervals: list[tuple[float, float, str]] = []
        for entry in entries:
            try:
                if isinstance(entry, dict):
                    begin = float(entry.get("begin", entry.get("start")))
                    end = float(entry.get("end", entry.get("stop")))
                    label = str(
                        entry.get("label", entry.get("text", entry.get("word", "")))
                    )
                elif isinstance(entry, list) and len(entry) >= 3:
                    begin, end, label = float(entry[0]), float(entry[1]), str(entry[2])
                else:
                    raise ValueError
            except (TypeError, ValueError):
                intervals = []
                break
            if label.strip() and label.casefold() not in {"<eps>", "sil", "sp"}:
                intervals.append((begin, end, label))
        observed = [
            word
            for _begin, _end, label in intervals
            for word in normalized_words(label)
        ]
        expected = normalized_words(str(take.get("text", "")))
        duration = float(take.get("duration_seconds", 0.0))
        invalid_intervals = any(
            begin < 0
            or end <= begin
            or end - begin > 1.5
            or (duration > 0 and end > duration + 0.1)
            or (index > 0 and begin < intervals[index - 1][1])
            or (index > 0 and begin - intervals[index - 1][1] > 2.0)
            for index, (begin, end, _label) in enumerate(intervals)
        )
        error = Levenshtein.distance(expected, observed) / max(1, len(expected))
        if not intervals or invalid_intervals or error > 0.01:
            failed.append(str(take["id"]))
    return not failed, failed


def _transient_alignment_failure(text: str) -> bool:
    """Retry only host-worker failures, never linguistic or evidence failures."""
    value = text.casefold()
    markers = (
        "resource_tracker",
        "semaphore",
        "multiprocessing",
        "broken pipe",
        "worker process",
        "worker startup",
        "cannot start new thread",
    )
    return any(marker in value for marker in markers)


def run_mfa_alignment(
    project: Path,
    repo: Path,
    takes: list[dict[str, Any]],
    *,
    performance_profile: str = "legacy",
) -> dict[str, Any]:
    """Align selected takes locally with isolated attempts and conservative fallback.

    An automatic profile may start with bounded MFA workers.  Only a recognised
    host-worker failure gets one clean serial retry; model, dictionary, corpus,
    and incomplete-evidence failures are still blocking.
    """
    paths = project_paths(project)
    config = load_project(project)
    profile = resolve_profile(performance_profile)
    mfa = _mfa_command(repo)
    report: dict[str, Any] = {
        "required": True,
        "available": bool(mfa),
        "ok": False,
        "takes": len(takes),
        "performance_profile": profile.as_dict(),
        "attempts": [],
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

    root = paths["production"] / "mfa"
    corpus = root / "corpus"
    canonical = root / "aligned"
    attempts_root = root / "attempts"
    shutil.rmtree(corpus, ignore_errors=True)
    corpus.mkdir(parents=True, exist_ok=True)
    attempts_root.mkdir(parents=True, exist_ok=True)
    for take in takes:
        source = project / str(take["file"])
        stem = corpus / str(take["id"])
        _ffmpeg_wav(source, stem.with_suffix(".wav"))
        stem.with_suffix(".lab").write_text(
            str(take["text"]).strip() + "\n", encoding="utf-8"
        )

    modes = [("serial", 1)]
    if profile.alignment_multiprocessing and profile.alignment_jobs > 1:
        modes = [("parallel", profile.alignment_jobs), ("serial-fallback", 1)]
    accepted: Path | None = None
    for attempt_index, (mode, jobs) in enumerate(modes, 1):
        attempt_root = attempts_root / f"attempt-{attempt_index:02d}-{mode}"
        runtime, aligned = attempt_root / "runtime", attempt_root / "aligned"
        shutil.rmtree(attempt_root, ignore_errors=True)
        runtime.mkdir(parents=True, exist_ok=True)
        command = [
            mfa,
            "align",
            "--clean",
            "--single_speaker",
            "--output_format",
            "json",
            "--temporary_directory",
            str(runtime),
        ]
        if jobs > 1:
            command.extend(["--num_jobs", str(jobs)])
        command.extend([str(corpus), dictionary, acoustic, str(aligned)])
        completed = subprocess.run(
            command, capture_output=True, text=True, env=_mfa_environment(repo)
        )
        complete, missing = (
            _alignment_complete(aligned, takes)
            if completed.returncode == 0
            else (False, [str(t["id"]) for t in takes])
        )
        output = f"{completed.stdout}\n{completed.stderr}"
        transient = completed.returncode != 0 and _transient_alignment_failure(output)
        report["attempts"].append(
            {
                "mode": mode,
                "jobs": jobs,
                "command": command,
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
                "missing_alignment": missing,
                "transient_worker_failure": transient,
            }
        )
        if completed.returncode == 0 and complete:
            accepted = aligned
            break
        if not (
            attempt_index == 1
            and mode == "parallel"
            and transient
            and profile.alignment_serial_fallback
        ):
            break
    final = report["attempts"][-1] if report["attempts"] else {}
    if accepted is not None:
        shutil.rmtree(canonical, ignore_errors=True)
        shutil.copytree(accepted, canonical)
    report.update(
        {
            "dictionary": dictionary,
            "acoustic_model": acoustic,
            "command": final.get("command", []),
            "returncode": final.get("returncode"),
            "stdout_tail": final.get("stdout_tail", ""),
            "stderr_tail": final.get("stderr_tail", ""),
            "aligned_directory": str(canonical.relative_to(project)),
            "missing_alignment": final.get("missing_alignment", []),
            "ok": accepted is not None,
        }
    )
    write_json(paths["production"] / "forced-alignment.json", report)
    return report


def _normalized_asr_with_evidence(
    text: str, equivalences: list[dict[str, str]]
) -> tuple[list[str], list[dict[str, str]]]:
    import re

    applied: list[dict[str, str]] = []
    for equivalence in equivalences:
        observed, expected = equivalence["observed"], equivalence["expected"]
        pattern = r"(?<!\w)" + re.escape(observed) + r"(?!\w)"
        text, substitutions = re.subn(
            pattern,
            expected,
            text,
            flags=re.IGNORECASE,
        )
        if substitutions:
            applied.extend([equivalence] * substitutions)
    return normalized_words(text), applied


def _normalized_asr(text: str, equivalences: list[dict[str, str]]) -> list[str]:
    """Compatibility helper for exact comparison tests and callers."""
    return _normalized_asr_with_evidence(text, equivalences)[0]


def _acoustic_checks(mono: np.ndarray, rate: int, words: int) -> list[str]:
    """Compatibility wrapper for callers of the historical quality module."""
    return acoustic_failures(mono, rate, words)


def _finalize_verification_integrity(
    project: Path, report: dict[str, Any]
) -> dict[str, Any]:
    report["candidate_selection_integrity"] = audit_candidate_selection(project, report)
    report["ok"] = bool(report["ok"] and report["candidate_selection_integrity"]["ok"])
    return report


def verify(
    project: Path, repo: Path, *, performance_profile: str = "legacy"
) -> dict[str, Any]:
    import whisper

    paths = project_paths(project)
    lexicon_report = audit_lexicon(project)
    candidates_path = paths["production"] / "candidates.json"
    candidates = json.loads(candidates_path.read_text())["candidates"]
    primary_path, secondary_path = (
        repo / ".tools/whisper/models/large-v3-turbo.pt",
        repo / ".tools/whisper/models/base.pt",
    )
    if not primary_path.exists() or not secondary_path.exists():
        raise FileNotFoundError(
            "Whisper primary/secondary models missing; run explicit model setup"
        )
    asr_cache_path = paths["production"] / "asr-evidence-cache.json"
    asr_progress_path = paths["production"] / "asr-progress.json"
    asr_cache = load_asr_cache(asr_cache_path)
    asr_completed = 0
    asr_cache_hits = 0
    asr_expected = len(candidates) * 2
    asr_started_at = _utc_now()

    def record_asr_progress(model: str, relative: str, cached: bool) -> None:
        nonlocal asr_completed, asr_cache_hits
        asr_completed += 1
        asr_cache_hits += int(cached)
        write_json(
            asr_progress_path,
            {
                "version": 2,
                "state": "running",
                "started_at": asr_started_at,
                "updated_at": _utc_now(),
                "completed_candidates": asr_completed,
                "expected_candidates": asr_expected,
                "cache_hits": asr_cache_hits,
                "active_model": model,
                "active_file": relative,
                "last_completed_file": relative,
                "advisory_only": True,
            },
        )

    write_json(
        asr_progress_path,
        {
            "version": 2,
            "state": "running",
            "started_at": asr_started_at,
            "updated_at": _utc_now(),
            "completed_candidates": 0,
            "expected_candidates": asr_expected,
            "cache_hits": 0,
            "active_model": "loading",
            "active_file": None,
            "last_completed_file": None,
            "advisory_only": True,
        },
    )
    try:
        primary_texts, primary_hits, primary_misses = _cached_transcripts(
            whisper,
            project=project,
            candidates=candidates,
            checkpoint=primary_path,
            decode=PRIMARY_DECODE,
            cache=asr_cache,
            model_label="large-v3-turbo",
            progress=record_asr_progress,
        )
        secondary_texts, secondary_hits, secondary_misses = _cached_transcripts(
            whisper,
            project=project,
            candidates=candidates,
            checkpoint=secondary_path,
            decode=SECONDARY_DECODE,
            cache=asr_cache,
            model_label="base",
            progress=record_asr_progress,
        )
    except BaseException as error:
        write_json(
            asr_progress_path,
            {
                "version": 2,
                "state": "failed",
                "started_at": asr_started_at,
                "updated_at": _utc_now(),
                "completed_at": _utc_now(),
                "completed_candidates": asr_completed,
                "expected_candidates": asr_expected,
                "cache_hits": asr_cache_hits,
                "active_model": None,
                "active_file": None,
                "error": {"type": type(error).__name__, "message": str(error)},
                "advisory_only": True,
            },
        )
        raise
    write_json(
        asr_progress_path,
        {
            "version": 2,
            "state": "complete",
            "started_at": asr_started_at,
            "updated_at": _utc_now(),
            "completed_at": _utc_now(),
            "completed_candidates": asr_completed,
            "expected_candidates": asr_expected,
            "cache_hits": asr_cache_hits,
            "active_model": None,
            "active_file": None,
            "last_completed_file": None,
            "advisory_only": True,
        },
    )
    save_asr_cache(asr_cache_path, asr_cache)
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
    candidate_evidence: dict[str, list[dict[str, Any]]] = {}
    for unit_id, options in grouped.items():
        attempts = []
        for take in options:
            audio_path = project / str(take["file"])
            audio, rate = sf.read(audio_path, dtype="float32")
            mono = np.mean(audio, axis=1) if getattr(audio, "ndim", 1) > 1 else audio
            expected = normalized_words(str(take["text"]))
            first, first_equivalences = _normalized_asr_with_evidence(
                primary_texts[str(take["file"])], equivalents
            )
            second, second_equivalences = _normalized_asr_with_evidence(
                secondary_texts[str(take["file"])], equivalents
            )
            first_error = Levenshtein.distance(expected, first) / max(1, len(expected))
            second_error = Levenshtein.distance(expected, second) / max(
                1, len(expected)
            )
            phrase_evidence = (
                reviewed_phrase_equivalence(
                    expected=expected,
                    primary=first,
                    secondary=second,
                    lexicon=lexicon,
                    candidate=take,
                )
                if first_error > 0.01 or second_error > 0.01
                else None
            )
            acoustic = _acoustic_checks(mono, rate, len(expected))
            attempt = {
                **take,
                "primary_text": " ".join(first),
                "secondary_text": " ".join(second),
                "primary_asr_equivalences": first_equivalences,
                "secondary_asr_equivalences": second_equivalences,
                "primary_wer": round(first_error, 4),
                "secondary_wer": round(second_error, 4),
                "protected_phrase_evidence": phrase_evidence,
                "duration_seconds": len(mono) / rate,
                "acoustic_failures": acoustic,
                "ok": (
                    (first_error <= 0.01 and second_error <= 0.01)
                    or phrase_evidence is not None
                )
                and not acoustic,
            }
            seconds_per_word = attempt["duration_seconds"] / max(1, len(expected))
            attempt["quality_vector"] = {
                "text_error": round(first_error + second_error, 6),
                "pace_deviation": round(abs(seconds_per_word - 0.38), 6),
                "speed_deviation": round(abs(float(take["speed"]) - 0.95), 6),
            }
            attempt["quality_score"] = round(
                (first_error + second_error) * 100
                + abs(seconds_per_word - 0.38) * 2
                + abs(float(take["speed"]) - 0.95),
                6,
            )
            attempts.append(attempt)
        candidate_evidence[unit_id] = attempts
        passing = [row for row in attempts if row["ok"]]
        passing.sort(
            key=lambda row: (
                float(row["quality_score"]),
                abs(float(row["speed"]) - 0.95),
                str(row["candidate"]),
            )
        )
        if passing:
            selected.append(
                {
                    **passing[0],
                    "selection_reason": "best verified quality vector; deterministic speed and candidate tie-break",
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
        run_mfa_alignment(
            project, repo, selected, performance_profile=performance_profile
        )
        if selected
        else {"ok": False, "failure": "no verified takes"}
    )
    report = {
        "version": 5,
        "audiobook_harness_version": __version__,
        "ok": lexicon_report["ok"] and not failures and alignment["ok"],
        "candidate_policy": "dual ASR, acoustic checks, alignment, and hash-bound selection",
        "candidate_manifest_sha256": sha256(candidates_path),
        "lexicon": lexicon_report,
        "forced_alignment": alignment,
        "takes": selected,
        "failures": failures,
        "candidate_evidence": candidate_evidence,
        "asr_equivalences": len(equivalents),
        "asr_performance": {
            "device": ASR_DEVICE,
            "word_timestamps": False,
            "cache": str(asr_cache_path.relative_to(project)),
            "primary_cache_hits": primary_hits,
            "secondary_cache_hits": secondary_hits,
            "primary_new_decodes": primary_misses,
            "secondary_new_decodes": secondary_misses,
        },
    }
    report["quality_policy"] = classify_quality_report(report)
    write_json(paths["production"] / "verification.json", report)
    candidate_plan = json.loads(
        (paths["production"] / "candidate-plan.json").read_text(encoding="utf-8")
    )
    write_json(
        paths["production"] / "candidate-strategy-ledger.json",
        build_candidate_strategy_ledger(
            candidate_plan,
            candidates,
            failures=failures,
        ),
    )
    _finalize_verification_integrity(project, report)
    write_json(paths["production"] / "verification.json", report)
    write_json(
        paths["production"] / "pronunciation-audit.json",
        {"version": 1, **lexicon_report},
    )
    duration_rows = [
        {
            "unit": row["id"],
            "duration_seconds": row["duration_seconds"],
            "words": len(normalized_words(str(row["text"]))),
            "seconds_per_word": row["duration_seconds"]
            / max(1, len(normalized_words(str(row["text"])))),
        }
        for row in selected
    ]
    write_json(
        paths["production"] / "phoneme-duration-audit.json",
        {
            "version": 1,
            "units": duration_rows,
            "ok": all(row["seconds_per_word"] <= 1.6 for row in duration_rows),
        },
    )
    write_json(
        paths["production"] / "pause-economy-lint.json",
        {
            "version": 1,
            "units": [
                {
                    "unit": row["id"],
                    "unexpected_silence": "unexpected_silence"
                    in row.get("acoustic_failures", []),
                }
                for row in selected
            ],
            "ok": all(
                "unexpected_silence" not in row.get("acoustic_failures", [])
                for row in selected
            ),
        },
    )
    selected_ids = {str(row["id"]) for row in selected}
    planned_energy = _planned_units(paths["production"] / "speaker-energy-map.json")
    planned_prosody = _planned_units(paths["production"] / "discourse-prosody-map.json")
    write_json(
        paths["production"] / "energy-lint.json",
        {
            "version": 1,
            "planned_units": sorted(planned_energy),
            "selected_units": sorted(selected_ids),
            "ok": bool(selected_ids) and selected_ids <= planned_energy,
        },
    )
    write_json(
        paths["production"] / "expressive-realization.json",
        {
            "version": 1,
            "measurement_scope": "delivery_plan_coverage",
            "planned_units": sorted(planned_prosody),
            "selected_units": sorted(selected_ids),
            "ok": bool(selected_ids) and selected_ids <= planned_prosody,
        },
    )
    build_quality_measurements(project)
    collect_advisory_scores(project)
    build_repair_artifacts(project, report)
    build_effective_cue_state(project, report)
    return report


def _planned_units(path: Path) -> set[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {
        str(row.get("unit", row.get("id")))
        for row in value.get("units", [])
        if isinstance(row, dict) and (row.get("unit") or row.get("id"))
    }
