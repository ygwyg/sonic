import pytest

from sonic.config import OFDMConfig
from sonic.protocol import (
    HEADER_SIZE,
    HeaderError,
    PayloadType,
    TransmissionHeader,
    packet_sizes,
    sha256,
    split_packets,
    verify_packets,
)


def _header(**kw):
    cfg = kw.pop("config", OFDMConfig(band_modulations=("qpsk", None, "16qam")))
    base = dict(
        original_length=1000,
        payload_length=700,
        packet_size=256,
        n_packets=3,
        sha256=sha256(b"x"),
        config=cfg,
        payload_type=PayloadType.CODE,
        compression="lzma",
        filename="héllo wörld.py",
    )
    base.update(kw)
    return TransmissionHeader(**base)


def test_header_roundtrip():
    h = _header()
    raw = h.pack()
    assert len(raw) == HEADER_SIZE
    back = TransmissionHeader.unpack(raw, 48000)
    assert back.original_length == 1000 and back.payload_length == 700
    assert back.packet_size == 256 and back.n_packets == 3
    assert back.sha256 == h.sha256
    assert back.payload_type == PayloadType.CODE
    assert back.compression == "lzma"
    assert back.filename == "héllo wörld.py"
    assert back.config.band_modulations == ("qpsk", None, "16qam")
    assert back.config.n_fft == h.config.n_fft and back.config.code_rate == h.config.code_rate
    assert back.tx_id == h.tx_id


def test_header_rejects_corruption():
    raw = bytearray(_header().pack())
    raw[20] ^= 0xFF
    with pytest.raises(HeaderError, match="CRC"):
        TransmissionHeader.unpack(bytes(raw), 48000)


def test_header_rejects_bad_magic_and_version():
    raw = bytearray(_header().pack())
    raw[0:4] = b"NOPE"
    from sonic.fec.crc import crc32

    body = bytes(raw[:-4])
    with pytest.raises(HeaderError, match="magic"):
        TransmissionHeader.unpack(body + crc32(body).to_bytes(4, "big"), 48000)
    raw = bytearray(_header().pack())
    raw[4] = 9
    body = bytes(raw[:-4])
    with pytest.raises(HeaderError, match="version"):
        TransmissionHeader.unpack(body + crc32(body).to_bytes(4, "big"), 48000)


def test_header_rejects_inconsistent_packet_count():
    with pytest.raises(HeaderError, match="packet count"):
        TransmissionHeader.unpack(_header(n_packets=5).pack(), 48000)


def test_header_wrong_length():
    with pytest.raises(HeaderError):
        TransmissionHeader.unpack(b"\0" * 10, 48000)


def test_header_long_filename_truncated():
    h = _header(filename="x" * 100)
    assert len(TransmissionHeader.unpack(h.pack(), 48000).filename) == 31


def test_packets_roundtrip():
    payload = bytes(range(256)) * 3 + b"tail"
    pk = split_packets(payload, 256)
    assert len(pk) == 4
    assert [len(p) for p in pk] == packet_sizes(len(payload), 256)
    data, rep = verify_packets(pk)
    assert data == payload and rep.all_ok


def test_packets_detect_corruption_and_order():
    pk = split_packets(b"abcdefgh", 4)
    bad = bytearray(pk[1])
    bad[3] ^= 1
    data, rep = verify_packets([pk[0], bytes(bad)])
    assert data is None and rep.crc_failed == [1]
    data, rep = verify_packets([pk[1], pk[0]])
    assert data is None and rep.index_mismatch == [0, 1]


def test_empty_payload_single_packet():
    pk = split_packets(b"", 64)
    assert len(pk) == 1 and packet_sizes(0, 64) == [6]
    data, rep = verify_packets(pk)
    assert data == b"" and rep.all_ok
