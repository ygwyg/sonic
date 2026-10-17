#!/usr/bin/env python3
"""Demonstration 1 — digital loopback.

Encode hello.py into a WAV file, decode the WAV file, verify SHA-256.
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from sonic import OFDMConfig, decode, encode  # noqa: E402
from sonic.audio import read_wav, write_wav  # noqa: E402

src = open(os.path.join(HERE, "hello.py"), "rb").read()
cfg = OFDMConfig()  # default: 2–10 kHz, 2048-point FFT, QPSK rate 1/2
wave, info = encode(src, cfg, filename="hello.py", payload_type="code")
out = os.path.join(HERE, "audio", "hello_py_default.wav")
write_wav(out, wave, cfg.sample_rate)
print(f"encoded {len(src)} B -> {info.duration_s:.2f} s of audio ({info.net_bitrate:.0f} bit/s net), "
      f"{len(cfg.active_carriers)} carriers, compression={info.compression.algorithm}")

clip = read_wav(out)
res = decode(clip.samples, clip.sample_rate)
assert res.success, res.error
assert res.data == src
print("SHA-256 original    ", hashlib.sha256(src).hexdigest())
print("SHA-256 reconstructed", hashlib.sha256(res.data).hexdigest())
print("byte-for-byte identical:", res.data == src)
