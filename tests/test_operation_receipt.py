from pathlib import Path

from audiobook_harness.operation_receipt import (
    new_operation,
    operation_identity,
    read_operation,
    update_operation,
    write_operation,
)


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
