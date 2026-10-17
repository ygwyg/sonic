#!/usr/bin/env python3
"""Sample-rate-offset tolerance per modulation (default profile, 30 dB SNR)."""
import argparse
import os

import _common  # noqa: F401
from sonic.benchmarking import run_trial, standard_datasets, summarize, write_results
from sonic.channel import ChannelConfig
from sonic.config import OFDMConfig

p = argparse.ArgumentParser()
p.add_argument("--trials", type=int, default=1)
p.add_argument("--out", default=os.path.join(_common.RESULTS, "sro_tolerance.json"))
a = p.parse_args()
data = standard_datasets(2048)[0].data
recs = []
for mod, rate in (("qpsk", "1/2"), ("16qam", "3/4"), ("64qam", "3/4")):
    cfg = OFDMConfig(modulation=mod, code_rate=rate)
    for ppm in (0, 30, 100, 200, 300):
        for t in range(a.trials):
            r = run_trial(data, cfg, ChannelConfig(name=f"sro_{ppm}", snr_db=30.0, sample_rate_ppm=ppm), seed=t, compression="none", label="sro")
            r["ppm"] = ppm
            recs.append(r)
summ = summarize(recs, ["modulation", "code_rate", "ppm"])
write_results(recs, a.out, summ, {"trials": a.trials})
for row in sorted(summ, key=lambda r: (r["modulation"], r["ppm"])):
    print(f"{row['modulation']:6s} r={row['code_rate']} ppm={row['ppm']:4d} success={row['success_rate']:.2f} snr_est={row.get('snr_est_db_mean', 0):5.1f} dB")
