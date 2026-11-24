"""Rolling frames-per-second meter and ETA formatting for the processing readout."""

from __future__ import annotations

import time
from collections import deque


class ProcessingRateMeter:
    """Frames/sec over a sliding time window.

    ``tick()`` is called once per finished frame. The rate is the number of
    frames inside the last ``window_sec`` seconds divided by the span they
    cover, so a single slow frame doesn't make the number jump around.
    """

    def __init__(self, window_sec: float = 3.0, max_samples: int = 2000):
        self.window_sec = float(window_sec)
        self._stamps: deque[float] = deque(maxlen=max_samples)

    def reset(self) -> None:
        self._stamps.clear()

    def tick(self, now_sec: float | None = None) -> None:
        now = time.perf_counter() if now_sec is None else float(now_sec)
        self._stamps.append(now)
        cutoff = now - self.window_sec
        while len(self._stamps) > 2 and self._stamps[0] < cutoff:
            self._stamps.popleft()

    @property
    def sample_count(self) -> int:
        return len(self._stamps)

    def fps(self) -> float:
        if len(self._stamps) < 2:
            return 0.0
        span = self._stamps[-1] - self._stamps[0]
        if span <= 0.0:
            return 0.0
        return (len(self._stamps) - 1) / span

    def eta_seconds(self, remaining_frames: int) -> float | None:
        rate = self.fps()
        if rate <= 0.0 or remaining_frames < 0:
            return None
        return remaining_frames / rate


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds != seconds or seconds < 0:  # None / NaN / negative
        return "--:--"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_processing_stats(
    fps: float, remaining_frames: int | None = None, eta: float | None = None
) -> str:
    text = f"{fps:.1f} fps"
    if remaining_frames is not None:
        text += f" · ETA {format_eta(eta)}"
    return text
