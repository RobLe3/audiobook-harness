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
        "status",
    ):
        command = sub.add_parser(name)
        command.add_argument("project", type=Path)
        if name == "stage":
            command.add_argument("--output", type=Path)
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
    actions = {
        "analyze": lambda: analyze(project),
        "generate": lambda: generate(project, REPO),
        "retry": lambda: generate(project, REPO, failed_only=True),
        "verify": lambda: verify(project, REPO),
        "release": lambda: assemble(project),
        "stage": lambda: stage(project, args.output),
        "promote": lambda: promote(project),
    }
    emit(_run(project, args.command, actions[args.command]))


if __name__ == "__main__":
    main()
