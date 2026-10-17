"""Versioned binary transmission header.

Layout (version 1, big-endian, fixed 111 bytes):

======  =====  ====================================================
offset  size   field
======  =====  ====================================================
0       4      magic ``b"SNC1"``
4       1      protocol version (1)
5       4      transmission id (random uint32)
9       1      payload type (see :class:`PayloadType`)
10      1      compression algorithm (see :data:`COMPRESSION_CODES`)
11      4      original payload length (bytes, before compression)
15      4      transmitted payload length (bytes, after compression)
19      2      packet payload size (bytes)
21      2      packet count
23      32     SHA-256 of the original payload
55      1      FEC code rate code
56      2      payload n_fft
58      2      payload cyclic prefix length
60      2      payload f_low (Hz)
62      2      payload f_high (Hz)
64      1      payload pilot spacing
65      1      payload default modulation code
66      1      payload n_training
67      1      number of adaptive bands (0 = uniform modulation)
68      8      16 nibbles: per-band modulation code (0 = disabled)
76      31     file name (UTF-8, zero padded)
107     4      CRC-32 of bytes 0..106
======  =====  ====================================================

Validation: magic and version must match, CRC must verify, every enum
code must be known, lengths must be consistent, and the payload
configuration must construct a valid :class:`~sonic.config.OFDMConfig`.
A header that fails any check is rejected; nothing is decoded from it.

The header is always transmitted with the fixed robust configuration
(:func:`sonic.config.header_config`), so the receiver never needs header
contents in order to read the header.
"""

from __future__ import annotations

import hashlib
import secrets
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from sonic.config import (
    CODE_RATE_CODES,
    CODE_TO_MODULATION,
    CODE_TO_RATE,
    MAX_BANDS,
    MODULATION_CODES,
    OFDMConfig,
)
from sonic.fec.crc import crc32

MAGIC = b"SNC1"
PROTOCOL_VERSION = 1
HEADER_SIZE = 111
FILENAME_FIELD = 31
MAX_PAYLOAD_BYTES = (1 << 32) - 1
MAX_PACKETS = 65535

_STRUCT = struct.Struct(">4sBIBBIIHH32sBHHHHBBBB8s31sI")
assert _STRUCT.size == HEADER_SIZE


class PayloadType(IntEnum):
    BINARY = 0
    TEXT = 1
    JSON = 2
    URL = 3
    CONTACT = 4
    CODE = 5


COMPRESSION_CODES: dict[str, int] = {"none": 0, "zlib": 1, "lzma": 2, "zstd": 3, "codeaware": 4}
CODE_TO_COMPRESSION: dict[int, str] = {v: k for k, v in COMPRESSION_CODES.items()}


class HeaderError(ValueError):
    """Raised when a header is malformed, corrupted or unsupported."""


@dataclass
class TransmissionHeader:
    original_length: int
    payload_length: int
    packet_size: int
    n_packets: int
    sha256: bytes
    config: OFDMConfig
    payload_type: PayloadType = PayloadType.BINARY
    compression: str = "none"
    filename: str = ""
    tx_id: int = field(default_factory=lambda: secrets.randbits(32))
    version: int = PROTOCOL_VERSION

    # --------------------------------------------------------------- pack
    def pack(self) -> bytes:
        cfg = self.config
        if self.payload_length > MAX_PAYLOAD_BYTES or self.original_length > MAX_PAYLOAD_BYTES:
            raise HeaderError("payload too large for 32-bit length field")
        if self.n_packets > MAX_PACKETS:
            raise HeaderError("too many packets for 16-bit packet count")
        if cfg.n_fft > 65535 or cfg.cp_len > 65535:
            raise HeaderError("n_fft/cp_len must fit 16 bits")
        name = self.filename.encode("utf-8")[:FILENAME_FIELD]
        # avoid cutting a multi-byte character in half
        while name and (name[-1] & 0xC0) == 0x80 and len(name.decode("utf-8", "ignore").encode()) != len(name):
            name = name[:-1]
        bands = bytearray(8)
        for i, m in enumerate(cfg.band_modulations):
            code = 0 if m is None else MODULATION_CODES[m]
            if i % 2 == 0:
                bands[i // 2] |= code << 4
            else:
                bands[i // 2] |= code
        body = _STRUCT.pack(
            MAGIC,
            self.version,
            self.tx_id & 0xFFFFFFFF,
            int(self.payload_type),
            COMPRESSION_CODES[self.compression],
            self.original_length,
            self.payload_length,
            self.packet_size,
            self.n_packets,
            self.sha256,
            CODE_RATE_CODES[cfg.code_rate],
            cfg.n_fft,
            cfg.cp_len,
            int(round(cfg.f_low)),
            int(round(cfg.f_high)),
            cfg.pilot_spacing,
            MODULATION_CODES[cfg.modulation],
            cfg.n_training,
            len(cfg.band_modulations),
            bytes(bands),
            name.ljust(FILENAME_FIELD, b"\0"),
            0,
        )[:-4]
        return body + crc32(body).to_bytes(4, "big")

    # ------------------------------------------------------------- unpack
    @classmethod
    def unpack(cls, raw: bytes, sample_rate: int) -> "TransmissionHeader":
        if len(raw) != HEADER_SIZE:
            raise HeaderError(f"header must be {HEADER_SIZE} bytes, got {len(raw)}")
        body, tag = raw[:-4], raw[-4:]
        if crc32(body) != int.from_bytes(tag, "big"):
            raise HeaderError("header CRC mismatch")
        (
            magic,
            version,
            tx_id,
            ptype,
            comp,
            orig_len,
            payload_len,
            packet_size,
            n_packets,
            sha,
            rate_code,
            n_fft,
            cp_len,
            f_low,
            f_high,
            pilot_spacing,
            mod_code,
            n_training,
            n_bands,
            bands,
            name,
            _crc,
        ) = _STRUCT.unpack(raw)
        if magic != MAGIC:
            raise HeaderError("bad magic; not a Sonic transmission")
        if version != PROTOCOL_VERSION:
            raise HeaderError(f"unsupported protocol version {version}")
        if comp not in CODE_TO_COMPRESSION:
            raise HeaderError(f"unknown compression code {comp}")
        if rate_code not in CODE_TO_RATE:
            raise HeaderError(f"unknown FEC rate code {rate_code}")
        if mod_code not in CODE_TO_MODULATION or mod_code == 0:
            raise HeaderError(f"unknown modulation code {mod_code}")
        if n_bands > MAX_BANDS:
            raise HeaderError(f"too many bands: {n_bands}")
        try:
            ptype_enum = PayloadType(ptype)
        except ValueError as e:
            raise HeaderError(f"unknown payload type {ptype}") from e
        band_mods: list[Optional[str]] = []
        for i in range(n_bands):
            code = (bands[i // 2] >> 4) if i % 2 == 0 else (bands[i // 2] & 0xF)
            if code not in CODE_TO_MODULATION:
                raise HeaderError(f"unknown band modulation code {code}")
            band_mods.append(CODE_TO_MODULATION[code])
        if packet_size == 0:
            raise HeaderError("packet_size must be > 0")
        expected_packets = max(1, (payload_len + packet_size - 1) // packet_size)
        if n_packets != expected_packets:
            raise HeaderError(
                f"inconsistent packet count: header says {n_packets}, lengths imply {expected_packets}"
            )
        try:
            cfg = OFDMConfig(
                sample_rate=sample_rate,
                n_fft=n_fft,
                cp_len=cp_len,
                f_low=float(f_low),
                f_high=float(f_high),
                pilot_spacing=pilot_spacing,
                modulation=CODE_TO_MODULATION[mod_code],
                code_rate=CODE_TO_RATE[rate_code],
                band_modulations=tuple(band_mods),
                n_training=n_training,
                packet_size=packet_size,
            )
        except ValueError as e:
            raise HeaderError(f"invalid payload configuration in header: {e}") from e
        return cls(
            original_length=orig_len,
            payload_length=payload_len,
            packet_size=packet_size,
            n_packets=n_packets,
            sha256=sha,
            config=cfg,
            payload_type=ptype_enum,
            compression=CODE_TO_COMPRESSION[comp],
            filename=name.rstrip(b"\0").decode("utf-8", "replace"),
            tx_id=tx_id,
            version=version,
        )

    def describe(self) -> dict:
        return {
            "version": self.version,
            "tx_id": self.tx_id,
            "payload_type": self.payload_type.name.lower(),
            "compression": self.compression,
            "original_length": self.original_length,
            "payload_length": self.payload_length,
            "packet_size": self.packet_size,
            "n_packets": self.n_packets,
            "sha256": self.sha256.hex(),
            "filename": self.filename,
            "config": self.config.describe(),
        }


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()
