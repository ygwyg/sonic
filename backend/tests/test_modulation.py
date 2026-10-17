import numpy as np
import pytest

from sonic.config import BITS_PER_SYMBOL, MODULATIONS
from sonic.modulation import demodulate_hard, demodulate_soft, get_constellation, modulate


@pytest.mark.parametrize("mod", MODULATIONS)
def test_constellation_unit_energy_and_gray(mod):
    c = get_constellation(mod)
    assert len(c.points) == 2**c.bits
    assert abs(np.mean(np.abs(c.points) ** 2) - 1.0) < 0.06
    if c.bits_per_dim > 1:
        # adjacent PAM levels differ in exactly one bit (Gray code)
        for i in range(len(c.levels) - 1):
            assert np.sum(c.level_bits[i] != c.level_bits[i + 1]) == 1


@pytest.mark.parametrize("mod", MODULATIONS)
def test_map_demap_roundtrip(mod, rng):
    b = rng.integers(0, 2, BITS_PER_SYMBOL[mod] * 500).astype(np.uint8)
    s = modulate(b, mod)
    assert np.array_equal(demodulate_hard(s, mod), b)
    llr = demodulate_soft(s, mod, 0.05)
    assert np.array_equal((llr < 0).astype(np.uint8), b)


@pytest.mark.parametrize("mod", MODULATIONS)
def test_soft_llr_magnitude_scales_with_noise(mod, rng):
    b = rng.integers(0, 2, BITS_PER_SYMBOL[mod] * 100).astype(np.uint8)
    s = modulate(b, mod)
    l1 = demodulate_soft(s, mod, 0.1)
    l2 = demodulate_soft(s, mod, 1.0)
    assert np.mean(np.abs(l1)) > np.mean(np.abs(l2))


def test_hard_decisions_under_noise_qpsk(rng):
    b = rng.integers(0, 2, 20000).astype(np.uint8)
    s = modulate(b, "qpsk")
    noisy = s + (rng.normal(0, 0.3, s.size) + 1j * rng.normal(0, 0.3, s.size))
    ber = np.mean(demodulate_hard(noisy, "qpsk") != b)
    assert 0.001 < ber < 0.05


def test_modulate_rejects_bad_length():
    with pytest.raises(ValueError):
        modulate(np.zeros(3, dtype=np.uint8), "qpsk")
