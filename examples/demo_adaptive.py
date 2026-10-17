#!/usr/bin/env python3
"""Demonstration 5 — adaptive bit loading vs fixed modulation."""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from sonic import OFDMConfig  # noqa: E402
from sonic.adaptive import apply_plan, best_fixed_config, plan_bit_loading  # noqa: E402
from sonic.benchmarking import measure_channel_state, run_trial  # noqa: E402
from sonic.channel import ChannelConfig  # noqa: E402

base = OFDMConfig()
channel = ChannelConfig(name="tilted+notch", snr_db=26.0, tilt_db_per_khz=-3.0, notches=[(5000.0, 25.0, 300.0)])
report, probe = measure_channel_state(base, channel)
print("channel-state report (8 bands, dB):", report.band_snr_db, f"-> {report.overhead_bytes} bytes of feedback")
plan = plan_bit_loading(base, np.array(report.carrier_snr_db), n_bands=8, margin_db=1.0)
for line in plan.rationale:
    print("  ", line)
print("adaptive plan:", plan.band_modulations, "rate", plan.code_rate)
fixed_best, fplan = best_fixed_config(base, np.array(report.carrier_snr_db))
print("best uniform :", fixed_best.modulation, "rate", fixed_best.code_rate)

data = open(os.path.join(HERE, "hello.py"), "rb").read() * 6
for name, cfg in (("fixed_default qpsk 1/2", base), ("fixed_best", fixed_best), ("adaptive", apply_plan(base, plan))):
    r = run_trial(data, cfg, channel, compression="none")
    print(f"{name:24s} success={r['success']!s:5} net={r['net_bitrate_bps']:7.0f} bit/s  raw BER={r['raw_ber']:.4f}  {r['error'] or ''}")
