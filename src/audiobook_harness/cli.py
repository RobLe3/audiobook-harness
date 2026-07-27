from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from . import __version__
from .analysis import analyze
from .project import scaffold
from .performance import resolve_profile
from .quality import verify
from .resilience import (
    append_terminal_failure,
    decide_candidate_retry,
    production_input_identity,
    terminal_signatures,
)
from .status import render_status, watch, write_run_status
from .tts import assemble, generate, promote, stage

REPO = Path(__file__).resolve().parents[2]


def emit(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def doctor(repo: Path) -> dict[str, object]:
    required = {
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "espeak-ng": shutil.which("espeak-ng") or shutil.which("espeak"),
        "mfa": shutil.which("mfa") or str(repo / ".tools/mfa/bin/mfa"),
    }
    checks = {
        name: bool(
            path
            and (not isinstance(path, str) or Path(path).exists() or shutil.which(path))
        )
        for name, path in required.items()
    }
    checks.update(
        {
            "kokoro_model": (repo / ".tools/kokoro/models/kokoro-v1.0.onnx").is_file(),
            "kokoro_voices": (repo / ".tools/kokoro/models/voices-v1.0.bin").is_file(),
            "whisper_models": all(
                (repo / ".tools/whisper/models" / name).is_file()
                for name in ("large-v3-turbo.pt", "base.pt")
            ),
        }
    )
    return {
        "version": __version__,
        "repo": str(repo),
        "offline_default": True,
        "checks": checks,
        "ok": all(checks.values()),
    }


def _run(project: Path, name: str, action):
    workflow = ("analyze", "generate", "verify", "stage", "promote")
    active_index = workflow.index(name) if name in workflow else 0
    steps = [
        {
            "name": value,
            "state": "complete"
            if index < active_index
            else "running"
            if index == active_index
            else "queued",
        }
        for index, value in enumerate(workflow)
    ]
    write_run_status(project, state="running", phase=name, steps=steps)
    try:
        result = action()
    except BaseException as error:
        write_run_status(
            project,
            state="failed",
            phase=name,
            steps=steps,
            error={"type": type(error).__name__, "message": str(error)},
        )
        raise
    steps = [
        {"name": value, "state": "complete" if index <= active_index else "queued"}
        for index, value in enumerate(workflow)
    ]
    write_run_status(project, state="complete", phase=name, steps=steps, error=None)
    return result


PRODUCTION_STEPS = (
    "analyze manuscript and pronunciation requirements",
    "generate bounded deterministic candidates",
    "verify with dual ASR, acoustics, and forced alignment",
    "repair only failed candidate units",
    "stage hash-bound verified deliverables",
)


def _production_progress(
    active: int, *, failed: bool = False
) -> list[dict[str, object]]:
    return [
        {
            "name": name,
            "state": (
                "complete"
                if index < active
                else "failed"
                if failed and index == active
                else "running"
                if index == active
                else "queued"
            ),
        }
        for index, name in enumerate(PRODUCTION_STEPS)
    ]


def produce(
    project: Path,
    *,
    output: Path | None,
    performance_profile: str,
    maximum_candidate_retries: int,
) -> dict[str, object]:
    """Run a staged local production with one evidence-bound repair loop."""
    production = project / "production"
    ledger = production / "recovery-ledger.jsonl"
    input_identity = production_input_identity(project, REPO)
    previous_signatures = terminal_signatures(ledger)
    retries = 0
    phase_index = 0

    def progress(index: int, phase: str) -> None:
        write_run_status(
            project,
            state="running",
            phase=phase,
            steps=_production_progress(index),
            input_identity=input_identity,
            candidate_retries=retries,
            maximum_candidate_retries=maximum_candidate_retries,
            error=None,
        )

    try:
        phase_index = 0
        progress(0, PRODUCTION_STEPS[0])
        analysis = analyze(project)
        phase_index = 1
        progress(1, PRODUCTION_STEPS[1])
        generation = generate(project, REPO)
        phase_index = 2
        progress(2, PRODUCTION_STEPS[2])
        verification = verify(
            project,
            REPO,
            performance_profile=performance_profile,
        )
        failures = [str(item) for item in verification.get("failures", [])]
        if not verification.get("ok"):
            phase_index = 3
            progress(phase_index, PRODUCTION_STEPS[phase_index])
            decision = decide_candidate_retry(
                failures,
                input_identity=input_identity,
                previous_signatures=previous_signatures,
                remaining_budget=maximum_candidate_retries - retries,
            )
            if decision.get("retry") is True:
                retries += 1
                generate(project, REPO, failed_only=True)
                progress(2, f"{PRODUCTION_STEPS[2]} after bounded repair")
                verification = verify(
                    project,
                    REPO,
                    performance_profile=performance_profile,
                )
                failures = [str(item) for item in verification.get("failures", [])]
            if not verification.get("ok"):
                terminal = decide_candidate_retry(
                    failures,
                    input_identity=input_identity,
                    previous_signatures=previous_signatures,
                    remaining_budget=maximum_candidate_retries - retries,
                )
                if failures and str(terminal["signature"]) not in previous_signatures:
                    append_terminal_failure(
                        ledger,
                        signature=str(terminal["signature"]),
                        input_identity=input_identity,
                        failures=failures,
                        reason=str(terminal["reason"]),
                    )
                raise RuntimeError(
                    "Verification remains blocked; inspect production/verification.json. "
                    f"Automatic recovery stopped: {terminal['reason']}."
                )
        phase_index = 4
        progress(phase_index, PRODUCTION_STEPS[phase_index])
        staged = stage(project, output)
    except BaseException as error:
        write_run_status(
            project,
            state="failed",
            phase=PRODUCTION_STEPS[phase_index],
            steps=_production_progress(phase_index, failed=True),
            input_identity=input_identity,
            candidate_retries=retries,
            maximum_candidate_retries=maximum_candidate_retries,
            error={"type": type(error).__name__, "message": str(error)},
        )
        raise
    write_run_status(
        project,
        state="complete",
        phase="verified deliverables staged",
        steps=[{"name": name, "state": "complete"} for name in PRODUCTION_STEPS],
        input_identity=input_identity,
        candidate_retries=retries,
        maximum_candidate_retries=maximum_candidate_retries,
        error=None,
    )
    return {
        "ok": True,
        "analysis": analysis,
        "generation": generation,
        "verification": verification,
        "stage": staged,
        "candidate_retries": retries,
        "input_identity": input_identity,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="audiobook-harness")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    performance = sub.add_parser("performance")
    performance.add_argument("--profile", choices=("legacy", "auto"), default="legacy")
    new = sub.add_parser("new-project")
    new.add_argument("directory", type=Path)
    for name in (
        "analyze",
        "generate",
        "retry",
        "verify",
        "release",
        "stage",
        "promote",
        "produce",
        "status",
    ):
        command = sub.add_parser(name)
        command.add_argument("project", type=Path)
        if name == "stage":
            command.add_argument("--output", type=Path)
        if name == "verify":
            command.add_argument(
                "--performance-profile", choices=("legacy", "auto"), default="legacy"
            )
        if name == "produce":
            command.add_argument("--output", type=Path)
            command.add_argument(
                "--performance-profile", choices=("legacy", "auto"), default="auto"
            )
            command.add_argument(
                "--max-candidate-retries", type=int, choices=(0, 1), default=1
            )
        if name == "status":
            command.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    if args.command == "doctor":
        emit(doctor(REPO))
        return
    if args.command == "performance":
        emit({"ok": True, "profile": resolve_profile(args.profile).as_dict()})
        return
    if args.command == "new-project":
        scaffold(args.directory.resolve(), REPO / "templates/project")
        emit({"ok": True, "project": str(args.directory.resolve())})
        return
    project = args.project.resolve()
    if args.command == "status":
        if args.watch:
            watch(project)
        else:
            print(render_status(project))
        return
    if args.command == "produce":
        emit(
            produce(
                project,
                output=args.output,
                performance_profile=args.performance_profile,
                maximum_candidate_retries=args.max_candidate_retries,
            )
        )
        return
    actions = {
        "analyze": lambda: analyze(project),
        "generate": lambda: generate(project, REPO),
        "retry": lambda: generate(project, REPO, failed_only=True),
        "verify": lambda: verify(
            project, REPO, performance_profile=args.performance_profile
        ),
        "release": lambda: assemble(project),
        "stage": lambda: stage(project, args.output),
        "promote": lambda: promote(project),
    }
    emit(_run(project, args.command, actions[args.command]))


if __name__ == "__main__":
    main()
