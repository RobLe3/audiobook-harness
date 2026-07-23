from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from . import __version__
from .analysis import analyze
from .project import scaffold
from .quality import verify
from .tts import assemble, generate

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
    kokoro = repo / ".tools/kokoro/models/kokoro-v1.0.onnx"
    voices = repo / ".tools/kokoro/models/voices-v1.0.bin"
    whisper = [
        repo / ".tools/whisper/models/large-v3-turbo.pt",
        repo / ".tools/whisper/models/base.pt",
    ]
    checks = {
        name: bool(
            path
            and (not isinstance(path, str) or Path(path).exists() or shutil.which(path))
        )
        for name, path in required.items()
    }
    checks.update(
        {
            "kokoro_model": kokoro.is_file(),
            "kokoro_voices": voices.is_file(),
            "whisper_models": all(path.is_file() for path in whisper),
        }
    )
    return {
        "version": __version__,
        "repo": str(repo),
        "offline_default": True,
        "checks": checks,
        "ok": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="audiobook-harness")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    new = sub.add_parser("new-project")
    new.add_argument("directory", type=Path)
    for name in ("analyze", "generate", "verify", "release"):
        command = sub.add_parser(name)
        command.add_argument("project", type=Path)
    args = parser.parse_args()
    if args.command == "doctor":
        emit(doctor(REPO))
        return
    if args.command == "new-project":
        scaffold(args.directory.resolve(), REPO / "templates/project")
        emit({"ok": True, "project": str(args.directory.resolve())})
        return
    project = args.project.resolve()
    if args.command == "analyze":
        emit(analyze(project))
        return
    if args.command == "generate":
        emit(generate(project, REPO))
        return
    if args.command == "verify":
        emit(verify(project, REPO))
        return
    if args.command == "release":
        emit(assemble(project))
        return


if __name__ == "__main__":
    main()
