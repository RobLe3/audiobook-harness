"""Single-writer project lock for long-running local production."""

from __future__ import annotations

import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def lock_path(project: Path) -> Path:
    return project / "production/.audiobook-harness.writer.lock"


@contextmanager
def project_writer_lock(project: Path) -> Iterator[None]:
    """Acquire a project-local lock, rejecting active concurrent writers."""
    path = lock_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir()
    except FileExistsError as error:
        owner = None
        try:
            owner = int(json.loads((path / "owner.json").read_text()).get("pid"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
        if owner and owner != os.getpid():
            try:
                os.kill(owner, 0)
            except ProcessLookupError:
                shutil.rmtree(path, ignore_errors=True)
                path.mkdir()
            except PermissionError:
                raise RuntimeError(
                    f"Project is locked by another production process (pid {owner})"
                ) from error
            else:
                raise RuntimeError(
                    f"Project is locked by another production process (pid {owner})"
                ) from error
        else:
            raise RuntimeError(
                "Project has an unreadable or active writer lock"
            ) from error
    (path / "owner.json").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    try:
        yield
    finally:
        shutil.rmtree(path, ignore_errors=True)
