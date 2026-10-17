"""Packet framing: ``index(u16) | payload | crc32(u32)``.

The header tells the receiver the packet payload size and the total
payload length, so every packet's exact size is known in advance and no
per-packet length field is needed. The index is redundant with position
but lets the receiver detect misplaced or duplicate packets and report
exactly which packets failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sonic.fec.crc import append_crc, verify_crc

PACKET_OVERHEAD = 2 + 4  # index + crc


def split_packets(payload: bytes, packet_size: int) -> list[bytes]:
    """Frame a payload into packets. An empty payload yields one empty packet."""
    if packet_size <= 0:
        raise ValueError("packet_size must be positive")
    chunks = [payload[i : i + packet_size] for i in range(0, len(payload), packet_size)] or [b""]
    return [append_crc(i.to_bytes(2, "big") + chunk) for i, chunk in enumerate(chunks)]


def packet_sizes(payload_length: int, packet_size: int) -> list[int]:
    """Framed packet sizes (bytes) for a payload of a given length."""
    if payload_length == 0:
        return [PACKET_OVERHEAD]
    n = (payload_length + packet_size - 1) // packet_size
    sizes = [packet_size + PACKET_OVERHEAD] * n
    rem = payload_length - packet_size * (n - 1)
    sizes[-1] = rem + PACKET_OVERHEAD
    return sizes


@dataclass
class PacketReport:
    n_packets: int
    ok: list[int] = field(default_factory=list)
    crc_failed: list[int] = field(default_factory=list)
    index_mismatch: list[int] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return len(self.ok) == self.n_packets and not self.crc_failed and not self.index_mismatch

    def describe(self) -> dict:
        return {
            "n_packets": self.n_packets,
            "n_ok": len(self.ok),
            "crc_failed": self.crc_failed,
            "index_mismatch": self.index_mismatch,
            "packet_error_rate": (self.n_packets - len(self.ok)) / max(1, self.n_packets),
        }


def verify_packets(framed: list[bytes]) -> tuple[bytes | None, PacketReport]:
    """Verify CRCs and indices; return the reassembled payload or None."""
    report = PacketReport(n_packets=len(framed))
    parts: list[bytes] = []
    for expected, pkt in enumerate(framed):
        if not verify_crc(pkt):
            report.crc_failed.append(expected)
            parts.append(b"")
            continue
        idx = int.from_bytes(pkt[:2], "big")
        if idx != expected:
            report.index_mismatch.append(expected)
            parts.append(b"")
            continue
        report.ok.append(expected)
        parts.append(pkt[2:-4])
    if report.all_ok:
        return b"".join(parts), report
    return None, report


def bytes_to_bits(data: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))


def bits_to_bytes(bits: np.ndarray) -> bytes:
    bits = np.asarray(bits, dtype=np.uint8)
    if bits.size % 8:
        raise ValueError("bit count must be a multiple of 8")
    return np.packbits(bits).tobytes()
