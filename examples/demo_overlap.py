#!/usr/bin/env python3
"""Demonstration 2 — overlapping waves and their separation by the FFT.

Prints how one OFDM symbol is the sum of hundreds of sinusoids and how the
receiver's FFT recovers every carrier's symbol. The web Explorer shows the
same data graphically.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from sonic import OFDMConfig, encode  # noqa: E402
from sonic.analysis import overlapping_carriers_demo  # noqa: E402
from sonic.modulation import demodulate_hard  # noqa: E402
from sonic.ofdm import active_positions, time_to_carriers  # noqa: E402

cfg = OFDMConfig(modulation="16qam")
wave, info = encode(open(os.path.join(HERE, "hello.py"), "rb").read(), cfg, compression="none")
sec = next(s for s in info.layout.sections() if s["name"] == "payload_data")
symbol = wave[sec["start"] : sec["start"] + cfg.symbol_len]

demo = overlapping_carriers_demo(cfg, symbol, n_show=5)
print(f"one OFDM symbol = {demo['n_total_carriers']} simultaneous carriers "
      f"({cfg.f_low:.0f}-{cfg.f_high:.0f} Hz, spacing {cfg.carrier_spacing:.2f} Hz)")
for c in demo["components"]:
    print(f"  carrier {c['carrier']:4d} @ {c['frequency_hz']:8.1f} Hz  |X|={c['magnitude']:.3f}  phase={c['phase_rad']:+.2f} rad")
comp = np.array(demo["composite"])
summed = sum(np.array(c["samples"]) for c in demo["components"])
print(f"first 5 samples of the composite: {comp[:5].round(4)}")
print(f"sum of the {demo['shown']} strongest carriers explains "
      f"{100 * np.sum(summed**2) / np.sum(comp**2):.1f}% of the symbol energy")

# the receiver side: FFT separates the carriers and recovers the symbols
Y = time_to_carriers(cfg, symbol[cfg.cp_len :][None, :], cfg.active_carriers)[0]
_, _, enabled = active_positions(cfg)
rx = Y[enabled] / (np.abs(info.data_symbols[0]).mean() / np.abs(Y[enabled]).mean())  # undo the global gain
tx = info.data_symbols[0]
scale = np.vdot(rx, tx) / np.vdot(rx, rx)
rx = rx * scale
bits_tx = demodulate_hard(tx, "16qam")
bits_rx = demodulate_hard(rx, "16qam")
print(f"recovered {len(tx)} 16-QAM symbols from the FFT; bit errors: {int(np.sum(bits_tx != bits_rx))} of {bits_tx.size}")
print(f"max symbol error after gain normalisation: {np.max(np.abs(rx - tx)):.2e}")
