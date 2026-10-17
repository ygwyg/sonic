#!/usr/bin/env python3
"""Carrier count at equal bandwidth vs. bandwidth at equal carrier spacing."""
import argparse
import os

import _common  # noqa: F401
from sonic.benchmarking import config_for_carriers, run_trial, standard_datasets, summarize, write_results
from sonic.channel import ChannelConfig
from sonic.config import OFDMConfig

p = argparse.ArgumentParser()
p.add_argument("--snr", type=float, default=20.0)
p.add_argument("--trials", type=int, default=2)
p.add_argument("--out", default=os.path.join(_common.RESULTS, "density_vs_bandwidth.json"))
a = p.parse_args()
data = standard_datasets(2048)[0].data
recs = []
# (A) equal bandwidth 2-10 kHz, varying carrier count
for n in (16, 64, 256, 1024):
    cfg = config_for_carriers(n, "16qam")
    for t in range(a.trials):
        r = run_trial(data, cfg, ChannelConfig(name="awgn", snr_db=a.snr), seed=t, compression="none", label="equal_bandwidth")
        r["target_carriers"] = n
        recs.append(r)
# (B) equal spacing (n_fft 2048), varying bandwidth -> carrier count grows with bandwidth
for f_high in (4000, 6000, 10000, 14000, 18000):
    cfg = OFDMConfig(n_fft=2048, cp_len=256, f_low=2000, f_high=f_high, modulation="16qam")
    for t in range(a.trials):
        r = run_trial(data, cfg, ChannelConfig(name="awgn", snr_db=a.snr), seed=t, compression="none", label="equal_spacing")
        r["target_carriers"] = len(cfg.active_carriers)
        recs.append(r)
summ = summarize(recs, ["label", "target_carriers"])
write_results(recs, a.out, summ, {"snr_db": a.snr, "trials": a.trials})
for row in sorted(summ, key=lambda r: (r["label"], r["target_carriers"])):
    print(f"{row['label']:16s} carriers={row['target_carriers']:5d} bw={row['bandwidth_hz']:6.0f} Hz info={row['info_bitrate_bps']:6.0f} net={row['net_bitrate_bps_mean']:6.0f} success={row['success_rate']:.2f}")
