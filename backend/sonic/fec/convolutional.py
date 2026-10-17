"""Rate-1/2, K=7 convolutional code (171,133 octal) with puncturing and a
vectorised soft-decision Viterbi decoder.

This is the industry-standard code used by 802.11a/g, DVB and many others.
Puncturing to 2/3 and 3/4 follows the 802.11 patterns. The decoder operates
on log-likelihood ratios where a positive value favours bit 0.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

K = 7
G0 = 0o171
G1 = 0o133
N_STATES = 1 << (K - 1)

# Puncturing patterns: (period of input bits, kept positions in the
# interleaved [o0, o1, o0, o1, ...] stream of length 2*period).
PUNCTURE = {
    "1/2": (1, np.array([1, 1], dtype=bool)),
    "2/3": (2, np.array([1, 1, 1, 0], dtype=bool)),
    "3/4": (3, np.array([1, 1, 1, 0, 0, 1], dtype=bool)),
}


def _parity(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.int64)
    p = np.zeros_like(x)
    for _ in range(K):
        p ^= x & 1
        x >>= 1
    return p


@lru_cache(maxsize=1)
def _trellis():
    """Precompute predecessor and output tables for the Viterbi decoder."""
    ns = np.arange(N_STATES)
    u = ns >> (K - 2)  # input bit that leads into state ns
    base = (ns & (N_STATES // 2 - 1)) << 1
    prev = np.stack([base, base | 1], axis=1)  # (64, 2) predecessor states
    reg = (u[:, None] << (K - 1)) | prev  # 7-bit register for each transition
    o0 = _parity(reg & G0)
    o1 = _parity(reg & G1)
    out_idx = (o0 << 1) | o1  # 0..3
    return prev, u, out_idx


def encode(bits: np.ndarray, code_rate: str = "1/2") -> np.ndarray:
    """Encode with tail termination (K-1 zero bits appended).

    Returns the punctured coded bit stream.
    """
    bits = np.asarray(bits, dtype=np.uint8).reshape(-1)
    period, pattern = PUNCTURE[code_rate]
    # pad so that terminated length is a multiple of the puncture period
    n_info = bits.size + (K - 1)
    pad = (-n_info) % period
    x = np.concatenate([bits, np.zeros(K - 1 + pad, dtype=np.uint8)]).astype(np.int64)
    g0 = np.array([(G0 >> (K - 1 - i)) & 1 for i in range(K)])
    g1 = np.array([(G1 >> (K - 1 - i)) & 1 for i in range(K)])
    c0 = np.convolve(x, g0)[: x.size] & 1
    c1 = np.convolve(x, g1)[: x.size] & 1
    coded = np.stack([c0, c1], axis=1).reshape(-1)
    if code_rate != "1/2":
        mask = np.tile(pattern, x.size // period)
        coded = coded[mask]
    return coded.astype(np.uint8)


def coded_length(n_info_bits: int, code_rate: str = "1/2") -> int:
    period, pattern = PUNCTURE[code_rate]
    n = n_info_bits + (K - 1)
    n += (-n) % period
    return int(n // period * pattern.sum())


def decode(llr: np.ndarray, n_info_bits: int, code_rate: str = "1/2") -> np.ndarray:
    """Soft-decision Viterbi decode. ``llr > 0`` favours bit 0.

    ``n_info_bits`` is the number of information bits before tail bits.
    """
    period, pattern = PUNCTURE[code_rate]
    llr = np.asarray(llr, dtype=np.float64).reshape(-1)
    n_total = n_info_bits + (K - 1)
    n_total += (-n_total) % period
    expected = n_total // period * int(pattern.sum())
    if llr.size != expected:
        raise ValueError(f"expected {expected} LLRs, got {llr.size}")
    # depuncture: unknown bits get LLR 0
    if code_rate != "1/2":
        full = np.zeros(2 * n_total)
        mask = np.tile(pattern, n_total // period)
        full[mask] = llr
        llr = full
    l0 = llr[0::2]
    l1 = llr[1::2]
    # branch metric for each of the 4 output pairs: correlation with +1/-1
    # bit 0 -> +llr, bit 1 -> -llr
    s0 = np.stack([l0, -l0], axis=1)  # (T, 2) metric contribution of o0 = 0/1
    s1 = np.stack([l1, -l1], axis=1)
    # bm[t, idx] where idx = (o0<<1)|o1
    bm = np.empty((n_total, 4))
    bm[:, 0] = s0[:, 0] + s1[:, 0]
    bm[:, 1] = s0[:, 0] + s1[:, 1]
    bm[:, 2] = s0[:, 1] + s1[:, 0]
    bm[:, 3] = s0[:, 1] + s1[:, 1]

    prev, u_in, out_idx = _trellis()
    pm = np.full(N_STATES, -1e18)
    pm[0] = 0.0
    decisions = np.empty((n_total, N_STATES), dtype=np.uint8)
    rows = np.arange(N_STATES)
    for t in range(n_total):
        cand = pm[prev] + bm[t][out_idx]  # (64, 2)
        choice = cand[:, 1] > cand[:, 0]
        pm = cand[rows, choice.astype(np.int64)]
        decisions[t] = choice
        # keep metrics bounded
        pm -= pm.max()
    # traceback from the zero state (terminated code)
    out = np.empty(n_total, dtype=np.uint8)
    s = 0
    for t in range(n_total - 1, -1, -1):
        out[t] = u_in[s]
        s = prev[s, decisions[t, s]]
    return out[:n_info_bits]
