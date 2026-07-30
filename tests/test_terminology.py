from pathlib import Path


def test_current_product_surface_uses_only_semver_product_identity():
    root = Path(__file__).parents[1]
    paths = [
        root / "README.md",
        root / "AGENTS.md",
        root / "docs/VERSIONING.md",
        root / "skills/audiobook-harness/SKILL.md",
        *sorted((root / "src/audiobook_harness").glob("*.py")),
    ]
    forbidden = ("8.3", "8.4", "v8")
    failures = [
        str(path.relative_to(root))
        for path in paths
        if any(value in path.read_text(encoding="utf-8") for value in forbidden)
    ]
    assert failures == []
