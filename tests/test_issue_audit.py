from audiobook_harness import __version__  # ensure package import remains fixture-free

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/audit-issues.py"
spec = importlib.util.spec_from_file_location("issue_audit", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


BODY = """## Reproduction
x
## Affected contract
x
## Risk and scope
x
## Acceptance criteria
- required local verification profile: `integrity`
## Closure release
x
"""


def test_empty_open_issue_list_is_clean():
    assert module.audit([]) == {
        "version": 1,
        "open_issue_count": 0,
        "problems": [],
        "ok": True,
    }


def test_issue_audit_rejects_missing_contract_and_profile():
    result = module.audit([{"number": 12, "body": "## Reproduction\nx"}])
    assert result["ok"] is False
    assert result["problems"][0]["number"] == 12


def test_issue_audit_accepts_complete_bounded_issue():
    assert module.audit([{"number": 12, "body": BODY}])["ok"] is True
    assert __version__
