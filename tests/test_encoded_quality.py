from audiobook_harness.encoded_quality import (
    codec_frame_tolerance_seconds,
    encoded_tail_result,
)


def test_aac_and_mp3_allow_only_one_codec_frame_of_tail_variance():
    aac = encoded_tail_result(
        master_tail_seconds=2.2,
        encoded_tail_seconds=2.200604,
        codec="aac",
        sample_rate=48_000,
    )
    mp3 = encoded_tail_result(
        master_tail_seconds=2.2,
        encoded_tail_seconds=2.209396,
        codec="mp3",
        sample_rate=48_000,
    )
    assert aac["ok"]
    assert mp3["ok"]
    assert codec_frame_tolerance_seconds("aac", 48_000) == 1024 / 48_000
    assert codec_frame_tolerance_seconds("mp3", 48_000) == 1152 / 48_000


def test_tail_beyond_one_codec_frame_remains_blocking():
    result = encoded_tail_result(
        master_tail_seconds=2.2,
        encoded_tail_seconds=2.25,
        codec="mp3",
        sample_rate=48_000,
    )
    assert not result["ok"]
    assert result["tail_status"] == "outside_codec_frame_tolerance"


def test_missing_encoded_tail_measurement_is_not_accepted():
    result = encoded_tail_result(
        master_tail_seconds=1.5,
        encoded_tail_seconds=None,
        codec="aac",
        sample_rate=48_000,
    )
    assert not result["ok"]
