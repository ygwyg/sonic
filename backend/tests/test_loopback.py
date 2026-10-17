"""Digital loopback: encode -> decode must be byte-for-byte identical."""

import hashlib
import lzma
import os

import numpy as np
import pytest

from sonic.config import OFDMConfig, PRESETS
from sonic.protocol import PayloadType
from sonic.receiver import decode
from sonic.transmitter import EncodeError, encode, estimate


def _roundtrip(data: bytes, cfg: OFDMConfig, **kw):
    wave, info = encode(data, cfg, **kw)
    assert np.max(np.abs(wave)) <= 0.8 + 1e-9
    assert np.all(np.isfinite(wave))
    res = decode(wave, cfg.sample_rate, reference=info)
    assert res.success, res.error
    assert res.data == data
    assert hashlib.sha256(res.data).digest() == info.header.sha256
    assert res.diagnostics["sha256"]["match"]
    return res, info


@pytest.mark.parametrize("preset", sorted(PRESETS))
def test_presets_roundtrip_python_source(preset, python_source):
    res, info = _roundtrip(python_source, PRESETS[preset], filename="config.py", payload_type=PayloadType.CODE)
    assert res.header.filename == "config.py"
    assert res.header.payload_type == PayloadType.CODE
    assert res.diagnostics["raw_ber"] == 0.0
    assert res.diagnostics["packets"]["packet_error_rate"] == 0.0


def test_empty_file(small_cfg):
    res, info = _roundtrip(b"", small_cfg)
    assert res.header.n_packets == 1 and res.header.original_length == 0


def test_one_byte(small_cfg):
    _roundtrip(b"\x7f", small_cfg)


def test_random_binary(small_cfg):
    data = os.urandom(3000)
    res, info = _roundtrip(data, small_cfg)
    assert info.compression.algorithm == "none"


def test_unicode_text(small_cfg):
    text = "Grüße aus München — 日本語テキスト — emoji 🎧🔊 — العربية".encode("utf-8") * 20
    res, _ = _roundtrip(text, small_cfg, payload_type="text")
    assert res.text == text.decode()


def test_already_compressed_payload(small_cfg):
    data = lzma.compress(b"the quick brown fox " * 500)
    res, info = _roundtrip(data, small_cfg)
    assert info.compression.algorithm == "none"
    assert len(info.compression.data) == len(data)


@pytest.mark.parametrize("compression", ["none", "zlib", "lzma", "codeaware"])
def test_explicit_compression(compression, python_source, small_cfg):
    res, info = _roundtrip(python_source, small_cfg, compression=compression, filename="config.py")
    assert res.header.compression == info.compression.algorithm


def test_large_file(python_source):
    data = (python_source * 8)[:60000]
    cfg = PRESETS["fast"]
    res, info = _roundtrip(data, cfg, compression="none")
    assert info.duration_s < 20


@pytest.mark.parametrize("modulation,rate", [("bpsk", "1/2"), ("qpsk", "3/4"), ("16qam", "2/3"), ("64qam", "3/4"), ("256qam", "3/4")])
def test_all_modulations_and_rates(modulation, rate, python_source):
    cfg = OFDMConfig(modulation=modulation, code_rate=rate)
    _roundtrip(python_source[:3000], cfg)


def test_adaptive_bands_roundtrip(python_source):
    cfg = OFDMConfig(band_modulations=("64qam", "16qam", None, "qpsk", "bpsk", "256qam", "qpsk", "16qam"), code_rate="2/3")
    res, info = _roundtrip(python_source[:4000], cfg)
    assert res.header.config.band_modulations == cfg.band_modulations


def test_other_sample_rates(python_source):
    for fs in (16000, 44100, 96000):
        cfg = OFDMConfig(sample_rate=fs, n_fft=2048, cp_len=512, f_low=1500, f_high=min(7000, fs / 2 - 500))
        _roundtrip(python_source[:1500], cfg)


def test_amplitude_and_estimate(small_cfg):
    wave, info = encode(b"x" * 500, small_cfg, amplitude=0.3, compression="none")
    assert abs(np.max(np.abs(wave)) - 0.3) < 1e-9
    est = estimate(small_cfg, 500)
    assert est["duration_s"] == pytest.approx(info.duration_s, rel=0.01)


def test_input_limits(small_cfg):
    with pytest.raises(EncodeError):
        encode(b"x" * 100, small_cfg, max_input_bytes=10)
    with pytest.raises(EncodeError):
        encode("not bytes", small_cfg)  # type: ignore[arg-type]


def test_two_transmissions_in_one_recording(small_cfg):
    w1, i1 = encode(b"first message", small_cfg)
    w2, i2 = encode(b"second message", small_cfg)
    rec = np.concatenate([np.zeros(5000), w1, np.zeros(9000), w2, np.zeros(1000)])
    r0 = decode(rec, small_cfg.sample_rate, candidate_index=0)
    r1 = decode(rec, small_cfg.sample_rate, candidate_index=1)
    assert {r0.data, r1.data} == {b"first message", b"second message"}
    assert len(r0.diagnostics["sync"]["candidates"]) == 2
