import numpy as np
import pytest

from sonic.fec import append_crc, convolutional as cc, crc32, deinterleave, interleave, verify_crc


@pytest.mark.parametrize("rate", ["1/2", "2/3", "3/4"])
def test_conv_roundtrip_clean(rate, rng):
    bits = rng.integers(0, 2, 3001).astype(np.uint8)
    coded = cc.encode(bits, rate)
    assert coded.size == cc.coded_length(bits.size, rate)
    llr = (1 - 2 * coded.astype(float)) * 3.0
    assert np.array_equal(cc.decode(llr, bits.size, rate), bits)


@pytest.mark.parametrize("rate", ["1/2", "3/4"])
def test_conv_corrects_noise(rate, rng):
    bits = rng.integers(0, 2, 4000).astype(np.uint8)
    coded = cc.encode(bits, rate)
    llr = (1 - 2 * coded.astype(float)) * 2.0 + rng.normal(0, 1.3 if rate == "1/2" else 0.9, coded.size)
    raw_errors = np.sum((llr < 0).astype(np.uint8) != coded)
    assert raw_errors > 50  # the channel really did corrupt bits
    assert np.array_equal(cc.decode(llr, bits.size, rate), bits)


def test_conv_empty_and_short():
    for n in (0, 1, 5):
        bits = np.ones(n, dtype=np.uint8)
        coded = cc.encode(bits)
        out = cc.decode((1 - 2 * coded.astype(float)), n)
        assert np.array_equal(out, bits)


def test_conv_wrong_llr_length():
    with pytest.raises(ValueError):
        cc.decode(np.zeros(10), 100)


def test_crc():
    assert crc32(b"123456789") == 0xCBF43926
    framed = append_crc(b"hello")
    assert verify_crc(framed)
    assert not verify_crc(framed[:-1] + bytes([framed[-1] ^ 1]))
    assert not verify_crc(b"abc")


def test_interleaver_is_a_permutation(rng):
    x = rng.integers(0, 100, 777)
    y = interleave(x)
    assert sorted(y) == sorted(x)
    assert not np.array_equal(x, y)
    assert np.array_equal(deinterleave(y), x)
