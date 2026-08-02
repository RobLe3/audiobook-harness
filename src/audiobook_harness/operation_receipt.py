"""Idempotent, durable receipts for UI-triggered harness operations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .project import write_json

SCHEMA = "audiobook-harness-operation-v1"
STATES = frozenset({"queued", "running", "complete", "failed", "blocked"})


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def operation_identity(kind: str, input_identity: str, payload: object) -> str:
    """Return the stable identity used to deduplicate a requested operation."""
    return hashlib.sha256(
        _canonical(
            {
                "kind": str(kind),
                "input_identity": str(input_identity),
                "payload": payload,
            }
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class OperationReceipt:
    operation_id: str
    kind: str
    input_identity: str
    state: str = "queued"
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""
    schema: str = SCHEMA

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def new_operation(
    *, kind: str, input_identity: str, payload: object, state: str = "queued"
) -> OperationReceipt:
    if state not in STATES:
        raise ValueError(f"invalid operation state: {state}")
    now = datetime.now(timezone.utc).isoformat()
    return OperationReceipt(
        operation_id=operation_identity(kind, input_identity, payload),
        kind=kind,
        input_identity=input_identity,
        state=state,
        created_at=now,
        updated_at=now,
    )


def read_operation(path: Path) -> OperationReceipt | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        return None
    state = str(value.get("state", ""))
    operation_id = str(value.get("operation_id", ""))
    kind = str(value.get("kind", ""))
    input_identity = str(value.get("input_identity", ""))
    if not operation_id or not kind or not input_identity or state not in STATES:
        return None
    return OperationReceipt(
        operation_id=operation_id,
        kind=kind,
        input_identity=input_identity,
        state=state,
        result=value.get("result") if isinstance(value.get("result"), dict) else None,
        error=value.get("error") if isinstance(value.get("error"), dict) else None,
        created_at=str(value.get("created_at", "")),
        updated_at=str(value.get("updated_at", "")),
    )


def write_operation(path: Path, receipt: OperationReceipt) -> OperationReceipt:
    if receipt.schema != SCHEMA or receipt.state not in STATES:
        raise ValueError("invalid operation receipt")
    write_json(path, receipt.as_dict())
    return receipt


def update_operation(
    receipt: OperationReceipt,
    *,
    state: str,
    result: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> OperationReceipt:
    if state not in STATES:
        raise ValueError(f"invalid operation state: {state}")
    return OperationReceipt(
        **{
            **receipt.as_dict(),
            "state": state,
            "result": result,
            "error": error,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
