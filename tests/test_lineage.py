import numpy as np

from audiobook_harness.lineage import (
    legacy_lineage_passes,
    pcm_lineage_metrics,
    render_identity,
    take_identity,
)


def test_take_and_render_identities_separate_performance_from_processing():
    take = take_identity(clean_audio_sha256="clean", synthesis={"voice": "v"})
    first = render_identity(
        take_id=take,
        processed_audio_sha256="processed-a",
        processor={"version": "one"},
    )
    second = render_identity(
        take_id=take,
        processed_audio_sha256="processed-b",
        processor={"version": "two"},
    )
    assert first != second
    assert take == take_identity(clean_audio_sha256="clean", synthesis={"voice": "v"})


def test_legacy_lineage_requires_every_declared_bound():
    expected = np.linspace(-0.2, 0.2, 1000)
    observed = expected + 1e-8
    metrics = pcm_lineage_metrics(expected, observed, edge_guard_samples=10)
    assert legacy_lineage_passes(
        metrics,
        minimum_correlation=0.999999,
        maximum_mean_error=1e-7,
        maximum_peak_error=1e-6,
    )
    observed[500] += 0.01
    assert not legacy_lineage_passes(
        pcm_lineage_metrics(expected, observed, edge_guard_samples=10),
        minimum_correlation=0.999999,
        maximum_mean_error=1e-7,
        maximum_peak_error=1e-6,
    )
