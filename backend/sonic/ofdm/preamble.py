"""Synchronisation preamble: a windowed linear chirp.

A chirp has a sharp, thumbtack-like autocorrelation, which makes the
matched-filter peak at the receiver an excellent timing reference even in
noise and mild reverberation. The chirp band (1--7 kHz) matches the fixed
header band so any speaker/microphone that can carry the header can also
carry the preamble.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.signal import chirp
from scipy.signal.windows import tukey

from sonic.config import PREAMBLE_DURATION, PREAMBLE_F0, PREAMBLE_F1, PREAMBLE_GUARD


@lru_cache(maxsize=8)
def preamble_chirp(sample_rate: int) -> np.ndarray:
    n = int(round(PREAMBLE_DURATION * sample_rate))
    t = np.arange(n) / sample_rate
    x = chirp(t, f0=PREAMBLE_F0, f1=PREAMBLE_F1, t1=t[-1], method="linear")
    return (x * tukey(n, 0.1)).astype(np.float64)


def preamble_guard_samples(sample_rate: int) -> int:
    return int(round(PREAMBLE_GUARD * sample_rate))


def preamble_length(sample_rate: int) -> int:
    """Chirp plus guard: the offset from preamble start to the first symbol."""
    return len(preamble_chirp(sample_rate)) + preamble_guard_samples(sample_rate)
