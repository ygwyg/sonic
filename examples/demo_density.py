#!/usr/bin/env python3
"""Demonstration 4 — carrier density experiment at equal bandwidth.

Runs a reduced version of `sonic benchmark carriers` and prints the table.
Full runs with confidence intervals live in benchmarks/results/.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from sonic.benchmarking import experiment_carrier_density, summarize  # noqa: E402
from sonic.channel import get_channel  # noqa: E402

for ch in ("awgn", "quiet_room"):
    recs = experiment_carrier_density(carrier_counts=(16, 64, 256, 1024), modulations=("qpsk", "64qam"),
                                      channel=get_channel(ch, snr_db=20.0), trials=2, payload_bytes=1024)
    print(f"\nchannel: {ch} (SNR 20 dB)")
    print(f"{'carriers':>8} {'mod':>6} {'PHY info bit/s':>14} {'net bit/s':>10} {'success':>8} {'raw BER':>9} {'PAPR dB':>8} {'symbol ms':>9}")
    for row in sorted(summarize(recs, ["target_carriers", "modulation"]), key=lambda r: (r["target_carriers"], r["modulation"])):
        print(f"{row['target_carriers']:>8} {row['modulation']:>6} {row['info_bitrate_bps']:>14.0f} {row['net_bitrate_bps_mean']:>10.0f} "
              f"{row['success_rate']:>8.2f} {row.get('raw_ber_mean', 0):>9.4f} {row.get('papr_db_mean', 0):>8.1f} {1000 * row['symbol_duration_s']:>9.1f}")
print("\nAt equal bandwidth the PHY information rate does not depend on the carrier count; only channel\n"
      "effects (echo tolerance of the short cyclic prefix at few carriers, PAPR at many) change the outcome.")
