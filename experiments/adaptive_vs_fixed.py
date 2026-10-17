#!/usr/bin/env python3
"""Adaptive bit loading vs fixed baselines (same as `sonic benchmark adaptive`)."""
import argparse
import os

import _common  # noqa: F401
from sonic.benchmarking import experiment_adaptive, summarize, write_results

p = argparse.ArgumentParser()
p.add_argument("--trials", type=int, default=3)
p.add_argument("--margin", type=float, default=1.0)
p.add_argument("--bands", type=int, default=8)
p.add_argument("--out", default=os.path.join(_common.RESULTS, "adaptive.json"))
a = p.parse_args()
recs = experiment_adaptive(trials=a.trials, n_bands=a.bands, margin_db=a.margin)
summ = summarize([r for r in recs if r.get("scheme") != "probe"], ["channel", "scheme"])
write_results(recs, a.out, summ, {"trials": a.trials, "margin_db": a.margin, "n_bands": a.bands})
for row in sorted(summ, key=lambda r: (r["channel"], r["scheme"])):
    print(f"{row['channel']:22s} {row['scheme']:14s} net={row['net_bitrate_bps_mean']:7.0f} ±{row['net_bitrate_bps_ci95']:4.0f} success={row['success_rate']:.2f}")
