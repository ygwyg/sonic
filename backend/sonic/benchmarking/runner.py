"""Automated, reproducible benchmark runner.

Every record produced here comes from an actual encode -> channel ->
decode execution. Nothing is estimated from formulas except the fields
explicitly named ``*_theoretical``.

Metric vocabulary (kept distinct on purpose):

* ``raw_bitrate_bps``        coded bits on data carriers per second (PHY symbol rate)
* ``info_bitrate_bps``       after FEC, before framing (PHY information rate)
* ``net_bitrate_bps``        original payload bits per second of audio, **only
                             counted when the file was reconstructed** (application throughput)
* ``spectral_efficiency``    info bits / s / Hz of occupied bandwidth
* ``compression_ratio``      original / transmitted payload bytes (independent of the PHY)
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import time
from dataclasses import dataclass, replace
from typing import Callable, Iterable, Optional, Sequence

import numpy as np

from sonic.adaptive import ChannelStateReport, apply_plan, best_fixed_config, map_snr_to_config, plan_bit_loading
from sonic.benchmarking.datasets import Sample, standard_datasets
from sonic.channel import ChannelConfig, apply_channel, get_channel
from sonic.compression import available_algorithms, compress
from sonic.config import CODE_RATE_VALUES, OFDMConfig
from sonic.receiver import decode
from sonic.transmitter import encode

ProgressFn = Callable[[dict], None]


def _noop(_: dict) -> None:
    pass


# ----------------------------------------------------------------- trials


def run_trial(
    data: bytes,
    cfg: OFDMConfig,
    channel: ChannelConfig,
    seed: int = 0,
    compression: str = "auto",
    filename: str = "",
    label: str = "",
) -> dict:
    """One encode -> channel -> decode execution with full metrics."""
    chan = replace(channel, seed=seed)
    t0 = time.perf_counter()
    wave, info = encode(data, cfg, compression=compression, filename=filename, seed=seed)
    t_enc = time.perf_counter() - t0
    rx = apply_channel(wave, cfg.sample_rate, chan)
    t1 = time.perf_counter()
    res = decode(rx, cfg.sample_rate, reference=info)
    t_dec = time.perf_counter() - t1
    d = res.diagnostics
    ps = d.get("payload_section", {})
    pk = d.get("packets", {})
    ok = bool(res.success and res.data == data)
    duration = info.duration_s
    rec = {
        "label": label,
        "seed": seed,
        "channel": chan.name,
        "snr_db": chan.snr_db,
        "modulation": cfg.modulation,
        "band_modulations": list(cfg.band_modulations),
        "code_rate": cfg.code_rate,
        "n_fft": cfg.n_fft,
        "cp_len": cfg.cp_len,
        "n_carriers": int(len(cfg.active_carriers)),
        "n_data_carriers": int(len(cfg.enabled_data_carriers)),
        "n_pilots": int(len(cfg.pilot_carriers)),
        "f_low": cfg.f_low,
        "f_high": cfg.f_high,
        "bandwidth_hz": cfg.occupied_bandwidth,
        "symbol_duration_s": cfg.symbol_duration,
        "source_bytes": len(data),
        "compression": info.compression.algorithm,
        "compressed_bytes": len(info.compression.data),
        "compression_ratio": info.compression.ratio,
        "info_bits": info.info_bits,
        "coded_bits": info.coded_bits,
        "n_samples": info.n_samples,
        "duration_s": duration,
        "papr_db": info.papr_db,
        "raw_bitrate_bps": cfg.raw_bitrate,
        "info_bitrate_bps": cfg.info_bitrate,
        "spectral_efficiency": cfg.spectral_efficiency,
        "gross_bitrate_bps": 8 * len(data) / duration,  # if everything decoded
        "net_bitrate_bps": 8 * len(data) / duration if ok else 0.0,
        "success": ok,
        "error": res.error,
        "raw_ber": d.get("raw_ber"),
        "packet_error_rate": pk.get("packet_error_rate"),
        "packets_ok": pk.get("n_ok"),
        "packets_total": pk.get("n_packets"),
        "snr_est_db": ps.get("snr_evm_mean_db"),
        "snr_training_db": ps.get("snr_training_mean_db"),
        "sync_score": (d.get("sync", {}).get("candidates") or [{}])[0].get("score"),
        "encode_time_s": t_enc,
        "decode_time_s": t_dec,
        "energy_j_theoretical": None,
    }
    return rec


# ---------------------------------------------------------------- helpers


def config_for_carriers(
    n_carriers: int,
    modulation: str = "qpsk",
    code_rate: str = "1/2",
    sample_rate: int = 48000,
    f_low: float = 2000.0,
    f_high: float = 10000.0,
    cp_fraction: float = 0.125,
    pilot_spacing: int = 8,
    packet_size: int = 256,
) -> OFDMConfig:
    """Equal-bandwidth configuration with (approximately) ``n_carriers``.

    The band is fixed; the FFT size is chosen so that the band holds the
    requested number of carriers. The cyclic prefix is a fixed *fraction*
    of the symbol, so overhead is equal across configurations while its
    absolute duration (echo tolerance) is not -- that is the real
    engineering trade-off this experiment exposes.
    """
    bw = f_high - f_low
    n_fft = int(round(n_carriers * sample_rate / bw))
    n_fft += n_fft % 2
    cp = max(1, int(round(n_fft * cp_fraction)))
    return OFDMConfig(
        sample_rate=sample_rate,
        n_fft=n_fft,
        cp_len=cp,
        f_low=f_low,
        f_high=f_high,
        pilot_spacing=min(pilot_spacing, max(2, n_carriers // 2)),
        modulation=modulation,
        code_rate=code_rate,
        packet_size=packet_size,
    )


def summarize(records: Iterable[dict], keys: Sequence[str]) -> list[dict]:
    """Group records by ``keys`` and report means with 95% confidence intervals."""
    groups: dict[tuple, list[dict]] = {}
    for r in records:
        groups.setdefault(tuple(r.get(k) for k in keys), []).append(r)
    out = []
    for key, rs in groups.items():
        row = {k: v for k, v in zip(keys, key)}
        n = len(rs)
        row["n_trials"] = n
        for m in ("net_bitrate_bps", "raw_ber", "packet_error_rate", "snr_est_db", "duration_s", "encode_time_s", "decode_time_s", "compression_ratio", "papr_db"):
            vals = np.array([r[m] for r in rs if r.get(m) is not None], dtype=np.float64)
            if vals.size:
                mean = float(vals.mean())
                ci = float(1.96 * vals.std(ddof=1) / math.sqrt(vals.size)) if vals.size > 1 else 0.0
                row[m + "_mean"] = mean
                row[m + "_ci95"] = ci
        row["success_rate"] = float(np.mean([r["success"] for r in rs]))
        for m in ("raw_bitrate_bps", "info_bitrate_bps", "spectral_efficiency", "bandwidth_hz", "n_carriers", "n_fft", "symbol_duration_s", "gross_bitrate_bps"):
            if rs[0].get(m) is not None:
                row[m] = rs[0][m]
        out.append(row)
    return out


def write_results(records: list[dict], path_json: str, summary: Optional[list[dict]] = None, meta: Optional[dict] = None) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path_json)), exist_ok=True)
    payload = {"meta": meta or {}, "records": records}
    if summary is not None:
        payload["summary"] = summary
    with open(path_json, "w") as f:
        json.dump(payload, f, indent=1, default=_json_default)
    with open(os.path.splitext(path_json)[0] + ".csv", "w", newline="") as f:
        f.write(records_to_csv(records))


def records_to_csv(records: list[dict]) -> str:
    if not records:
        return ""
    keys = list(records[0].keys())
    for r in records[1:]:
        for k in r:
            if k not in keys:
                keys.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=keys)
    w.writeheader()
    for r in records:
        w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})
    return buf.getvalue()


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


# ------------------------------------------------------------ experiments


def experiment_snr_sweep(
    snrs: Sequence[float],
    modulations: Sequence[str] = ("bpsk", "qpsk", "16qam", "64qam"),
    code_rate: str = "1/2",
    trials: int = 3,
    payload_bytes: int = 2048,
    base: Optional[OFDMConfig] = None,
    progress: ProgressFn = _noop,
) -> list[dict]:
    """BER / throughput versus SNR per modulation on an AWGN channel."""
    base = base or OFDMConfig()
    data = standard_datasets(payload_bytes)[0].data  # random binary: incompressible
    records = []
    total = len(snrs) * len(modulations) * trials
    done = 0
    for m in modulations:
        cfg = base.with_modulation(m, code_rate)
        for snr in snrs:
            for t in range(trials):
                rec = run_trial(data, cfg, ChannelConfig(name="awgn", snr_db=float(snr)), seed=t, compression="none", label="snr_sweep")
                records.append(rec)
                done += 1
                progress({"experiment": "snr_sweep", "done": done, "total": total, "last": rec})
    return records


def experiment_carrier_density(
    carrier_counts: Sequence[int] = (16, 32, 64, 128, 256, 512, 1024),
    modulations: Sequence[str] = ("qpsk", "16qam", "64qam"),
    code_rate: str = "1/2",
    channel: Optional[ChannelConfig] = None,
    trials: int = 3,
    payload_bytes: int = 2048,
    progress: ProgressFn = _noop,
) -> list[dict]:
    """Throughput vs carrier count at equal bandwidth, power and channel."""
    channel = channel or ChannelConfig(name="awgn", snr_db=20.0)
    data = standard_datasets(payload_bytes)[0].data
    records = []
    total = len(carrier_counts) * len(modulations) * trials
    done = 0
    for n in carrier_counts:
        for m in modulations:
            cfg = config_for_carriers(n, m, code_rate)
            for t in range(trials):
                rec = run_trial(data, cfg, channel, seed=t, compression="none", label="carrier_density")
                rec["target_carriers"] = n
                records.append(rec)
                done += 1
                progress({"experiment": "carrier_density", "done": done, "total": total, "last": rec})
    return records


def experiment_file_sizes(
    sizes: Sequence[int] = (256, 1024, 4096, 16384),
    cfg: Optional[OFDMConfig] = None,
    channel: Optional[ChannelConfig] = None,
    trials: int = 2,
    progress: ProgressFn = _noop,
) -> list[dict]:
    cfg = cfg or OFDMConfig()
    channel = channel or ChannelConfig(name="awgn", snr_db=20.0)
    records = []
    total = len(sizes) * trials
    done = 0
    for n in sizes:
        data = standard_datasets(n)[0].data
        for t in range(trials):
            rec = run_trial(data, cfg, channel, seed=t, compression="none", label="file_size")
            records.append(rec)
            done += 1
            progress({"experiment": "file_size", "done": done, "total": total, "last": rec})
    return records


def experiment_channels(
    channels: Sequence[str] = ("ideal", "quiet_room", "noisy_room", "reverberant_room", "difficult"),
    presets: Optional[dict[str, OFDMConfig]] = None,
    trials: int = 2,
    payload_bytes: int = 2048,
    progress: ProgressFn = _noop,
) -> list[dict]:
    from sonic.config import PRESETS

    presets = presets or {k: PRESETS[k] for k in ("default", "audioqr", "robust", "fast")}
    data = standard_datasets(payload_bytes)[0].data
    records = []
    total = len(channels) * len(presets) * trials
    done = 0
    for ch in channels:
        for name, cfg in presets.items():
            for t in range(trials):
                rec = run_trial(data, cfg, get_channel(ch), seed=t, compression="none", label=f"preset:{name}")
                rec["preset"] = name
                records.append(rec)
                done += 1
                progress({"experiment": "channels", "done": done, "total": total, "last": rec})
    return records


def experiment_compression(samples: Optional[list[Sample]] = None, progress: ProgressFn = _noop) -> list[dict]:
    """Compression ratio per algorithm and source type (no PHY involved)."""
    from sonic.benchmarking.datasets import source_corpus
    from sonic.compression import decompress
    from sonic.compression.codeaware import detect_language

    samples = samples or source_corpus()
    algos = available_algorithms()
    records = []
    total = len(samples) * len(algos)
    done = 0
    for s in samples:
        lang = detect_language(s.data, s.filename)
        for a in algos:
            t0 = time.perf_counter()
            out = compress(s.data, a, language=lang)
            t_c = time.perf_counter() - t0
            t1 = time.perf_counter()
            back = decompress(out, a)
            t_d = time.perf_counter() - t1
            rec = {
                "label": "compression",
                "sample": s.name,
                "kind": s.kind,
                "language": lang,
                "algorithm": a,
                "source_bytes": len(s.data),
                "compressed_bytes": len(out),
                "compression_ratio": len(s.data) / max(1, len(out)),
                "bits_per_byte": 8 * len(out) / max(1, len(s.data)),
                "lossless": back == s.data,
                "compress_time_s": t_c,
                "decompress_time_s": t_d,
            }
            records.append(rec)
            done += 1
            progress({"experiment": "compression", "done": done, "total": total, "last": rec})
    return records


def measure_channel_state(cfg: OFDMConfig, channel: ChannelConfig, seed: int = 0, probe_bytes: int = 512) -> tuple[ChannelStateReport, dict]:
    """Send a probe through the channel and return the receiver's SNR report.

    The probe uses the most robust uniform setting so that it decodes on
    any channel the adaptive scheme could hope to use.
    """
    probe_cfg = cfg.with_modulation("bpsk", "1/2")
    data = standard_datasets(probe_bytes, seed=99)[0].data
    wave, info = encode(data, probe_cfg, compression="none", seed=seed)
    rx = apply_channel(wave, cfg.sample_rate, replace(channel, seed=seed))
    res = decode(rx, cfg.sample_rate, reference=info)
    ps = res.diagnostics.get("payload_section")
    if not ps or ps.get("snr_evm_db") is None:
        raise RuntimeError(f"probe could not be demodulated: {res.error}")
    snr = np.array(ps["snr_evm_db"], dtype=np.float64)
    freqs = probe_cfg.enabled_data_carriers * probe_cfg.carrier_spacing
    carrier_snr = map_snr_to_config(cfg, snr, freqs)
    from sonic.adaptive import band_effective_snr

    report = ChannelStateReport(
        n_bands=8,
        band_snr_db=band_effective_snr(carrier_snr, 8).round(1).tolist(),
        carrier_snr_db=carrier_snr.round(2).tolist(),
        carrier_frequencies_hz=(cfg.data_carriers * cfg.carrier_spacing).round(1).tolist(),
    )
    return report, {"probe_success": res.success, "probe_error": res.error, "probe_duration_s": info.duration_s}


def experiment_adaptive(
    channels: Optional[Sequence[ChannelConfig]] = None,
    base: Optional[OFDMConfig] = None,
    n_bands: int = 8,
    margin_db: float = 1.0,
    trials: int = 3,
    payload_bytes: int = 4096,
    progress: ProgressFn = _noop,
) -> list[dict]:
    """Adaptive bit loading vs. fixed baselines on frequency-selective channels.

    Three transmitters are compared on identical channel realisations:

    * ``fixed_default``  the default uniform QPSK 1/2 (no channel knowledge)
    * ``fixed_best``     the strongest uniform setting the channel-state
                         report says the whole band supports (same knowledge
                         as adaptive, but one modulation everywhere)
    * ``adaptive``       per-band bit loading from the same report
    """
    base = base or OFDMConfig()
    channels = channels or default_adaptive_channels()
    data = standard_datasets(payload_bytes)[0].data
    records = []
    total = len(channels) * trials * 3
    done = 0
    for ch in channels:
        try:
            report, probe_info = measure_channel_state(base, ch, seed=1000)
        except RuntimeError as e:
            records.append({"label": "adaptive", "channel": ch.name, "scheme": "probe", "success": False, "error": str(e)})
            continue
        carrier_snr = np.array(report.carrier_snr_db)
        plan = plan_bit_loading(base, carrier_snr, n_bands=n_bands, margin_db=margin_db)
        adaptive_cfg = apply_plan(base, plan)
        fixed_best_cfg, fixed_plan = best_fixed_config(base, carrier_snr, margin_db=margin_db)
        schemes = {
            "fixed_default": base.with_modulation("qpsk", "1/2"),
            "fixed_best": fixed_best_cfg,
            "adaptive": adaptive_cfg,
        }
        for t in range(trials):
            for name, cfg in schemes.items():
                rec = run_trial(data, cfg, ch, seed=t, compression="none", label="adaptive")
                rec["scheme"] = name
                rec["plan"] = plan.describe() if name == "adaptive" else (fixed_plan if name == "fixed_best" else None)
                rec["feedback_overhead_bytes"] = report.overhead_bytes if name != "fixed_default" else 0
                rec["band_snr_db"] = report.band_snr_db
                rec["probe"] = probe_info
                records.append(rec)
                done += 1
                progress({"experiment": "adaptive", "done": done, "total": total, "last": rec})
    return records


def default_adaptive_channels() -> list[ChannelConfig]:
    """Frequency-selective synthetic channels where bit loading can matter."""
    return [
        ChannelConfig(name="flat_20db", snr_db=20.0),
        ChannelConfig(name="tilted_-3db_per_khz", snr_db=26.0, tilt_db_per_khz=-3.0),
        ChannelConfig(name="notched", snr_db=24.0, notches=[(4000.0, 25.0, 400.0), (7500.0, 20.0, 300.0)]),
        ChannelConfig(name="lowpass_6k", snr_db=28.0, lowpass_hz=6000.0),
        ChannelConfig(name="tilt_plus_tones", snr_db=25.0, tilt_db_per_khz=-2.0, tones=[(3300.0, 0.3), (8800.0, 0.3)]),
        ChannelConfig(name="quiet_room_like", snr_db=28.0, multipath=[(0.0021, 0.25), (0.0048, 0.12)], tilt_db_per_khz=-1.0),
    ]


def calibrate_thresholds(
    modulations: Sequence[str] = ("bpsk", "qpsk", "16qam", "64qam", "256qam"),
    rates: Sequence[str] = ("1/2", "2/3", "3/4"),
    snr_lo: float = -2.0,
    snr_hi: float = 34.0,
    step: float = 1.0,
    trials: int = 3,
    payload_bytes: int = 2048,
    base: Optional[OFDMConfig] = None,
    progress: ProgressFn = _noop,
) -> dict:
    """Measure, per (modulation, rate), the lowest AWGN SNR at which all
    trials decode. Returns thresholds keyed by the receiver's own EVM-based
    SNR estimate so they are directly comparable with channel-state reports.
    """
    base = base or OFDMConfig()
    data = standard_datasets(payload_bytes)[0].data
    out: dict[str, dict] = {}
    for m in modulations:
        for r in rates:
            cfg = base.with_modulation(m, r)
            snr = snr_lo
            found = None
            sweep = []
            while snr <= snr_hi:
                ok_all = True
                est = []
                for t in range(trials):
                    rec = run_trial(data, cfg, ChannelConfig(name="awgn", snr_db=snr), seed=t, compression="none", label="calibrate")
                    est.append(rec["snr_est_db"])
                    if not rec["success"]:
                        ok_all = False
                        break
                sweep.append({"snr_db": snr, "ok": ok_all, "snr_est_db": float(np.mean([e for e in est if e is not None])) if est else None})
                progress({"experiment": "calibrate", "modulation": m, "rate": r, "snr_db": snr, "ok": ok_all})
                if ok_all:
                    found = sweep[-1]
                    break
                snr += step
            out[f"{m}|{r}"] = {
                "modulation": m,
                "code_rate": r,
                "threshold_channel_snr_db": found["snr_db"] if found else None,
                "threshold_est_snr_db": found["snr_est_db"] if found else None,
                "sweep": sweep,
            }
    return out


# -------------------------------------------------------------- bundles


def run_quick_suite(progress: ProgressFn = _noop, trials: int = 2) -> dict[str, list[dict]]:
    """A reduced set of experiments suitable for the dashboard."""
    return {
        "snr_sweep": experiment_snr_sweep(snrs=(0, 3, 6, 9, 12, 15, 18, 21, 24), trials=trials, payload_bytes=1024, progress=progress),
        "carrier_density": experiment_carrier_density(trials=trials, payload_bytes=1024, progress=progress),
    }
