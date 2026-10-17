"""Bit <-> carrier mapping with per-carrier modulation (bit loading).

Bits are consumed in carrier order: carrier 0 takes the first ``b_0`` bits,
carrier 1 the next ``b_1`` bits, and so on, where ``b_k`` is the number of
bits the carrier's modulation carries. The receiver reproduces the same
order when it lays out LLRs, so the FEC decoder sees a continuous stream.
"""

from __future__ import annotations

import numpy as np

from sonic.config import OFDMConfig
from sonic.modulation import demodulate_hard, demodulate_soft, modulate


def _layout(cfg: OFDMConfig):
    bpc = cfg.bits_per_data_carrier
    enabled = bpc > 0
    mods = [m for m, e in zip(cfg.data_carrier_modulations, enabled) if e]
    bits = bpc[enabled]
    offsets = np.concatenate([[0], np.cumsum(bits)[:-1]])
    groups: dict[str, np.ndarray] = {}
    for i, m in enumerate(mods):
        groups.setdefault(m, []).append(i)
    return bits, offsets, {m: np.array(idx) for m, idx in groups.items()}


def pad_bits(bits: np.ndarray, bits_per_symbol: int, rng: np.random.Generator) -> np.ndarray:
    pad = (-bits.size) % bits_per_symbol
    if pad:
        bits = np.concatenate([bits, rng.integers(0, 2, pad).astype(np.uint8)])
    return bits


def bits_to_data_symbols(cfg: OFDMConfig, bits: np.ndarray) -> np.ndarray:
    """``bits`` length must be a multiple of ``cfg.bits_per_ofdm_symbol``."""
    B = cfg.bits_per_ofdm_symbol
    bits = np.asarray(bits, dtype=np.uint8)
    if bits.size % B:
        raise ValueError("bit count must be a multiple of bits_per_ofdm_symbol")
    n_sym = bits.size // B
    rows = bits.reshape(n_sym, B)
    per_carrier_bits, offsets, groups = _layout(cfg)
    out = np.empty((n_sym, len(per_carrier_bits)), dtype=np.complex128)
    for mod, idx in groups.items():
        b = int(per_carrier_bits[idx[0]])
        cols = offsets[idx][:, None] + np.arange(b)[None, :]  # (n_c, b)
        chunk = rows[:, cols]  # (n_sym, n_c, b)
        out[:, idx] = modulate(chunk.reshape(-1), mod).reshape(n_sym, len(idx))
    return out


def data_symbols_to_llr(cfg: OFDMConfig, symbols: np.ndarray, noise_var: np.ndarray | float) -> np.ndarray:
    """Soft demap ``(n_sym, n_enabled)`` equalised symbols to a flat LLR array.

    ``noise_var`` may be a scalar, a per-carrier array ``(n_enabled,)`` or a
    per-symbol-per-carrier array ``(n_sym, n_enabled)``.
    """
    symbols = np.atleast_2d(symbols)
    n_sym = symbols.shape[0]
    per_carrier_bits, offsets, groups = _layout(cfg)
    B = int(per_carrier_bits.sum())
    nv = np.broadcast_to(np.asarray(noise_var, dtype=np.float64), symbols.shape)
    out = np.empty((n_sym, B))
    for mod, idx in groups.items():
        b = int(per_carrier_bits[idx[0]])
        cols = offsets[idx][:, None] + np.arange(b)[None, :]
        llr = demodulate_soft(symbols[:, idx].reshape(-1), mod, nv[:, idx].reshape(-1))
        out[:, cols] = llr.reshape(n_sym, len(idx), b)
    return out.reshape(-1)


def data_symbols_to_hard_bits(cfg: OFDMConfig, symbols: np.ndarray) -> np.ndarray:
    symbols = np.atleast_2d(symbols)
    n_sym = symbols.shape[0]
    per_carrier_bits, offsets, groups = _layout(cfg)
    B = int(per_carrier_bits.sum())
    out = np.empty((n_sym, B), dtype=np.uint8)
    for mod, idx in groups.items():
        b = int(per_carrier_bits[idx[0]])
        cols = offsets[idx][:, None] + np.arange(b)[None, :]
        hb = demodulate_hard(symbols[:, idx].reshape(-1), mod)
        out[:, cols] = hb.reshape(n_sym, len(idx), b)
    return out.reshape(-1)
