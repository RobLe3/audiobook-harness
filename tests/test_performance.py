from audiobook_harness.performance import resolve_profile


def test_legacy_profile_is_serial():
    profile = resolve_profile("legacy", logical_cpus=16, memory_bytes=128 * 1024**3)
    assert profile.alignment_jobs == 1
    assert not profile.alignment_multiprocessing


def test_auto_profile_reserves_capacity():
    profile = resolve_profile("auto", logical_cpus=16, memory_bytes=128 * 1024**3)
    assert profile.reserved_cpus >= 2
    assert profile.cpu_budget == 16 - profile.reserved_cpus
    assert profile.alignment_jobs == 6
    assert profile.alignment_serial_fallback
    assert profile.asr_model_workers == 2


def test_small_auto_profile_is_bounded():
    profile = resolve_profile("auto", logical_cpus=2, memory_bytes=8 * 1024**3)
    assert 1 <= profile.alignment_jobs <= profile.cpu_budget
    assert profile.asr_model_workers == 1
