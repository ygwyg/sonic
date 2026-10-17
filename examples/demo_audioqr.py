#!/usr/bin/env python3
"""Demonstration 3 — Audio QR: short text <-> sound."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from sonic import PRESETS, decode, encode  # noqa: E402
from sonic.audio import read_wav, write_wav  # noqa: E402
from sonic.channel import apply_channel, get_channel  # noqa: E402

msg = "https://example.com/sonic?demo=audio-qr ✓ (max 4000 chars)"
cfg = PRESETS["audioqr"]
wave, info = encode(msg.encode(), cfg, payload_type="url", amplitude=0.6)
out = os.path.join(HERE, "audio", "audioqr_url.wav")
write_wav(out, wave, cfg.sample_rate)
print(f"'{msg}' -> {out} ({info.duration_s:.2f} s)")

clip = read_wav(out)
res = decode(clip.samples, clip.sample_rate)
print("decoded from file :", res.text)

rx = apply_channel(clip.samples, clip.sample_rate, get_channel("noisy_room"))
res = decode(rx, clip.sample_rate)
print("decoded via synthetic noisy room:", res.text if res.success else f"FAILED ({res.error})")
