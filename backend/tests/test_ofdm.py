import numpy as np
import pytest

from sonic.config import OFDMConfig, header_config
from sonic.modulation import modulate
from sonic.ofdm import (
    bits_to_data_symbols,
    build_symbols,
    carriers_to_time,
    data_symbols_to_hard_bits,
    data_symbols_to_llr,
    papr_db,
    preamble_chirp,
    time_to_carriers,
)
from sonic.synchronization import detect_preambles


def test_config_geometry():
    cfg = OFDMConfig()
    assert cfg.active_carriers[0] * cfg.carrier_spacing >= cfg.f_low
    assert cfg.active_carriers[-1] * cfg.carrier_spacing <= cfg.f_high
    assert cfg.active_carriers[0] >= 1 and cfg.active_carriers[-1] < cfg.n_fft // 2
    assert len(cfg.pilot_carriers) + len(cfg.data_carriers) == len(cfg.active_carriers)
    assert set(cfg.pilot_carriers).isdisjoint(set(cfg.data_carriers))
    assert cfg.bits_per_ofdm_symbol == 2 * len(cfg.data_carriers)


def test_config_validation():
    with pytest.raises(ValueError):
        OFDMConfig(f_low=5000, f_high=4000)
    with pytest.raises(ValueError):
        OFDMConfig(f_high=30000)
    with pytest.raises(ValueError):
        OFDMConfig(cp_len=4096)
    with pytest.raises(ValueError):
        OFDMConfig(modulation="128qam")
    with pytest.raises(ValueError):
        OFDMConfig(band_modulations=(None, None))
    with pytest.raises(ValueError):
        OFDMConfig(n_fft=64, f_low=2000, f_high=2100)  # too few carriers


def test_fft_separates_overlapping_carriers(rng):
    """Many simultaneous carriers sum into one real waveform; the FFT recovers
    each carrier's complex symbol exactly."""
    cfg = OFDMConfig()
    n = len(cfg.active_carriers)
    X = (rng.normal(size=(3, n)) + 1j * rng.normal(size=(3, n))) / np.sqrt(2)
    x = carriers_to_time(cfg, X, cfg.active_carriers)
    assert x.shape == (3, cfg.symbol_len)
    assert np.isrealobj(x)
    # cyclic prefix is a copy of the symbol tail
    assert np.allclose(x[:, : cfg.cp_len], x[:, -cfg.cp_len :])
    Y = time_to_carriers(cfg, x[:, cfg.cp_len :], cfg.active_carriers)
    assert np.allclose(Y, X, atol=1e-9)


def test_overlap_is_a_sum_of_sinusoids():
    cfg = OFDMConfig(n_fft=256, cp_len=0, f_low=2000, f_high=10000, pilot_spacing=2)
    carriers = cfg.active_carriers[:5]
    X = np.ones((1, 5), dtype=complex)
    x = carriers_to_time(cfg, X, carriers)[0]
    n = np.arange(cfg.n_fft)
    expected = sum(2 * np.cos(2 * np.pi * k * n / cfg.n_fft) / np.sqrt(cfg.n_fft) for k in carriers)
    assert np.allclose(x, expected)


def test_bit_loading_mapping_roundtrip(rng):
    cfg = OFDMConfig(band_modulations=("bpsk", "qpsk", None, "16qam", "64qam"))
    B = cfg.bits_per_ofdm_symbol
    assert B == int(cfg.bits_per_data_carrier.sum())
    bits = rng.integers(0, 2, 4 * B).astype(np.uint8)
    syms = bits_to_data_symbols(cfg, bits)
    assert syms.shape == (4, len(cfg.enabled_data_carriers))
    assert np.array_equal(data_symbols_to_hard_bits(cfg, syms), bits)
    llr = data_symbols_to_llr(cfg, syms, 0.1)
    assert np.array_equal((llr < 0).astype(np.uint8), bits)


def test_build_symbols_places_pilots():
    cfg = OFDMConfig()
    d = modulate(np.zeros(2 * len(cfg.data_carriers), dtype=np.uint8), "qpsk")
    rows = build_symbols(cfg, d[None, :])
    assert rows.shape == (1, len(cfg.active_carriers))
    assert np.all(np.abs(rows[0, :: cfg.pilot_spacing]) == 1)


def test_preamble_detection_with_offset_and_noise(rng):
    fs = 48000
    ch = preamble_chirp(fs)
    x = np.concatenate([np.zeros(12345), ch, np.zeros(5000)]) * 0.3
    x += rng.normal(0, 0.1, x.size)
    cands = detect_preambles(x, fs)
    assert cands and cands[0].position == 12345


def test_preamble_not_detected_in_noise(rng):
    assert detect_preambles(rng.normal(0, 0.1, 48000), 48000) == []


def test_papr():
    assert papr_db(np.ones(100)) == 0.0
    assert papr_db(np.array([0, 0, 0, 1.0])) == pytest.approx(10 * np.log10(4))


def test_header_config_fixed():
    h = header_config(48000)
    assert h.modulation == "bpsk" and h.code_rate == "1/2"
    assert header_config(48000) == header_config(48000)
