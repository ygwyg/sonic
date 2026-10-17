"""Gray-coded square constellations with exact max-log soft demapping.

All constellations are normalised to unit average symbol energy, so
different modulation orders can be compared at equal transmit power.

Bit ordering for a ``b``-bit symbol: the first ``b/2`` bits select the
in-phase level, the last ``b/2`` bits the quadrature level (BPSK uses the
real axis only). Levels are Gray coded so adjacent levels differ in one
bit, which minimises bit errors for a given symbol error.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from sonic.config import BITS_PER_SYMBOL


def _gray_encode(i: np.ndarray) -> np.ndarray:
    return i ^ (i >> 1)


def _gray_decode(g: np.ndarray) -> np.ndarray:
    g = np.asarray(g).copy()
    mask = g >> 1
    while np.any(mask):
        g ^= mask
        mask >>= 1
    return g


@dataclass(frozen=True)
class Constellation:
    name: str
    bits: int
    bits_per_dim: int
    levels: np.ndarray  # PAM levels (unnormalised ints), index = natural order
    level_bits: np.ndarray  # (L, bits_per_dim) bit pattern of each level index
    norm: float  # multiply unnormalised points by this
    points: np.ndarray  # (2**bits,) complex, index = symbol integer value

    def average_energy_unnormalised(self) -> float:
        return float(np.mean(np.abs(self.points / self.norm) ** 2))


@lru_cache(maxsize=None)
def get_constellation(name: str) -> Constellation:
    if name not in BITS_PER_SYMBOL:
        raise ValueError(f"unknown modulation {name!r}")
    bits = BITS_PER_SYMBOL[name]
    if name == "bpsk":
        levels = np.array([-1, 1])
        level_bits = np.array([[0], [1]])
        pts = levels.astype(np.complex128)
        norm = 1.0
        return Constellation(name, 1, 1, levels, level_bits, norm, pts * norm)

    bpd = bits // 2
    L = 2**bpd
    idx = np.arange(L)
    levels = 2 * idx - (L - 1)  # -(L-1), ..., L-1 step 2
    gray = _gray_encode(idx)
    level_bits = ((gray[:, None] >> (bpd - 1 - np.arange(bpd))[None, :]) & 1).astype(np.int64)
    # symbol integer v = (i_bits << bpd) | q_bits  with bits in MSB-first order
    sym = np.arange(2**bits)
    i_code = sym >> bpd
    q_code = sym & (L - 1)
    i_lvl = levels[_gray_decode(i_code)]
    q_lvl = levels[_gray_decode(q_code)]
    pts = i_lvl + 1j * q_lvl
    norm = 1.0 / np.sqrt(np.mean(np.abs(pts) ** 2))
    return Constellation(name, bits, bpd, levels, level_bits, float(norm), pts * norm)


def bits_to_ints(bits: np.ndarray, width: int) -> np.ndarray:
    """Pack a flat bit array (MSB first) into integers of ``width`` bits."""
    bits = np.asarray(bits, dtype=np.int64).reshape(-1, width)
    weights = 1 << (width - 1 - np.arange(width))
    return (bits * weights).sum(axis=1)


def ints_to_bits(vals: np.ndarray, width: int) -> np.ndarray:
    vals = np.asarray(vals, dtype=np.int64)
    shifts = width - 1 - np.arange(width)
    return ((vals[:, None] >> shifts[None, :]) & 1).reshape(-1).astype(np.uint8)


def modulate(bits: np.ndarray, modulation: str) -> np.ndarray:
    """Map bits (0/1 array, length multiple of bits-per-symbol) to symbols."""
    c = get_constellation(modulation)
    bits = np.asarray(bits, dtype=np.uint8)
    if bits.size % c.bits:
        raise ValueError(f"bit count {bits.size} is not a multiple of {c.bits}")
    return c.points[bits_to_ints(bits, c.bits)]


def _nearest_level_index(y: np.ndarray, c: Constellation) -> np.ndarray:
    L = len(c.levels)
    i = np.rint((y / c.norm + (L - 1)) / 2).astype(np.int64)
    return np.clip(i, 0, L - 1)


def demodulate_hard(symbols: np.ndarray, modulation: str) -> np.ndarray:
    """Nearest-point hard decisions, returned as a flat bit array."""
    c = get_constellation(modulation)
    y = np.asarray(symbols, dtype=np.complex128)
    if c.name == "bpsk":
        return (y.real > 0).astype(np.uint8)
    i_idx = _nearest_level_index(y.real, c)
    q_idx = _nearest_level_index(y.imag, c)
    out = np.concatenate([c.level_bits[i_idx], c.level_bits[q_idx]], axis=1)
    return out.reshape(-1).astype(np.uint8)


def _soft_1d(y: np.ndarray, c: Constellation, noise_var: np.ndarray) -> np.ndarray:
    """Max-log LLRs for one dimension. Returns (N, bits_per_dim)."""
    lv = c.levels * c.norm  # (L,)
    d2 = (y[:, None] - lv[None, :]) ** 2  # (N, L)
    out = np.empty((y.size, c.bits_per_dim))
    for j in range(c.bits_per_dim):
        is_one = c.level_bits[:, j] == 1
        d0 = d2[:, ~is_one].min(axis=1)
        d1 = d2[:, is_one].min(axis=1)
        out[:, j] = (d1 - d0) / noise_var
    return out


def demodulate_soft(symbols: np.ndarray, modulation: str, noise_var: float | np.ndarray = 1.0) -> np.ndarray:
    """Max-log LLRs. Positive LLR means bit 0 is more likely.

    ``noise_var`` is the complex noise variance per symbol (scalar or array of
    length N). Returned shape is ``(N * bits_per_symbol,)``.
    """
    c = get_constellation(modulation)
    y = np.asarray(symbols, dtype=np.complex128)
    nv = np.broadcast_to(np.asarray(noise_var, dtype=np.float64), y.shape).copy()
    nv = np.maximum(nv, 1e-12)
    if c.name == "bpsk":
        # bit 0 -> -1, bit 1 -> +1: LLR = (|y-1|^2 - |y+1|^2)/nv = -4 Re(y)/nv
        return -4.0 * y.real / nv
    llr_i = _soft_1d(y.real, c, nv)
    llr_q = _soft_1d(y.imag, c, nv)
    return np.concatenate([llr_i, llr_q], axis=1).reshape(-1)
