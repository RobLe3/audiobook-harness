from audiobook_harness.resilience import GateDisposition, GateResult


def test_chapter_evidence_block_does_not_block_series():
    result = GateResult(
        gate="lineage",
        disposition=GateDisposition.BLOCKED_EVIDENCE,
        owner_phase=6,
        evidence_fingerprint="fingerprint",
        affected_units=("unit-1",),
    )
    assert result.blocks_chapter
    assert not result.blocks_series


def test_fatal_tool_failure_blocks_series():
    result = GateResult(
        gate="runtime",
        disposition=GateDisposition.FATAL_TOOL_FAILURE,
        owner_phase=2,
        evidence_fingerprint="fingerprint",
    )
    assert result.blocks_series
