"""Synthetic acoustic channel simulator.

**These are synthetic channel models, not validated replicas of real
rooms.** They exist so that different encoding schemes can be compared
under identical, reproducible impairments.

Impairment order (fixed so results are reproducible and comparable):

1. multipath / reverberation (linear filtering)
2. frequency-selective response (tilt, notches, band limits)
3. sample-rate mismatch (band-limited resampling)
4. frequency offset (analytic-signal shift)
5. timing offset (leading/trailing silence)
6. narrowband and broadband interference
7. additive white Gaussian noise at the requested SNR
8. clipping

SNR is defined as the ratio of received *signal* power (after steps 1--4,
measured over the signal's extent) to white-noise power over the full
Nyquist band. Interference is not counted in the SNR.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np
from scipy.signal import butter, fftconvolve, hilbert, resample, sosfilt


@dataclass
class ChannelConfig:
    name: str = "custom"
    snr_db: Optional[float] = None
    multipath: list[tuple[float, float]] = field(default_factory=list)  # (delay s, gain)
    reverb_rt60_s: float = 0.0
    reverb_level: float = 0.0  # tail amplitude relative to direct path
    tilt_db_per_khz: float = 0.0
    notches: list[tuple[float, float, float]] = field(default_factory=list)  # (f Hz, depth dB, width Hz)
    lowpass_hz: Optional[float] = None
    highpass_hz: Optional[float] = None
    sample_rate_ppm: float = 0.0
    frequency_offset_hz: float = 0.0
    timing_offset_s: float = 0.0
    tones: list[tuple[float, float]] = field(default_factory=list)  # (f Hz, amplitude rel. to signal rms)
    burst_level_db: Optional[float] = None  # broadband bursts relative to signal power
    burst_duty: float = 0.0
    burst_len_s: float = 0.05
    clip_level: Optional[float] = None
    seed: int = 0

    def describe(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ChannelConfig":
        kw = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        for key in ("multipath", "notches", "tones"):
            if key in kw and kw[key] is not None:
                kw[key] = [tuple(t) for t in kw[key]]
        return cls(**kw)


def _impulse_response(cfg: ChannelConfig, fs: int, rng: np.random.Generator) -> Optional[np.ndarray]:
    taps = [(0.0, 1.0)] + list(cfg.multipath)
    max_delay = max(d for d, _ in taps)
    n_rev = int(cfg.reverb_rt60_s * fs) if cfg.reverb_rt60_s > 0 and cfg.reverb_level > 0 else 0
    n = int(max_delay * fs) + 1 + n_rev
    if n <= 1 and n_rev == 0 and len(taps) == 1:
        return None
    h = np.zeros(max(n, 1))
    for d, g in taps:
        h[int(round(d * fs))] += g
    if n_rev:
        tau = cfg.reverb_rt60_s / np.log(1000.0)
        t = np.arange(n_rev) / fs
        tail = rng.normal(size=n_rev) * np.exp(-t / tau)
        # reverb_level = total tail energy relative to the direct path, so
        # a level of 0.1 corresponds to a direct-to-reverberant ratio of 10 dB
        tail *= np.sqrt(cfg.reverb_level / max(np.sum(tail**2), 1e-12))
        h[1 : n_rev + 1] += tail[: len(h) - 1]
    return h


def _frequency_response(x: np.ndarray, cfg: ChannelConfig, fs: int) -> np.ndarray:
    if not (cfg.tilt_db_per_khz or cfg.notches or cfg.lowpass_hz or cfg.highpass_hz):
        return x
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(x.size, 1 / fs)
    gain_db = cfg.tilt_db_per_khz * (f / 1000.0)
    for f0, depth, width in cfg.notches:
        gain_db -= depth * np.exp(-0.5 * ((f - f0) / max(width, 1.0)) ** 2)
    g = 10 ** (gain_db / 20)
    y = np.fft.irfft(X * g, n=x.size)
    if cfg.lowpass_hz:
        sos = butter(4, cfg.lowpass_hz / (fs / 2), btype="low", output="sos")
        y = sosfilt(sos, y)
    if cfg.highpass_hz:
        sos = butter(2, cfg.highpass_hz / (fs / 2), btype="high", output="sos")
        y = sosfilt(sos, y)
    return y


def apply_channel(x: np.ndarray, fs: int, cfg: ChannelConfig) -> np.ndarray:
    """Pass ``x`` through the synthetic channel and return the received audio."""
    rng = np.random.default_rng(cfg.seed)
    y = np.asarray(x, dtype=np.float64).copy()
    n_orig = y.size

    h = _impulse_response(cfg, fs, rng)
    if h is not None:
        y = fftconvolve(y, h)[: n_orig + len(h)]
    y = _frequency_response(y, cfg, fs)
    if cfg.sample_rate_ppm:
        n_new = int(round(y.size * (1 + cfg.sample_rate_ppm * 1e-6)))
        y = resample(y, n_new)
    if cfg.frequency_offset_hz:
        t = np.arange(y.size) / fs
        y = np.real(hilbert(y) * np.exp(2j * np.pi * cfg.frequency_offset_hz * t))

    sig_power = float(np.mean(y[:n_orig] ** 2)) if n_orig else 0.0
    sig_rms = np.sqrt(sig_power)

    if cfg.timing_offset_s:
        lead = np.zeros(int(round(abs(cfg.timing_offset_s) * fs)))
        y = np.concatenate([lead, y, lead[: len(lead) // 4]])

    t = np.arange(y.size) / fs
    for f0, amp in cfg.tones:
        y = y + amp * sig_rms * np.sqrt(2) * np.sin(2 * np.pi * f0 * t + rng.uniform(0, 2 * np.pi))
    if cfg.burst_level_db is not None and cfg.burst_duty > 0:
        burst_rms = sig_rms * 10 ** (cfg.burst_level_db / 20)
        L = max(1, int(cfg.burst_len_s * fs))
        n_bursts = int(cfg.burst_duty * y.size / L)
        for _ in range(n_bursts):
            s = int(rng.integers(0, max(1, y.size - L)))
            y[s : s + L] += rng.normal(0, burst_rms, L)
    if cfg.snr_db is not None:
        noise_rms = sig_rms * 10 ** (-cfg.snr_db / 20)
        y = y + rng.normal(0.0, noise_rms, y.size)
    if cfg.clip_level is not None:
        y = np.clip(y, -cfg.clip_level, cfg.clip_level)
    return y
