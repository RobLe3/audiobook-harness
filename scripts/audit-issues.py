#!/usr/bin/env python3
"""Validate issue-tracker hygiene without changing GitHub state.

The default input is GitHub CLI JSON; --input supports offline fixtures and is
used by tests. This script never opens, edits, labels, or closes issues.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


REQUIRED_HEADINGS = (
    "## Reproduction",
    "## Affected contract",
    "## Risk and scope",
    "## Acceptance criteria",
    "## Closure release",
)
VALID_PROFILES = {
    "integrity",
    "filesystem",
    "quality",
    "supply-chain",
    "operations",
    "release",
}


def audit(rows: list[dict[str, object]]) -> dict[str, object]:
    problems: list[dict[str, object]] = []
    for row in rows:
        number = row.get("number")
        body = str(row.get("body") or "")
        missing = [heading for heading in REQUIRED_HEADINGS if heading not in body]
        profiles = [profile for profile in VALID_PROFILES if f"`{profile}`" in body]
        if missing or not profiles:
            problems.append(
                {
                    "number": number,
                    "missing_headings": missing,
                    "has_profile": bool(profiles),
                }
            )
    return {
        "version": 1,
        "open_issue_count": len(rows),
        "problems": problems,
        "ok": not problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="RobLe3/audiobook-harness")
    parser.add_argument("--input", type=Path, help="Offline GitHub-CLI JSON fixture.")
    args = parser.parse_args()
    if args.input:
        rows = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        output = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                args.repo,
                "--state",
                "open",
                "--limit",
                "100",
                "--json",
                "number,body",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        rows = json.loads(output)
    if not isinstance(rows, list):
        raise ValueError("issue input must be a JSON list")
    report = audit([row for row in rows if isinstance(row, dict)])
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
