#!/usr/bin/env python3
"""Cyclic-prefix length vs synthetic reverberation time (RT60)."""
import argparse
import os

import _common  # noqa: F401
from sonic.benchmarking import run_trial, standard_datasets, summarize, write_results
from sonic.channel import ChannelConfig
from sonic.config import OFDMConfig

p = argparse.ArgumentParser()
p.add_argument("--trials", type=int, default=2)
p.add_argument("--out", default=os.path.join(_common.RESULTS, "cp_vs_reverb.json"))
a = p.parse_args()
data = standard_datasets(2048)[0].data
recs = []
for rt60 in (0.1, 0.3, 0.6):
    ch = ChannelConfig(name=f"rt60_{rt60}", snr_db=25.0, reverb_rt60_s=rt60, reverb_level=0.15, multipath=[(0.002, 0.4), (0.005, 0.25)])
    for cp in (128, 512, 2048):
        cfg = OFDMConfig(n_fft=4096, cp_len=cp, modulation="qpsk")
        for t in range(a.trials):
            r = run_trial(data, cfg, ch, seed=t, compression="none", label="cp_vs_reverb")
            r["rt60_s"] = rt60
            recs.append(r)
summ = summarize(recs, ["rt60_s", "cp_len"])
write_results(recs, a.out, summ, {"trials": a.trials})
for row in sorted(summ, key=lambda r: (r["rt60_s"], r["cp_len"])):
    print(f"RT60={row['rt60_s']:.1f}s cp={row['cp_len']:5d} ({1000 * row['cp_len'] / 48000:5.1f} ms) success={row['success_rate']:.2f} snr_est={row.get('snr_est_db_mean', 0):5.1f} dB net={row['net_bitrate_bps_mean']:6.0f}")
