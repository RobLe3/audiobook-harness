import re
from pathlib import Path

from audiobook_harness import __version__
from audiobook_harness.versioning import compatibility_receipt


def test_product_version_is_single_source_for_package_metadata():
    root = Path(__file__).parents[1]
    assert __version__ == "0.5.2"
    pyproject = (root / "pyproject.toml").read_text()
    assert 'dynamic = ["version"]' in pyproject
    assert re.findall(
        r'(?m)^__version__\s*=\s*"([^"]+)"$',
        (root / "src/audiobook_harness/_version.py").read_text(),
    ) == [__version__]


def test_primary_docs_use_current_product_identity():
    root = Path(__file__).parents[1]
    for name in (
        "ARCHITECTURE.md",
        "QUALITY.md",
        "PERFORMANCE.md",
        "GETTING_STARTED.md",
    ):
        text = (root / "docs" / name).read_text(encoding="utf-8")
        assert "Audiobook Harness **0.4.15**" not in text
        assert f"Audiobook Harness **{__version__}**" in text


def test_compatibility_receipt_is_hash_bound_and_non_destructive(tmp_path: Path):
    production = tmp_path / "production"
    production.mkdir()
    analysis = production / "analysis.json"
    analysis.write_text('{"ok":true}')
    first = compatibility_receipt(tmp_path)
    assert first["product_version"] == "0.5.2"
    assert first["historical_artifact_family"] == "pre-semver-project"
    assert not (production / "version-compatibility-receipt.json").exists()
    stored = compatibility_receipt(tmp_path, apply=True)
    assert (production / "version-compatibility-receipt.json").is_file()
    analysis.write_text('{"ok":false}')
    assert (
        compatibility_receipt(tmp_path)["compatibility_sha256"]
        != stored["compatibility_sha256"]
    )
