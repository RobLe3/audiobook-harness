"""Single-writer project lock for long-running local production."""

from __future__ import annotations

import json
import os
import secrets
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .project import write_json


def lock_path(project: Path) -> Path:
    return project / "production/.audiobook-harness.writer.lock"


def _owner_record(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads((path / "owner.json").read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _remove_stale_lock(path: Path, expected: dict[str, object]) -> None:
    """Remove only the exact stale lease inspected by this process.

    A lock directory can be recreated between a stale-owner check and cleanup.
    Re-reading the complete owner record prevents this process from deleting a
    newer lease. Symlinked lock paths are never followed by cleanup.
    """
    if path.is_symlink() or not path.is_dir() or _owner_record(path) != expected:
        raise RuntimeError("Project writer lock changed during stale-lock recovery")
    shutil.rmtree(path)


@contextmanager
def project_writer_lock(project: Path) -> Iterator[None]:
    """Acquire a project-local lock, rejecting active concurrent writers."""
    path = lock_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    owner_record: dict[str, object] = {
        "pid": os.getpid(),
        "token": secrets.token_urlsafe(24),
    }
    try:
        path.mkdir()
    except FileExistsError as error:
        existing = _owner_record(path)
        owner = existing.get("pid") if existing else None
        try:
            owner = int(owner) if owner is not None else None
        except (TypeError, ValueError):
            owner = None
        if owner and owner != os.getpid():
            try:
                os.kill(owner, 0)
            except ProcessLookupError:
                if existing is None:
                    raise RuntimeError(
                        "Project has an unreadable writer lock"
                    ) from error
                _remove_stale_lock(path, existing)
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
    write_json(path / "owner.json", owner_record)
    try:
        yield
    finally:
        # Never remove a lease that another writer replaced while this command
        # was running. Leaving the unexpected lease in place fails safe.
        if not path.is_symlink() and _owner_record(path) == owner_record:
            shutil.rmtree(path)
