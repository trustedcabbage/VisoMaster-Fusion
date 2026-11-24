import pytest

from app.helpers.processing_rate import (
    ProcessingRateMeter,
    format_eta,
    format_processing_stats,
)


def test_fps_is_zero_until_two_samples():
    meter = ProcessingRateMeter(window_sec=3)
    assert meter.fps() == 0.0
    meter.tick(10.0)
    assert meter.fps() == 0.0


def test_steady_rate():
    meter = ProcessingRateMeter(window_sec=3)
    for i in range(31):  # 30 frames over 1 second
        meter.tick(100.0 + i / 30)
    assert meter.fps() == pytest.approx(30.0)


def test_window_drops_old_samples():
    meter = ProcessingRateMeter(window_sec=1)
    for i in range(10):  # slow phase: 1 fps
        meter.tick(float(i))
    for i in range(1, 21):  # fast phase: 20 fps
        meter.tick(9.0 + i / 20)
    assert meter.fps() == pytest.approx(20.0, rel=0.1)


def test_eta_and_reset():
    meter = ProcessingRateMeter()
    for i in range(11):
        meter.tick(i * 0.1)  # 10 fps
    assert meter.eta_seconds(50) == pytest.approx(5.0)
    meter.reset()
    assert meter.sample_count == 0
    assert meter.eta_seconds(50) is None


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (None, "--:--"),
        (-1, "--:--"),
        (float("nan"), "--:--"),
        (0, "00:00"),
        (65.4, "01:05"),
        (3725, "1:02:05"),
    ],
)
def test_format_eta(seconds, expected):
    assert format_eta(seconds) == expected


def test_format_processing_stats():
    assert format_processing_stats(12.345) == "12.3 fps"
    assert format_processing_stats(10, 100, 10) == "10.0 fps · ETA 00:10"
