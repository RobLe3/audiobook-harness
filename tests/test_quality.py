from audiobook_harness.quality import _alignment_complete, _mfa_profile


def test_mfa_profile_defaults_to_explicit_english_models():
    assert _mfa_profile({"language": "en-gb"}) == ("english_us_arpa", "english_us_arpa")


def test_non_english_requires_explicit_local_profile():
    try:
        _mfa_profile({"language": "de-de"})
    except ValueError as exc:
        assert "requires" in str(exc)
    else:
        raise AssertionError("non-English profile should not be guessed")


def test_alignment_evidence_requires_every_take(tmp_path):
    (tmp_path / "one.json").write_text("{}")
    ok, missing = _alignment_complete(tmp_path, [{"id": "one"}, {"id": "two"}])
    assert not ok
    assert missing == ["two"]
