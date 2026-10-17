"""Waveform analysis for the explorer and the ``sonic analyze`` command.

Everything here is derived from actual samples (and, when available, the
transmission's own layout) so the dashboard shows what was really
generated or received, not a cartoon of it.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from scipy.signal import spectrogram as _spectrogram

from sonic.config import OFDMConfig, header_config
from sonic.ofdm import active_positions, papr_db, time_to_carriers
from sonic.ofdm.modem import pilot_values


def _downsample_minmax(x: np.ndarray, n_points: int) -> dict:
    """Min/max envelope so long waveforms plot faithfully at low resolution."""
    x = np.asarray(x, dtype=np.float64)
    if x.size <= n_points:
        idx = np.arange(x.size)
        return {"index": idx.tolist(), "min": x.tolist(), "max": x.tolist()}
    step = int(np.ceil(x.size / n_points))
    pad = (-x.size) % step
    xp = np.concatenate([x, np.full(pad, np.nan)]).reshape(-1, step)
    return {
        "index": (np.arange(xp.shape[0]) * step).tolist(),
        "min": np.nan_to_num(np.nanmin(xp, axis=1)).round(5).tolist(),
        "max": np.nan_to_num(np.nanmax(xp, axis=1)).round(5).tolist(),
    }


def waveform_summary(x: np.ndarray, fs: int, n_points: int = 2000) -> dict:
    x = np.asarray(x, dtype=np.float64)
    env = _downsample_minmax(x, n_points)
    return {
        "sample_rate": fs,
        "n_samples": int(x.size),
        "duration_s": x.size / fs,
        "peak": float(np.max(np.abs(x))) if x.size else 0.0,
        "rms": float(np.sqrt(np.mean(x**2))) if x.size else 0.0,
        "papr_db": papr_db(x),
        "envelope": env,
    }


def spectrum(x: np.ndarray, fs: int, n_fft: int = 8192, max_points: int = 2048) -> dict:
    """Welch-style averaged power spectrum in dB (relative to full scale)."""
    x = np.asarray(x, dtype=np.float64)
    if x.size < n_fft:
        n_fft = max(64, 1 << int(np.floor(np.log2(max(x.size, 64)))))
    hop = n_fft // 2
    win = np.hanning(n_fft)
    n_frames = max(1, (x.size - n_fft) // hop + 1)
    acc = np.zeros(n_fft // 2 + 1)
    for i in range(n_frames):
        seg = x[i * hop : i * hop + n_fft]
        if seg.size < n_fft:
            seg = np.pad(seg, (0, n_fft - seg.size))
        acc += np.abs(np.fft.rfft(seg * win)) ** 2
    acc /= n_frames * np.sum(win**2)
    f = np.fft.rfftfreq(n_fft, 1 / fs)
    db = 10 * np.log10(np.maximum(acc, 1e-20))
    if f.size > max_points:
        step = int(np.ceil(f.size / max_points))
        f, db = f[::step], db[::step]
    return {"frequency_hz": f.round(2).tolist(), "power_db": db.round(2).tolist()}


def spectrogram_image(
    x: np.ndarray, fs: int, n_fft: int = 1024, max_cols: int = 400, max_rows: int = 256, f_max: Optional[float] = None
) -> dict:
    x = np.asarray(x, dtype=np.float64)
    if x.size < n_fft:
        x = np.pad(x, (0, n_fft - x.size))
    f, t, S = _spectrogram(x, fs=fs, nperseg=n_fft, noverlap=n_fft // 2, scaling="spectrum", mode="magnitude")
    db = 20 * np.log10(np.maximum(S, 1e-10))
    if f_max:
        keep = f <= f_max
        f, db = f[keep], db[keep]
    if db.shape[1] > max_cols:
        step = int(np.ceil(db.shape[1] / max_cols))
        db = db[:, ::step]
        t = t[::step]
    if db.shape[0] > max_rows:
        step = int(np.ceil(db.shape[0] / max_rows))
        db = db[::step]
        f = f[::step]
    vmax = float(np.max(db))
    vmin = vmax - 80
    return {
        "time_s": t.round(4).tolist(),
        "frequency_hz": f.round(1).tolist(),
        "db": np.clip(db, vmin, vmax).round(1).tolist(),
        "db_min": vmin,
        "db_max": vmax,
    }


def carrier_allocation(cfg: OFDMConfig) -> dict:
    pilot_pos, data_pos, enabled_pos = active_positions(cfg)
    carriers = cfg.active_carriers
    mods = cfg.data_carrier_modulations
    roles = []
    for i in range(len(carriers)):
        roles.append("pilot")
    for j, pos in enumerate(data_pos):
        roles[pos] = mods[j] or "disabled"
    return {
        "n_fft": cfg.n_fft,
        "carrier_spacing_hz": cfg.carrier_spacing,
        "carriers": carriers.tolist(),
        "frequencies_hz": (carriers * cfg.carrier_spacing).round(2).tolist(),
        "roles": roles,
        "pilot_carriers": cfg.pilot_carriers.tolist(),
        "n_data": int(len(data_pos)),
        "n_pilot": int(len(pilot_pos)),
        "guard_low_hz": float(carriers[0] * cfg.carrier_spacing),
        "guard_high_hz": float(cfg.sample_rate / 2 - carriers[-1] * cfg.carrier_spacing),
        "bits_per_symbol": cfg.bits_per_ofdm_symbol,
    }


def overlapping_carriers_demo(cfg: OFDMConfig, symbol_samples: np.ndarray, n_show: int = 8) -> dict:
    """Decompose one OFDM symbol into its individual carrier sinusoids.

    This is the "see the overlapping waves" view: the FFT of the symbol
    gives every carrier's complex amplitude; each carrier is rebuilt as a
    time-domain sinusoid so the viewer can watch them sum into the symbol
    and separate again.
    """
    win = np.asarray(symbol_samples[cfg.cp_len : cfg.cp_len + cfg.n_fft], dtype=np.float64)
    X = np.fft.rfft(win) / np.sqrt(cfg.n_fft)
    carriers = cfg.active_carriers
    mags = np.abs(X[carriers])
    order = np.argsort(-mags)[:n_show]
    n = np.arange(cfg.n_fft)
    comps = []
    for j in sorted(order):
        k = int(carriers[j])
        c = X[k]
        wave = 2 * np.abs(c) * np.cos(2 * np.pi * k * n / cfg.n_fft + np.angle(c)) / np.sqrt(cfg.n_fft)
        comps.append(
            {
                "carrier": k,
                "frequency_hz": k * cfg.carrier_spacing,
                "magnitude": float(np.abs(c)),
                "phase_rad": float(np.angle(c)),
                "samples": wave[: min(cfg.n_fft, 512)].round(5).tolist(),
            }
        )
    return {
        "n_fft": cfg.n_fft,
        "shown": len(comps),
        "n_total_carriers": int(len(carriers)),
        "composite": win[: min(cfg.n_fft, 512)].round(5).tolist(),
        "components": comps,
        "carrier_magnitudes": mags.round(5).tolist(),
        "carrier_phases": np.angle(X[carriers]).round(4).tolist(),
        "carrier_frequencies_hz": (carriers * cfg.carrier_spacing).round(2).tolist(),
    }


def analyze_waveform(x: np.ndarray, fs: int, info=None) -> dict:
    """Full explorer payload for a generated (or received) waveform."""
    out = {
        "waveform": waveform_summary(x, fs),
        "spectrum": spectrum(x, fs),
        "spectrogram": spectrogram_image(x, fs, f_max=min(fs / 2, 24000)),
    }
    if info is not None:
        cfg = info.config
        out["allocation"] = carrier_allocation(cfg)
        out["header_allocation"] = carrier_allocation(header_config(fs))
        out["sections"] = info.layout.sections()
        # the first payload data symbol (after training) shows overlapping carriers
        sec = next(s for s in info.layout.sections() if s["name"] == "payload_data")
        if sec["end"] - sec["start"] >= cfg.symbol_len:
            out["carriers_demo"] = overlapping_carriers_demo(cfg, x[sec["start"] : sec["start"] + cfg.symbol_len])
        ds = np.asarray(info.data_symbols).reshape(-1)
        step = max(1, ds.size // 4000)
        ds = ds[::step]
        out["constellation_tx"] = {"re": ds.real.round(4).tolist(), "im": ds.imag.round(4).tolist()}
        out["power"] = _power_distribution(x, fs, info)
    return out


def _power_distribution(x: np.ndarray, fs: int, info) -> dict:
    """Energy per section and per active carrier in the payload."""
    sections = {}
    for s in info.layout.sections():
        seg = x[s["start"] : s["end"]]
        sections[s["name"]] = float(np.sum(seg**2)) if seg.size else 0.0
    total = max(sum(sections.values()), 1e-12)
    cfg = info.config
    sec = next(s for s in info.layout.sections() if s["name"] == "payload_data")
    n_sym = (sec["end"] - sec["start"]) // cfg.symbol_len
    per_carrier = None
    if n_sym > 0:
        n_use = min(n_sym, 64)
        idx = sec["start"] + cfg.cp_len + np.arange(n_use)[:, None] * cfg.symbol_len + np.arange(cfg.n_fft)[None, :]
        Y = time_to_carriers(cfg, x[idx], cfg.active_carriers)
        per_carrier = (np.mean(np.abs(Y) ** 2, axis=0)).round(8).tolist()
    return {
        "section_energy_fraction": {k: v / total for k, v in sections.items()},
        "per_carrier_power": per_carrier,
        "carrier_frequencies_hz": (cfg.active_carriers * cfg.carrier_spacing).round(2).tolist(),
    }
