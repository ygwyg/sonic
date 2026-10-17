"""CRC-32 (IEEE 802.3) helpers used for header and packet integrity."""

from __future__ import annotations

import zlib


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def append_crc(data: bytes) -> bytes:
    return data + crc32(data).to_bytes(4, "big")


def verify_crc(data_with_crc: bytes) -> bool:
    if len(data_with_crc) < 4:
        return False
    body, tag = data_with_crc[:-4], data_with_crc[-4:]
    return crc32(body) == int.from_bytes(tag, "big")
