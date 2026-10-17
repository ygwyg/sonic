"""Noise resistance and impairment handling through the channel simulator."""

import numpy as np
import pytest

from sonic.channel import CHANNEL_PRESETS, ChannelConfig, apply_channel, get_channel
from sonic.config import PRESETS, OFDMConfig
from sonic.receiver import decode
from sonic.transmitter import encode

FS = 48000


def _run(data, cfg, channel):
    wave, info = encode(data, cfg, compression="none")
    rx = apply_channel(wave, FS, channel)
    return decode(rx, FS, reference=info), info


def test_awgn_snr_is_calibrated(rng):
    x = rng.normal(0, 0.1, 48000)
    y = apply_channel(x, FS, ChannelConfig(snr_db=10.0))
    noise = y - x
    measured = 10 * np.log10(np.mean(x**2) / np.mean(noise**2))
    assert abs(measured - 10.0) < 0.3


def test_ber_decreases_with_snr(python_source):
    cfg = OFDMConfig()
    bers = []
    for snr in (4.0, 8.0, 14.0):
        res, _ = _run(python_source[:2000], cfg, ChannelConfig(snr_db=snr))
        bers.append(res.diagnostics["raw_ber"])
    assert bers[0] > bers[1] > bers[2]
    assert bers[2] == 0.0


def test_qpsk_half_rate_decodes_at_moderate_snr(python_source):
    res, _ = _run(python_source[:2000], OFDMConfig(), ChannelConfig(snr_db=6.0))
    assert res.success, res.error
    assert res.diagnostics["raw_ber"] > 0  # FEC actually corrected errors


def test_low_snr_fails_cleanly(python_source):
    res, _ = _run(python_source[:2000], OFDMConfig(modulation="64qam", code_rate="3/4"), ChannelConfig(snr_db=5.0))
    assert not res.success and res.data is None
    assert "integrity" in res.error or "header" in res.error


@pytest.mark.parametrize("name", ["ideal", "quiet_room", "noisy_room", "reverberant_room"])
def test_room_presets_with_robust_profile(name, python_source):
    res, _ = _run(python_source[:1500], PRESETS["robust"], get_channel(name))
    assert res.success, (name, res.error)


@pytest.mark.parametrize("name", ["quiet_room", "noisy_room"])
def test_room_presets_with_default_profile(name, python_source):
    res, _ = _run(python_source[:2000], PRESETS["default"], get_channel(name))
    assert res.success, (name, res.error)


def test_difficult_channel_header_still_decodes(python_source):
    res, _ = _run(python_source[:1500], PRESETS["robust"], get_channel("difficult"))
    assert res.header is not None  # header is robust even where the payload may fail


@pytest.mark.parametrize("ppm", [-200.0, 60.0, 250.0])
def test_sample_rate_mismatch_tracking(ppm, python_source):
    res, _ = _run(python_source[:3000], PRESETS["default"], ChannelConfig(sample_rate_ppm=ppm, snr_db=25.0))
    assert res.success, res.error
    drift = res.diagnostics["payload_section"]["timing_drift_samples"]
    lay = res.diagnostics["layout"]
    # drift is measured relative to the payload training symbols
    expected = ppm * 1e-6 * (lay["payload_data"][1] - lay["payload_training"][0])
    assert abs(drift[-1] - expected) < max(3.0, 0.1 * abs(expected))


def test_timing_offset_and_multipath(python_source):
    ch = ChannelConfig(timing_offset_s=0.37, multipath=[(0.002, 0.5), (0.005, 0.3)], snr_db=25.0)
    res, _ = _run(python_source[:2000], OFDMConfig(), ch)
    assert res.success, res.error
    assert abs(res.diagnostics["sync"]["candidates"][0]["position"] - 0.37 * FS) <= 2


def test_frequency_offset_and_clipping(python_source):
    ch = ChannelConfig(frequency_offset_hz=1.0, clip_level=0.35, snr_db=25.0)
    res, _ = _run(python_source[:2000], OFDMConfig(), ch)
    assert res.success, res.error
    assert res.diagnostics["input"]["peak"] <= 0.35 + 1e-9


def test_interference(python_source):
    ch = ChannelConfig(tones=[(4000.0, 0.3), (6500.0, 0.2)], burst_level_db=-3.0, burst_duty=0.03, snr_db=20.0)
    res, _ = _run(python_source[:2000], OFDMConfig(), ch)
    assert res.success, res.error


def test_channel_presets_describe_roundtrip():
    for name, cfg in CHANNEL_PRESETS.items():
        assert ChannelConfig.from_dict(cfg.describe()) == cfg
