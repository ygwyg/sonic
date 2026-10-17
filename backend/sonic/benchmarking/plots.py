"""Static PNG charts from benchmark result files (matplotlib, optional)."""

from __future__ import annotations

import json
import os
from collections import defaultdict

import numpy as np


def _load(path: str):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.dpi": 120, "axes.grid": True, "grid.alpha": 0.3})
    return plt


def plot_snr_sweep(res_dir: str, out_dir: str) -> list[str]:
    data = _load(os.path.join(res_dir, "snr_sweep.json"))
    if not data:
        return []
    plt = _plt()
    rows = data["summary"]
    made = []
    for metric, ylabel, fname, logy in (
        ("raw_ber_mean", "raw (pre-FEC) bit error rate", "ber_vs_snr.png", True),
        ("net_bitrate_bps_mean", "net payload throughput (bit/s)", "throughput_vs_snr.png", False),
        ("success_rate", "file reconstruction success rate", "success_vs_snr.png", False),
    ):
        fig, ax = plt.subplots(figsize=(7, 4.2))
        by_mod = defaultdict(list)
        for r in rows:
            by_mod[(r["modulation"], r["code_rate"])].append(r)
        for (m, rate), rs in by_mod.items():
            rs.sort(key=lambda r: r["snr_db"])
            x = [r["snr_db"] for r in rs]
            y = [r.get(metric, np.nan) for r in rs]
            if logy:
                y = [max(v, 1e-6) if v is not None else np.nan for v in y]
            ax.plot(x, y, marker="o", label=f"{m} r={rate}")
        ax.set_xlabel("channel SNR (dB, white noise over full band)")
        ax.set_ylabel(ylabel)
        if logy:
            ax.set_yscale("log")
        ax.legend()
        ax.set_title(f"{ylabel} vs SNR (AWGN, measured)")
        p = os.path.join(out_dir, fname)
        fig.tight_layout()
        fig.savefig(p)
        plt.close(fig)
        made.append(p)
    return made


def plot_carrier_density(res_dir: str, out_dir: str) -> list[str]:
    data = _load(os.path.join(res_dir, "carrier_density.json"))
    if not data:
        return []
    plt = _plt()
    rows = data["summary"]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    by_mod = defaultdict(list)
    for r in rows:
        by_mod[r["modulation"]].append(r)
    for m, rs in by_mod.items():
        rs.sort(key=lambda r: r["target_carriers"])
        x = [r["target_carriers"] for r in rs]
        axes[0].errorbar(x, [r["net_bitrate_bps_mean"] for r in rs], yerr=[r.get("net_bitrate_bps_ci95", 0) for r in rs], marker="o", label=m, capsize=3)
        axes[0].plot(x, [r["info_bitrate_bps"] for r in rs], ls="--", alpha=0.5)
        axes[1].plot(x, [r["spectral_efficiency"] for r in rs], marker="o", label=m)
        axes[2].plot(x, [r.get("papr_db_mean", np.nan) for r in rs], marker="o", label=m)
    axes[0].set_xscale("log", base=2)
    axes[1].set_xscale("log", base=2)
    axes[2].set_xscale("log", base=2)
    axes[0].set_xlabel("carriers (equal 8 kHz bandwidth)")
    axes[0].set_ylabel("bit/s (solid: net measured, dashed: PHY info rate)")
    axes[0].set_title("Throughput vs carrier count")
    axes[1].set_xlabel("carriers")
    axes[1].set_ylabel("info bit/s/Hz")
    axes[1].set_title("Spectral efficiency (identical by construction)")
    axes[2].set_xlabel("carriers")
    axes[2].set_ylabel("PAPR (dB)")
    axes[2].set_title("Peak-to-average power ratio")
    for ax in axes:
        ax.legend()
    fig.tight_layout()
    p = os.path.join(out_dir, "throughput_vs_carriers.png")
    fig.savefig(p)
    plt.close(fig)
    return [p]


def plot_file_sizes(res_dir: str, out_dir: str) -> list[str]:
    data = _load(os.path.join(res_dir, "file_sizes.json"))
    if not data:
        return []
    plt = _plt()
    rows = sorted(data["summary"], key=lambda r: r["source_bytes"])
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.plot([r["source_bytes"] for r in rows], [r["duration_s_mean"] for r in rows], marker="o")
    ax.set_xscale("log", base=2)
    ax.set_xlabel("file size (bytes)")
    ax.set_ylabel("transmission duration (s)")
    ax.set_title("Transmission time vs file size (fixed overhead ~1.2 s)")
    fig.tight_layout()
    p = os.path.join(out_dir, "time_vs_size.png")
    fig.savefig(p)
    plt.close(fig)
    return [p]


def plot_compression(res_dir: str, out_dir: str) -> list[str]:
    data = _load(os.path.join(res_dir, "compression.json"))
    if not data:
        return []
    plt = _plt()
    recs = data["records"]
    kinds = sorted({r["language"] for r in recs})
    algos = [a for a in ("none", "zlib", "lzma", "zstd", "codeaware") if any(r["algorithm"] == a for r in recs)]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    w = 0.8 / len(algos)
    for i, a in enumerate(algos):
        vals = []
        for k in kinds:
            rs = [r["bits_per_byte"] for r in recs if r["language"] == k and r["algorithm"] == a]
            vals.append(np.mean(rs) if rs else np.nan)
        ax.bar(np.arange(len(kinds)) + i * w, vals, w, label=a)
    ax.set_xticks(np.arange(len(kinds)) + 0.4 - w / 2)
    ax.set_xticklabels(kinds)
    ax.set_ylabel("compressed bits per source byte (lower is better)")
    ax.set_title("Compression by source type (lossless, measured)")
    ax.legend()
    fig.tight_layout()
    p = os.path.join(out_dir, "compression_by_type.png")
    fig.savefig(p)
    plt.close(fig)
    return [p]


def plot_adaptive(res_dir: str, out_dir: str) -> list[str]:
    data = _load(os.path.join(res_dir, "adaptive.json"))
    if not data:
        return []
    plt = _plt()
    rows = data["summary"]
    channels = sorted({r["channel"] for r in rows})
    schemes = ["fixed_default", "fixed_best", "adaptive"]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    w = 0.26
    for i, s in enumerate(schemes):
        vals, errs = [], []
        for c in channels:
            r = next((r for r in rows if r["channel"] == c and r["scheme"] == s), None)
            vals.append(r["net_bitrate_bps_mean"] if r else 0)
            errs.append(r.get("net_bitrate_bps_ci95", 0) if r else 0)
        ax.bar(np.arange(len(channels)) + i * w, vals, w, yerr=errs, capsize=2, label=s)
    ax.set_xticks(np.arange(len(channels)) + w)
    ax.set_xticklabels(channels, rotation=15)
    ax.set_ylabel("net successfully delivered bit/s")
    ax.set_title("Adaptive bit loading vs fixed modulation (same band, power, channel)")
    ax.legend()
    fig.tight_layout()
    p = os.path.join(out_dir, "adaptive_vs_fixed.png")
    fig.savefig(p)
    plt.close(fig)
    return [p]


def plot_channels(res_dir: str, out_dir: str) -> list[str]:
    data = _load(os.path.join(res_dir, "channels.json"))
    if not data:
        return []
    plt = _plt()
    rows = data["summary"]
    channels = sorted({r["channel"] for r in rows}, key=lambda c: ["ideal", "quiet_room", "noisy_room", "reverberant_room", "difficult"].index(c) if c in ("ideal", "quiet_room", "noisy_room", "reverberant_room", "difficult") else 99)
    presets = sorted({r["preset"] for r in rows})
    fig, ax = plt.subplots(figsize=(9, 4.2))
    w = 0.8 / len(presets)
    for i, p_ in enumerate(presets):
        vals = []
        for c in channels:
            r = next((r for r in rows if r["channel"] == c and r["preset"] == p_), None)
            vals.append(r["net_bitrate_bps_mean"] if r else 0)
        ax.bar(np.arange(len(channels)) + i * w, vals, w, label=p_)
    ax.set_xticks(np.arange(len(channels)) + 0.4 - w / 2)
    ax.set_xticklabels(channels)
    ax.set_ylabel("net delivered bit/s (0 = failed)")
    ax.set_title("Presets across synthetic channels")
    ax.legend()
    fig.tight_layout()
    p = os.path.join(out_dir, "presets_vs_channels.png")
    fig.savefig(p)
    plt.close(fig)
    return [p]


def make_all_plots(res_dir: str, out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for fn in (plot_snr_sweep, plot_carrier_density, plot_file_sizes, plot_compression, plot_adaptive, plot_channels):
        made += fn(res_dir, out_dir)
    return made
