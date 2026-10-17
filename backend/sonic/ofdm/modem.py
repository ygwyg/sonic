"""OFDM symbol generation and recovery.

Transmit side
    frequency-domain carriers -> conjugate-symmetric spectrum -> IFFT ->
    real-valued time samples -> cyclic prefix.

Receive side
    time window (after the cyclic prefix) -> FFT -> active carriers.

Because audio is real-valued, only bins ``1 .. n_fft/2 - 1`` are usable;
the IFFT of a Hermitian spectrum gives the real waveform directly via
``numpy.fft.irfft``. The DC bin and the Nyquist bin are always zero.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from sonic.config import OFDMConfig

PILOT_SEED = 0x9E3779B9
TRAINING_SEED = 0x7F4A7C15


@lru_cache(maxsize=32)
def pilot_values(n_pilots: int) -> np.ndarray:
    """Known BPSK pilot values (deterministic pseudo-random)."""
    rng = np.random.default_rng(PILOT_SEED + n_pilots)
    return (1 - 2 * rng.integers(0, 2, n_pilots)).astype(np.complex128)


@lru_cache(maxsize=64)
def training_values(n_active: int, index: int = 0) -> np.ndarray:
    """Known BPSK training symbol ``index`` on all active carriers.

    Consecutive training symbols use *different* sequences so that
    inter-symbol interference from a too-short cyclic prefix shows up in
    the noise estimate instead of masquerading as signal.
    """
    rng = np.random.default_rng(TRAINING_SEED + 1000003 * index + n_active)
    return (1 - 2 * rng.integers(0, 2, n_active)).astype(np.complex128)


def carriers_to_time(cfg: OFDMConfig, spectrum_rows: np.ndarray, carriers: np.ndarray) -> np.ndarray:
    """Map ``(n_symbols, len(carriers))`` complex values to time samples.

    Returns ``(n_symbols, n_fft + cp_len)`` real samples including the
    cyclic prefix. The IFFT is scaled so each unit-energy carrier produces
    a sinusoid of amplitude ``2 / sqrt(n_fft)``-ish; a global amplitude
    normalisation is applied later by the transmitter.
    """
    spectrum_rows = np.atleast_2d(spectrum_rows)
    n_sym = spectrum_rows.shape[0]
    half = np.zeros((n_sym, cfg.n_fft // 2 + 1), dtype=np.complex128)
    half[:, carriers] = spectrum_rows
    x = np.fft.irfft(half, n=cfg.n_fft, axis=1) * np.sqrt(cfg.n_fft)
    if cfg.cp_len:
        x = np.concatenate([x[:, -cfg.cp_len :], x], axis=1)
    return x


def time_to_carriers(cfg: OFDMConfig, samples: np.ndarray, carriers: np.ndarray) -> np.ndarray:
    """FFT of ``(n_symbols, n_fft)`` windows (CP already removed)."""
    samples = np.atleast_2d(samples)
    spec = np.fft.rfft(samples, n=cfg.n_fft, axis=1) / np.sqrt(cfg.n_fft)
    return spec[:, carriers]


def build_symbols(cfg: OFDMConfig, data_symbols: np.ndarray) -> np.ndarray:
    """Assemble full active-carrier rows from data symbols plus pilots.

    ``data_symbols`` has shape ``(n_symbols, n_enabled_data_carriers)``.
    Disabled carriers are left at zero.
    """
    data_symbols = np.atleast_2d(data_symbols)
    n_sym = data_symbols.shape[0]
    n_active = len(cfg.active_carriers)
    rows = np.zeros((n_sym, n_active), dtype=np.complex128)
    pilot_pos = np.arange(n_active)[:: cfg.pilot_spacing]
    rows[:, pilot_pos] = pilot_values(len(pilot_pos))[None, :]
    data_pos = np.setdiff1d(np.arange(n_active), pilot_pos)
    enabled = cfg.bits_per_data_carrier > 0
    rows[:, data_pos[enabled]] = data_symbols
    return rows


def training_rows(cfg: OFDMConfig) -> np.ndarray:
    n = len(cfg.active_carriers)
    return np.stack([training_values(n, i) for i in range(cfg.n_training)], axis=0)


def active_positions(cfg: OFDMConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Index helpers into the active-carrier axis.

    Returns ``(pilot_pos, data_pos, enabled_data_pos)``.
    """
    n_active = len(cfg.active_carriers)
    pilot_pos = np.arange(n_active)[:: cfg.pilot_spacing]
    data_pos = np.setdiff1d(np.arange(n_active), pilot_pos)
    enabled = cfg.bits_per_data_carrier > 0
    return pilot_pos, data_pos, data_pos[enabled]


def papr_db(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return 0.0
    p_avg = np.mean(x**2)
    if p_avg <= 0:
        return 0.0
    return float(10 * np.log10(np.max(x**2) / p_avg))
