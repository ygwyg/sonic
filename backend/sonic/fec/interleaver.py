"""Deterministic pseudo-random bit interleaver.

Burst errors (a notch in the channel, an impulsive click) damage adjacent
coded bits. Spreading each packet's coded bits with a fixed permutation
turns a burst into scattered errors the convolutional code can correct.
The permutation only depends on the length, so the receiver can invert it
without side information.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

INTERLEAVER_SEED = 0x5A17
SCRAMBLER_SEED = 0x2F6E


@lru_cache(maxsize=64)
def _perm(n: int) -> np.ndarray:
    rng = np.random.default_rng(INTERLEAVER_SEED + n)
    return rng.permutation(n)


def interleave(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x)
    return x[_perm(x.size)]


def deinterleave(y: np.ndarray) -> np.ndarray:
    y = np.asarray(y)
    out = np.empty_like(y)
    out[_perm(y.size)] = y
    return out


@lru_cache(maxsize=64)
def _scramble_seq(n: int) -> np.ndarray:
    rng = np.random.default_rng(SCRAMBLER_SEED + n)
    return rng.integers(0, 2, n).astype(np.uint8)


def scramble(bits: np.ndarray) -> np.ndarray:
    """XOR coded bits with a fixed pseudo-random sequence.

    Without this, structured data (runs of zero bytes in headers, sparse
    files) puts the same value on hundreds of carriers, which add
    coherently into a huge time-domain peak (PAPR > 20 dB). Scrambling
    makes the carrier phases pseudo-random regardless of content.
    """
    bits = np.asarray(bits, dtype=np.uint8)
    return bits ^ _scramble_seq(bits.size)


def descramble_llr(llr: np.ndarray) -> np.ndarray:
    """Undo :func:`scramble` on soft values: flip the sign where the
    scrambler bit is 1."""
    llr = np.asarray(llr, dtype=np.float64)
    return llr * (1.0 - 2.0 * _scramble_seq(llr.size))
