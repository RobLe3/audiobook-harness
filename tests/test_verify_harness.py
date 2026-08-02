import importlib.util
import os
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/verify-harness.py"
spec = importlib.util.spec_from_file_location("verify_harness", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_each_issue_profile_has_a_focused_pytest_command():
    root = Path(__file__).parents[1]
    python = Path("/python")
    for profile, expected in module.PROFILE_TESTS.items():
        commands = module.verification_commands(root, python, profile)
        pytest = next(row for row in commands if row[0] == "pytest")
        assert pytest[1][-len(expected) :] == list(expected)


def test_release_profile_runs_the_complete_test_suite_and_lock_check_when_available(
    monkeypatch,
):
    monkeypatch.setattr(
        module.shutil, "which", lambda name: "/uv" if name == "uv" else None
    )
    commands = module.verification_commands(Path("."), Path("/python"), "release")
    pytest = next(row for row in commands if row[0] == "pytest")
    assert pytest[1] == ["/python", "-m", "pytest", "-q"]
    assert any(row[0] == "lock" for row in commands)


def test_contract_self_check_uses_a_non_recursive_pytest_subset(monkeypatch):
    monkeypatch.setitem(os.environ, "AUDIOBOOK_HARNESS_VERIFY_TEST", "1")
    commands = module.verification_commands(Path("."), Path("/python"), "release")
    pytest = next(row for row in commands if row[0] == "pytest")
    assert pytest[1] == ["/python", "-m", "pytest", "-q", "tests/test_phase_engine.py"]
