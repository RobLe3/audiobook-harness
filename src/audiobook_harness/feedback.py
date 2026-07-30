from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .project import write_json

DEFECT_CATEGORIES = {
    "spoken_form",
    "pause",
    "pronunciation",
    "mix_or_loudness",
    "performance",
    "speaker_or_mode",
    "stretch_or_timing",
    "other",
}
PROMOTION_STATES = {"observed", "reproduced", "candidate", "promoted", "retired"}


def _canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in decisions:
        item = str(raw.get("id", "")).strip()
        decision = str(raw.get("decision", "")).strip()
        if not item or item in seen:
            raise ValueError("Every review decision must have one unique id")
        if decision not in {"approve", "reject", "uncertain"}:
            raise ValueError(f"Invalid decision for {item}: {decision}")
        category = str(raw.get("defect_category", "")).strip()
        note = str(raw.get("note", raw.get("notes", ""))).strip()
        if decision != "approve":
            if category not in DEFECT_CATEGORIES:
                raise ValueError(
                    f"{item}: reject/uncertain requires a valid defect_category"
                )
            if category == "other" and not note:
                raise ValueError(f"{item}: defect_category=other requires a note")
        row: dict[str, Any] = {"id": item, "decision": decision}
        if category:
            row["defect_category"] = category
        if note:
            row["note"] = note
        normalized.append(row)
        seen.add(item)
    return normalized


def append_observations(
    project: Path, manifest: dict[str, Any], decisions: list[dict[str, Any]]
) -> Path:
    production = project / "production"
    path = production / "listener-feedback-ledger.jsonl"
    item_by_id = {str(row["id"]): row for row in manifest.get("items", [])}
    existing: set[str] = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                existing.add(str(json.loads(line).get("observation_sha256", "")))
            except json.JSONDecodeError:
                continue
    additions: list[str] = []
    for decision in decisions:
        item = item_by_id.get(str(decision["id"]), {})
        record: dict[str, Any] = {
            "version": 1,
            "project": str(project.resolve()),
            "item_id": decision["id"],
            "item_kind": item.get("kind"),
            "audio_sha256": item.get("audio_sha256"),
            "review_identity_sha256": manifest["review_identity_sha256"],
            "decision": decision["decision"],
            "defect_category": decision.get("defect_category"),
            "note": decision.get("note"),
            "root_cause": None,
            "correction": None,
            "corrected_audio_sha256": None,
            "objective_evidence": None,
            "follow_up_decision": None,
            "generalization_scope": "cue_only",
            "promotion_state": "observed",
            "recorded_at": _now(),
        }
        identity_value = {
            key: value for key, value in record.items() if key != "recorded_at"
        }
        record["observation_sha256"] = _canonical(identity_value)
        if record["observation_sha256"] not in existing:
            additions.append(json.dumps(record, ensure_ascii=False, sort_keys=True))
            existing.add(record["observation_sha256"])
    if additions:
        production.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(additions) + "\n")
    return path


def load_defaults(project: Path) -> dict[str, Any]:
    path = project / "listener-derived-defaults.json"
    if not path.is_file():
        return {"version": 1, "revision": 0, "rules": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("rules", []), list):
        raise ValueError("listener-derived-defaults.json must contain a rules list")
    return value


def defaults_identity(defaults: dict[str, Any]) -> str:
    return _canonical(defaults)


def historical_matches(project: Path, text: str) -> list[dict[str, Any]]:
    defaults = load_defaults(project)
    matches: list[dict[str, Any]] = []
    for rule in defaults.get("rules", []):
        if rule.get("promotion_state") != "promoted":
            continue
        matcher = rule.get("matcher", {})
        kind = matcher.get("kind")
        pattern = str(matcher.get("value", ""))
        matched = False
        if kind == "exact_term":
            matched = bool(
                re.search(rf"(?<!\w){re.escape(pattern)}(?!\w)", text, re.IGNORECASE)
            )
        elif kind == "regex":
            matched = bool(re.search(pattern, text, re.IGNORECASE))
        if matched:
            matches.append(
                {
                    "rule_id": rule.get("id"),
                    "defect_category": rule.get("defect_category"),
                    "action": rule.get("action"),
                    "provenance": rule.get("provenance", []),
                }
            )
    return matches


def compile_feedback(project: Path) -> dict[str, Any]:
    path = project / "production/listener-feedback-ledger.jsonl"
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen: set[str] = set()
    if path.is_file():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                failures.append({"line": number, "error": "invalid_json"})
                continue
            identity = str(row.get("observation_sha256", ""))
            if not identity or identity in seen:
                failures.append(
                    {"line": number, "error": "missing_or_duplicate_identity"}
                )
                continue
            if row.get("promotion_state") not in PROMOTION_STATES:
                failures.append({"line": number, "error": "invalid_promotion_state"})
                continue
            seen.add(identity)
            records.append(row)
    categories: dict[str, int] = {}
    repeated: dict[str, set[str]] = {}
    for row in records:
        category = str(row.get("defect_category") or "approved")
        categories[category] = categories.get(category, 0) + 1
        root = str(row.get("root_cause") or "")
        if root:
            repeated.setdefault(root, set()).add(str(row.get("item_id")))
    candidates = [
        {
            "root_cause": root,
            "occurrences": len(items),
            "eligible_for_candidate": len(items) >= 3,
        }
        for root, items in sorted(repeated.items())
    ]
    summary = {
        "version": 1,
        "records": len(records),
        "categories": categories,
        "promotion_candidates": candidates,
        "failures": failures,
        "ok": not failures,
    }
    summary["identity_sha256"] = _canonical(summary)
    write_json(project / "production/listener-learning-summary.json", summary)
    write_json(
        project / "production/default-promotion-candidates.json",
        {"version": 1, "candidates": candidates},
    )
    write_json(
        project / "production/feedback-coverage-audit.json",
        {
            "version": 1,
            "ledger_records": len(records),
            "unique_records": len(seen),
            "failures": failures,
            "ok": not failures,
        },
    )
    return summary


def promote_rule(project: Path, rule_id: str) -> dict[str, Any]:
    defaults = load_defaults(project)
    matched = False
    for rule in defaults.get("rules", []):
        if str(rule.get("id")) != rule_id:
            continue
        evidence = rule.get("evidence", {})
        occurrences = int(evidence.get("distinct_occurrences", 0))
        episodes = int(evidence.get("distinct_episodes", 0))
        editorial = bool(evidence.get("editorial_authority"))
        verified = bool(evidence.get("objective_verification_ok"))
        approved = bool(evidence.get("listener_follow_up_approved"))
        regression = bool(evidence.get("regression_ok"))
        eligible = (editorial or occurrences >= 3 or episodes >= 2) and all(
            (verified, approved, regression)
        )
        if not eligible:
            raise ValueError(f"Rule {rule_id} does not satisfy promotion policy")
        rule["promotion_state"] = "promoted"
        rule["promoted_at"] = _now()
        matched = True
    if not matched:
        raise KeyError(f"Unknown listener-derived rule: {rule_id}")
    defaults["revision"] = int(defaults.get("revision", 0)) + 1
    defaults["identity_sha256"] = _canonical(
        {key: value for key, value in defaults.items() if key != "identity_sha256"}
    )
    write_json(project / "listener-derived-defaults.json", defaults)
    return defaults
