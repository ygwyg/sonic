"""Preamble detection by normalised matched filtering."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import fftconvolve

from sonic.ofdm.preamble import preamble_chirp

DEFAULT_THRESHOLD = 0.15
RELATIVE_THRESHOLD = 0.4  # secondary candidates must reach this fraction of the best score


@dataclass
class SyncCandidate:
    position: int  # sample index where the chirp starts
    score: float  # normalised correlation in [0, 1]


def detect_preambles(
    samples: np.ndarray,
    sample_rate: int,
    threshold: float = DEFAULT_THRESHOLD,
    max_candidates: int = 8,
) -> list[SyncCandidate]:
    """Return chirp start positions sorted by decreasing correlation score.

    The matched-filter output is normalised by the local signal energy so
    that loud transients do not masquerade as preambles and quiet
    recordings are not missed. OFDM payload symbols correlate weakly with
    the chirp (~0.05-0.13 normalised), so secondary candidates must also
    reach a fraction of the strongest candidate's score.
    """
    x = np.asarray(samples, dtype=np.float64)
    ch = preamble_chirp(sample_rate)
    n = len(ch)
    if x.size < n:
        return []
    corr = fftconvolve(x, ch[::-1], mode="valid")  # corr[i] ~ <x[i:i+n], ch>
    energy = fftconvolve(x**2, np.ones(n), mode="valid")
    norm = np.sqrt(np.maximum(energy, 1e-12) * np.sum(ch**2))
    score = np.abs(corr) / norm
    # ignore windows that are essentially silent
    silent = energy < 1e-9 * max(np.max(energy), 1e-12)
    score[silent] = 0.0
    cands: list[SyncCandidate] = []
    work = score.copy()
    for _ in range(max_candidates):
        i = int(np.argmax(work))
        s = float(work[i])
        if s < threshold or (cands and s < RELATIVE_THRESHOLD * cands[0].score):
            break
        cands.append(SyncCandidate(position=i, score=s))
        lo, hi = max(0, i - n), min(work.size, i + n)
        work[lo:hi] = 0.0
    return cands
