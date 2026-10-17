"""Deterministic adaptive bit loading.

Given a per-carrier SNR estimate (fed back from a receiver), choose a
modulation per carrier band and a common code rate that maximise the
expected useful throughput subject to a reliability target.

The algorithm is deliberately conventional and explainable:

1. Split the data carriers into ``n_bands`` contiguous bands (the header
   can signal up to 16 bands; this is the granularity the receiver learns).
2. For each band compute an *effective* SNR: the 25th percentile of the
   carrier SNRs in that band. A convolutional code tolerates a minority of
   weak carriers, but a band whose weakest quarter is below threshold will
   produce packet errors.
3. For every candidate code rate, pick for each band the highest-order
   modulation whose measured SNR threshold (plus a safety margin) is below
   the band's effective SNR; bands where even BPSK fails are disabled.
4. Keep the rate whose total expected throughput is highest.
5. Power is split equally among enabled carriers: disabling a band
   concentrates the fixed transmit power on the remaining ones.

Thresholds are **measured** (``sonic benchmark calibrate``) rather than
taken from textbook AWGN curves, so they include the real receiver's
losses (pilot overhead, imperfect channel/noise estimation, interleaver
depth). The receiver needs no extra signalling: the band plan travels in
the header.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, Sequence

import numpy as np

from sonic.config import BITS_PER_SYMBOL, CODE_RATE_VALUES, MAX_BANDS, MODULATIONS, OFDMConfig

# Minimum per-carrier SNR (dB, after zero-forcing equalisation, as measured
# by the receiver's EVM estimate) at which a 2 KiB payload decoded without
# packet errors in 3/3 AWGN trials, rounded up to the next 0.5 dB. Measured
# by ``sonic benchmark calibrate`` on 2026-10-17 with the default 2048/512
# 2-10 kHz profile (1 dB steps); raw sweep in benchmarks/results/thresholds.json.
DEFAULT_THRESHOLDS: dict[tuple[str, str], float] = {
    ("bpsk", "1/2"): 4.0,
    ("bpsk", "2/3"): 4.0,
    ("bpsk", "3/4"): 5.0,
    ("qpsk", "1/2"): 6.0,
    ("qpsk", "2/3"): 8.0,
    ("qpsk", "3/4"): 9.0,
    ("16qam", "1/2"): 12.0,
    ("16qam", "2/3"): 14.0,
    ("16qam", "3/4"): 16.0,
    ("64qam", "1/2"): 18.5,
    ("64qam", "2/3"): 20.0,
    ("64qam", "3/4"): 21.5,
    ("256qam", "1/2"): 24.0,
    ("256qam", "2/3"): 25.5,
    ("256qam", "3/4"): 27.0,
}


@dataclass
class ChannelStateReport:
    """Receiver -> transmitter feedback. Overhead: 1 + n_bands bytes.

    ``band_snr_db`` is quantised to 0.5 dB steps in a uint8 (0..127.5 dB)
    when serialised; the per-carrier estimate is kept only for analysis.
    """

    n_bands: int
    band_snr_db: list[float]
    carrier_snr_db: Optional[list[float]] = None
    carrier_frequencies_hz: Optional[list[float]] = None

    def to_bytes(self) -> bytes:
        q = [int(np.clip(round(s * 2), 0, 255)) for s in self.band_snr_db]
        return bytes([self.n_bands]) + bytes(q)

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ChannelStateReport":
        n = raw[0]
        return cls(n_bands=n, band_snr_db=[b / 2 for b in raw[1 : 1 + n]])

    @property
    def overhead_bytes(self) -> int:
        return 1 + self.n_bands


@dataclass
class BitLoadingPlan:
    code_rate: str
    band_modulations: list[Optional[str]]
    band_effective_snr_db: list[float]
    expected_info_bitrate_bps: float
    margin_db: float
    rationale: list[str] = field(default_factory=list)

    def describe(self) -> dict:
        return asdict(self)


def band_effective_snr(carrier_snr_db: np.ndarray, n_bands: int, percentile: float = 25.0) -> np.ndarray:
    n = carrier_snr_db.size
    bands = np.minimum((np.arange(n) * n_bands) // n, n_bands - 1)
    out = np.empty(n_bands)
    for b in range(n_bands):
        vals = carrier_snr_db[bands == b]
        out[b] = np.percentile(vals, percentile) if vals.size else -np.inf
    return out


def map_snr_to_config(
    cfg: OFDMConfig, snr_db: Sequence[float], frequencies_hz: Sequence[float]
) -> np.ndarray:
    """Interpolate a measured SNR-vs-frequency curve onto ``cfg``'s data carriers."""
    f_data = cfg.data_carriers * cfg.carrier_spacing
    f = np.asarray(frequencies_hz, dtype=np.float64)
    s = np.asarray(snr_db, dtype=np.float64)
    order = np.argsort(f)
    return np.interp(f_data, f[order], s[order], left=s[order][0], right=s[order][-1])


def plan_bit_loading(
    cfg: OFDMConfig,
    carrier_snr_db: np.ndarray,
    n_bands: int = 8,
    margin_db: float = 1.0,
    thresholds: Optional[dict[tuple[str, str], float]] = None,
    allowed_modulations: Sequence[str] = MODULATIONS,
    allowed_rates: Sequence[str] = ("1/2", "2/3", "3/4"),
) -> BitLoadingPlan:
    """Choose per-band modulations and a code rate for ``cfg``."""
    if not 1 <= n_bands <= MAX_BANDS:
        raise ValueError(f"n_bands must be in 1..{MAX_BANDS}")
    thr = thresholds or DEFAULT_THRESHOLDS
    snr = np.asarray(carrier_snr_db, dtype=np.float64)
    if snr.size != len(cfg.data_carriers):
        raise ValueError("carrier_snr_db must have one entry per data carrier")
    eff = band_effective_snr(snr, n_bands)
    n = snr.size
    band_idx = np.minimum((np.arange(n) * n_bands) // n, n_bands - 1)
    band_sizes = np.bincount(band_idx, minlength=n_bands)
    sym_rate = 1.0 / cfg.symbol_duration

    best: Optional[BitLoadingPlan] = None
    for rate in allowed_rates:
        mods: list[Optional[str]] = []
        notes: list[str] = []
        bits = 0
        for b in range(n_bands):
            chosen = None
            for m in allowed_modulations:
                t = thr.get((m, rate))
                if t is None:
                    continue
                if eff[b] - margin_db >= t:
                    chosen = m  # modulations are ordered by increasing order
            mods.append(chosen)
            if chosen is None:
                notes.append(f"band {b}: eff SNR {eff[b]:.1f} dB below BPSK threshold -> disabled")
            else:
                bits += int(band_sizes[b]) * BITS_PER_SYMBOL[chosen]
        if all(m is None for m in mods):
            continue
        bitrate = bits * sym_rate * CODE_RATE_VALUES[rate]
        plan = BitLoadingPlan(rate, mods, eff.round(2).tolist(), bitrate, margin_db, notes)
        if best is None or bitrate > best.expected_info_bitrate_bps:
            best = plan
    if best is None:
        # nothing is usable; return the most robust plan and let the caller decide
        best = BitLoadingPlan("1/2", ["bpsk"] * n_bands, eff.round(2).tolist(), 0.0, margin_db, ["no band meets the BPSK threshold; falling back to BPSK 1/2 everywhere"])
    best.rationale.insert(
        0,
        f"rate {best.code_rate}: expected {best.expected_info_bitrate_bps:.0f} bit/s from "
        f"{sum(1 for m in best.band_modulations if m)} of {n_bands} bands",
    )
    return best


def apply_plan(cfg: OFDMConfig, plan: BitLoadingPlan) -> OFDMConfig:
    """Return ``cfg`` with the plan's band modulations and code rate."""
    from dataclasses import replace

    mods = plan.band_modulations
    first = next((m for m in mods if m), "bpsk")
    return replace(cfg, band_modulations=tuple(mods), modulation=first, code_rate=plan.code_rate)


def best_fixed_config(
    cfg: OFDMConfig,
    carrier_snr_db: np.ndarray,
    margin_db: float = 1.0,
    thresholds: Optional[dict[tuple[str, str], float]] = None,
) -> tuple[OFDMConfig, dict]:
    """The strongest *uniform* modulation/rate that the whole band supports.

    This is the fair fixed-modulation baseline: it uses the same channel
    knowledge as the adaptive planner but may not vary across the band.
    """
    plan = plan_bit_loading(cfg, carrier_snr_db, n_bands=1, margin_db=margin_db, thresholds=thresholds)
    m = plan.band_modulations[0] or "bpsk"
    from dataclasses import replace

    return replace(cfg, modulation=m, code_rate=plan.code_rate, band_modulations=()), plan.describe()
