from pathlib import Path
import pytest

from audiobook_harness.operation_receipt import (
    new_operation,
    operation_identity,
    read_operation,
    update_operation,
    write_operation,
)
from audiobook_harness import project as project_module


def test_operation_identity_is_stable_for_same_request():
    assert operation_identity("repair", "input", {"cue": "c001"}) == operation_identity(
        "repair", "input", {"cue": "c001"}
    )
    assert operation_identity("repair", "input", {"cue": "c001"}) != operation_identity(
        "repair", "input", {"cue": "c002"}
    )


def test_operation_receipt_round_trips_and_updates(tmp_path: Path):
    path = tmp_path / "production" / "operation.json"
    queued = new_operation(
        kind="targeted_repair", input_identity="abc", payload={"cues": ["c001"]}
    )
    write_operation(path, queued)
    assert read_operation(path) == queued

    complete = update_operation(queued, state="complete", result={"reused": True})
    write_operation(path, complete)
    loaded = read_operation(path)
    assert loaded is not None
    assert loaded.state == "complete"
    assert loaded.result == {"reused": True}


def test_invalid_operation_receipt_is_not_authoritative(tmp_path: Path):
    path = tmp_path / "operation.json"
    path.write_text('{"schema":"wrong","state":"complete"}')
    assert read_operation(path) is None


def test_atomic_receipt_write_preserves_previous_document_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "operation.json"
    previous = new_operation(kind="repair", input_identity="old", payload={})
    write_operation(path, previous)

    def fail_replace(_temporary: str, _destination: Path) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr(project_module.os, "replace", fail_replace)
    current = new_operation(kind="repair", input_identity="new", payload={})
    with pytest.raises(OSError, match="simulated interruption"):
        write_operation(path, current)
    assert read_operation(path) == previous


def test_atomic_receipt_write_cleans_temporary_file_on_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    path = tmp_path / "operation.json"
    previous = new_operation(kind="repair", input_identity="old", payload={})
    write_operation(path, previous)
    original_fsync = project_module.os.fsync

    def fail_fsync(fd: int) -> None:
        raise OSError("simulated fsync interruption")

    monkeypatch.setattr(project_module.os, "fsync", fail_fsync)
    current = new_operation(kind="repair", input_identity="new", payload={})
    with pytest.raises(OSError, match="fsync interruption"):
        write_operation(path, current)
    assert read_operation(path) == previous
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))
    monkeypatch.setattr(project_module.os, "fsync", original_fsync)
