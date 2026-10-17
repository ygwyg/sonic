"""The receiver must fail clearly, never emit corrupted data."""

import io

import numpy as np
import pytest

from sonic.audio import WavError, read_wav, wav_bytes, write_wav
from sonic.config import PRESETS
from sonic.receiver import decode
from sonic.transmitter import encode

FS = 48000


def test_silent_audio():
    res = decode(np.zeros(FS), FS)
    assert not res.success and "silent" in res.error


def test_empty_audio():
    res = decode(np.zeros(0), FS)
    assert not res.success and "empty" in res.error


def test_random_noise_no_preamble(rng):
    res = decode(rng.normal(0, 0.1, FS), FS)
    assert not res.success and "no preamble" in res.error


def test_non_finite_samples():
    x = np.zeros(FS)
    x[10] = np.nan
    res = decode(x, FS)
    assert not res.success and "non-finite" in res.error


def test_integer_and_stereo_input(python_source):
    wave, info = encode(python_source[:800], PRESETS["default"])
    pcm = (wave * 32767).astype(np.int16)
    assert decode(pcm, FS).data == python_source[:800]
    stereo = np.stack([wave, wave], axis=1)
    assert decode(stereo, FS).data == python_source[:800]


def test_truncated_recording_reports_missing_packets(python_source):
    wave, info = encode(python_source[:4000], PRESETS["default"])
    cut = wave[: int(len(wave) * 0.7)]
    res = decode(cut, FS)
    assert not res.success and res.data is None
    assert res.header is not None  # the header was fine
    assert res.diagnostics["packets"]["missing"] > 0
    assert "missing" in res.error


def test_recording_cut_inside_header(python_source):
    wave, info = encode(python_source[:800], PRESETS["default"])
    res = decode(wave[: info.layout.header_start + 3000], FS)
    assert not res.success and "header" in res.error


def test_corrupted_packet_is_detected_not_emitted(python_source):
    wave, info = encode(python_source[:4000], PRESETS["default"], compression="none")
    sec = next(s for s in info.layout.sections() if s["name"] == "payload_data")
    bad = wave.copy()
    # obliterate ~12 OFDM symbols (more than a whole packet) in the payload
    mid = (sec["start"] + sec["end"]) // 2
    bad[mid : mid + 12 * info.config.symbol_len] = 0.0
    res = decode(bad, FS)
    assert not res.success and res.data is None
    assert res.diagnostics["packets"]["n_ok"] < res.header.n_packets
    assert "CRC" in res.error


def test_hard_clipping_still_decodes(python_source):
    wave, info = encode(python_source[:2000], PRESETS["default"])
    clipped = np.clip(wave * 3.0, -1.0, 1.0)
    res = decode(clipped, FS)
    assert res.success, res.error
    assert res.diagnostics["input"]["clipped_fraction"] > 0.001


def test_wrong_sample_rate_declared(python_source):
    wave, info = encode(python_source[:1000], PRESETS["default"])
    res = decode(wave, 44100)
    assert not res.success


def test_invalid_wav_files(tmp_path):
    p = tmp_path / "bad.wav"
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt junk")
    with pytest.raises(WavError):
        read_wav(str(p))
    with pytest.raises(WavError):
        read_wav(b"not a wav at all")


def test_wav_roundtrip(tmp_path, python_source):
    wave, info = encode(python_source[:1000], PRESETS["default"])
    p = tmp_path / "t.wav"
    write_wav(str(p), wave, FS)
    clip = read_wav(str(p))
    assert clip.sample_rate == FS and clip.channels == 1
    assert decode(clip.samples, clip.sample_rate).data == python_source[:1000]
    clip2 = read_wav(wav_bytes(wave, FS))
    assert np.allclose(clip2.samples, clip.samples)


def test_wav_length_limit(tmp_path):
    p = tmp_path / "long.wav"
    write_wav(str(p), np.zeros(FS * 3), FS)
    with pytest.raises(WavError, match="longer"):
        read_wav(str(p), max_seconds=2)
