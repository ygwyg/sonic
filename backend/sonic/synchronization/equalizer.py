"""Channel estimation, equalisation and pilot-based tracking for one
section of OFDM symbols (the header section or the payload section).

Per section:

1. ``n_training`` known symbols give the channel estimate ``H`` per
   carrier and (with >= 2 training symbols) a per-carrier noise estimate.
2. The linear phase slope of ``H`` reveals whether the FFT window starts
   *after* the true symbol start (which would cause inter-symbol
   interference); if so the window is moved earlier and ``H`` re-estimated.
3. Each data symbol is zero-forcing equalised, then the pilots give a
   common phase, a residual timing slope and an amplitude gain which are
   removed. The slope is integrated into a timing-drift estimate; whenever
   it exceeds half a sample the window is shifted by an integer number of
   samples so that sample-rate mismatch does not walk the window out of the
   cyclic prefix.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sonic.config import OFDMConfig
from sonic.ofdm.modem import active_positions, pilot_values, time_to_carriers, training_values


class SectionError(ValueError):
    pass


class _DriftTracker:
    """Incremental least-squares line fit of timing offset versus symbol index.

    Sample-rate mismatch produces a timing offset that grows linearly with
    time, so a straight line through *all* measurements so far is the
    right model and averages away the per-symbol estimation noise.
    """

    def __init__(self) -> None:
        self.n = 0
        self.sx = self.sy = self.sxx = self.sxy = self.syy = 0.0

    def update(self, x: float, y: float) -> None:
        self.n += 1
        self.sx += x
        self.sy += y
        self.sxx += x * x
        self.sxy += x * y
        self.syy += y * y

    def predict(self, x: float) -> tuple[float, float]:
        """Return (predicted offset, estimated std of that prediction)."""
        if self.n == 0:
            return 0.0, float("inf")
        if self.n < 3:
            return self.sy / self.n, float("inf")
        n = self.n
        den = n * self.sxx - self.sx * self.sx
        if den <= 1e-12:
            return self.sy / n, float("inf")
        slope = (n * self.sxy - self.sx * self.sy) / den
        icpt = (self.sy - slope * self.sx) / n
        pred = icpt + slope * x
        # residual variance and prediction variance of the fitted line
        ss_res = max(self.syy - icpt * self.sy - slope * self.sxy, 0.0)
        var_res = ss_res / max(n - 2, 1)
        xm = self.sx / n
        var_pred = var_res * (1.0 / n + (x - xm) ** 2 * n / den)
        return float(pred), float(np.sqrt(var_pred))


@dataclass
class SectionResult:
    symbols: np.ndarray  # (n_sym, n_enabled_data) equalised data symbols
    noise_var: np.ndarray  # (n_sym, n_enabled_data) complex noise variance estimate
    channel: np.ndarray  # (n_active,) channel estimate H
    snr_training_db: np.ndarray  # (n_active,)
    snr_evm_db: np.ndarray | None  # (n_enabled_data,) decision-directed estimate
    start: int  # window start actually used (after refinement)
    timing_refine: int  # samples the window was moved earlier
    drift_samples: list[float] = field(default_factory=list)
    symbol_noise: list[float] = field(default_factory=list)
    phase_track: list[float] = field(default_factory=list)
    gain_track: list[float] = field(default_factory=list)
    n_symbols_available: int = 0
    n_symbols_requested: int = 0

    @property
    def truncated(self) -> bool:
        return self.n_symbols_available < self.n_symbols_requested


def _windows(samples: np.ndarray, start: int, cfg: OFDMConfig, n: int) -> np.ndarray:
    """Stack ``n`` FFT windows (CP skipped) beginning at ``start``."""
    L = cfg.symbol_len
    idx = start + cfg.cp_len + np.arange(n)[:, None] * L + np.arange(cfg.n_fft)[None, :]
    return samples[idx]


def estimate_channel(samples: np.ndarray, start: int, cfg: OFDMConfig):
    n_t = cfg.n_training
    end = start + n_t * cfg.symbol_len
    if start < 0 or end > samples.size:
        raise SectionError("recording too short for training symbols")
    Y = time_to_carriers(cfg, _windows(samples, start, cfg, n_t), cfg.active_carriers)
    n_active = len(cfg.active_carriers)
    T = np.stack([training_values(n_active, i) for i in range(n_t)], axis=0)
    Hi = Y / T  # per-training-symbol channel estimates (|T| = 1)
    H = Hi.mean(axis=0)
    if n_t >= 2:
        nv = (np.abs(Hi - H[None, :]) ** 2).sum(axis=0) / (n_t - 1)
    else:
        nv = np.full(H.shape, np.nan)
    return H, nv


def group_delay_samples(H: np.ndarray, carriers: np.ndarray, n_fft: int) -> float:
    """Average delay (samples) implied by the phase slope of H.

    Positive means the signal arrives *after* the window start (safe);
    negative means the window starts late.
    """
    # Active carriers are a contiguous bin range, so adjacent products give
    # the phase advance per bin directly.
    prod = H[1:] * np.conj(H[:-1])
    if not np.any(np.abs(prod)):
        return 0.0
    slope = float(np.angle(np.sum(prod)))
    return float(-slope * n_fft / (2 * np.pi))


def demodulate_section(
    samples: np.ndarray,
    start: int,
    cfg: OFDMConfig,
    n_data_symbols: int,
    refine_timing: bool = True,
) -> SectionResult:
    """Equalise ``n_data_symbols`` data symbols that follow the training."""
    samples = np.asarray(samples, dtype=np.float64)
    H, nv_active = estimate_channel(samples, start, cfg)
    refine = 0
    if refine_timing and cfg.cp_len > 0:
        gd = group_delay_samples(H, cfg.active_carriers, cfg.n_fft)
        if gd < -1.0:
            # window starts after the symbol: move it earlier (into the CP)
            refine = int(min(np.ceil(-gd) + 2, cfg.cp_len // 2, start))
            if refine > 0:
                start -= refine
                H, nv_active = estimate_channel(samples, start, cfg)
    pilot_pos, data_pos, enabled_pos = active_positions(cfg)
    P = pilot_values(len(pilot_pos))
    k_all = cfg.active_carriers.astype(np.float64)
    k_pil = k_all[pilot_pos]
    k_en = k_all[enabled_pos]
    H_safe = np.where(np.abs(H) < 1e-9, 1e-9, H)
    sig_power = np.abs(H) ** 2
    nv_floor = np.maximum(np.nanmax(sig_power) * 1e-6, 1e-12)
    if np.all(np.isnan(nv_active)):
        nv_est = np.full(H.shape, np.nan)
    else:
        nv_est = np.maximum(nv_active, nv_floor)
    snr_training = 10 * np.log10(np.maximum(sig_power, 1e-18) / np.where(np.isnan(nv_est), np.nan, nv_est))

    data_start = start + cfg.n_training * cfg.symbol_len
    L = cfg.symbol_len
    n_avail = max(0, (samples.size - data_start) // L)
    n_avail = min(n_avail, n_data_symbols)
    out = np.zeros((n_avail, len(enabled_pos)), dtype=np.complex128)
    drift, phases, gains, sym_noise = [], [], [], []
    if np.all(np.isnan(nv_est)):
        nv_eq = None
    else:
        nv_eq = _smooth(nv_est / np.maximum(sig_power, 1e-18), 9)  # noise var after ZF
    spacing = cfg.pilot_spacing
    if nv_eq is None:
        w_pil = sig_power[pilot_pos]
    else:
        nvp = nv_eq[pilot_pos]
        # cap the weight spread: a two-sample noise estimate is far too
        # uncertain to let any single pilot dominate the fit
        w_pil = 1.0 / np.maximum(nvp, 0.25 * np.median(nvp))
    w_pil = w_pil / max(np.sum(w_pil), 1e-12)
    tracker = _DriftTracker()
    shift = 0  # integer samples the window has been moved later
    b_prev = 0.0
    for i in range(n_avail):
        # predicted timing for this symbol from the regression over all
        # previous symbols; the window follows it in whole samples
        tau_pred, tau_sigma = tracker.predict(i)
        if abs(tau_pred - shift) >= 0.5:
            step = int(np.round(tau_pred)) - shift
            shift += step
            # the window moved, so the slope relative to it changes too
            b_prev += 2 * np.pi * step / cfg.n_fft
        s = data_start + i * L + shift
        if s + cfg.cp_len + cfg.n_fft > samples.size or s < 0:
            out = out[:i]
            break
        win = samples[s + cfg.cp_len : s + cfg.cp_len + cfg.n_fft]
        Y = np.fft.rfft(win) / np.sqrt(cfg.n_fft)
        Y = Y[cfg.active_carriers]
        Z = Y / H_safe
        r = Z[pilot_pos] * np.conj(P)
        b_meas, a_meas = _pilot_phase_fit(r, k_pil, spacing, w_pil, b_seed=b_prev)
        tau_meas = -b_meas * cfg.n_fft / (2 * np.pi)  # samples; >0 signal arrives later
        tracker.update(i, tau_meas + shift)
        # Use the smoothed regression once it is demonstrably accurate,
        # otherwise the per-symbol least-squares estimate.
        if tracker.n >= 8 and tau_sigma < 0.15:
            b_used = -2 * np.pi * (tau_pred - shift) / cfg.n_fft
        else:
            b_used = b_meas
        r_flat = r * np.exp(-1j * b_used * k_pil)
        a = float(np.angle(np.sum(w_pil * r_flat / np.maximum(np.abs(r_flat), 1e-12))))
        g = float(np.sum(w_pil * np.abs(r)))
        if g < 1e-9:
            g = 1e-9
        corr_pil = np.exp(-1j * (a + b_used * k_pil)) / g
        sym_noise.append(float(np.mean(np.abs(r * corr_pil - 1.0) ** 2)))
        corr = np.exp(-1j * (a + b_used * k_en)) / g
        out[i] = Z[enabled_pos] * corr
        b_prev = b_used
        drift.append(float(tau_meas + shift))
        phases.append(a)
        gains.append(g)
    if out.shape[0] != n_avail:
        n_avail = out.shape[0]
    # noise per enabled data carrier for soft demapping
    if nv_eq is None:
        base = _evm_noise(out, cfg)
        if base is None:
            base = np.full(len(enabled_pos), 0.1)
        nv_data = np.tile(base[None, :], (n_avail, 1))
    else:
        base = nv_eq[enabled_pos]
        ref = float(np.mean(nv_eq[pilot_pos]))
        # per-symbol scaling from pilot residuals discounts symbols hit by
        # bursts or clicks that the training-based estimate cannot see
        scale = np.clip(np.asarray(sym_noise) / max(ref, 1e-12), 0.3, 1e4) if sym_noise else np.ones(0)
        nv_data = base[None, :] * scale[:, None]
    snr_evm = None
    if out.shape[0] > 0:
        e = _evm_noise(out, cfg)
        if e is not None:
            snr_evm = 10 * np.log10(1.0 / np.maximum(e, 1e-12))
    return SectionResult(
        symbols=out,
        noise_var=np.maximum(nv_data, 1e-9),
        channel=H,
        snr_training_db=snr_training,
        snr_evm_db=snr_evm,
        start=start,
        timing_refine=refine,
        drift_samples=drift,
        symbol_noise=sym_noise,
        phase_track=phases,
        gain_track=gains,
        n_symbols_available=n_avail,
        n_symbols_requested=n_data_symbols,
    )


def _pilot_phase_fit(
    r: np.ndarray, k: np.ndarray, spacing: int, w: np.ndarray, b_seed: float = 0.0
) -> tuple[float, float]:
    """Weighted least-squares fit ``angle(r) ~ a + b*k`` over the pilots.

    ``w`` weights each pilot by its SNR so pilots sitting in channel
    notches (where zero-forcing amplifies noise) do not dominate. The fit
    is seeded with ``b_seed`` (the previous symbol's slope: timing drifts
    by well under a sample per symbol, so residual phases are small and
    need no unwrapping). Two refinement passes absorb moderate residuals;
    if the residual still implies a wrap the coarse adjacent-pilot
    estimate is used as the seed instead.
    """
    unit = r / np.maximum(np.abs(r), 1e-12)
    span = float(k[-1] - k[0]) if k.size > 1 else 1.0
    sw = max(float(np.sum(w)), 1e-12)
    km = float(np.sum(w * k) / sw)
    den = float(np.sum(w * (k - km) ** 2))

    def refine(b: float) -> float:
        for _ in range(2):
            phi = np.angle(unit * np.exp(-1j * b * k))
            pm = np.sum(w * phi) / sw
            db = float(np.sum(w * (k - km) * (phi - pm)) / den) if den > 0 else 0.0
            b += db
        return b

    b = refine(b_seed)
    # sanity: residual phase spread must be small, otherwise re-seed coarsely
    phi = np.angle(unit * np.exp(-1j * b * k))
    if np.sum(w * np.abs(phi)) / sw > 1.0:
        wp = np.minimum(w[1:], w[:-1])
        prod = unit[1:] * np.conj(unit[:-1]) * wp
        b = refine(float(np.angle(np.sum(prod))) / spacing)
    a = float(np.angle(np.sum(w * unit * np.exp(-1j * b * k))))
    return b, a


def _smooth(x: np.ndarray, w: int) -> np.ndarray:
    if x.size < w:
        return x
    k = np.ones(w) / w
    pad = np.pad(x, (w // 2, w // 2), mode="edge")
    return np.convolve(pad, k, mode="valid")[: x.size]


def _evm_noise(symbols: np.ndarray, cfg: OFDMConfig) -> np.ndarray | None:
    """Decision-directed noise variance per enabled data carrier."""
    from sonic.ofdm.mapping import _layout
    from sonic.modulation import demodulate_hard, modulate

    if symbols.shape[0] == 0:
        return None
    per_bits, offsets, groups = _layout(cfg)
    nv = np.zeros(symbols.shape[1])
    for mod, idx in groups.items():
        y = symbols[:, idx].reshape(-1)
        nearest = modulate(demodulate_hard(y, mod), mod)
        nv[idx] = (np.abs(y - nearest) ** 2).reshape(symbols.shape[0], len(idx)).mean(axis=0)
    return nv
