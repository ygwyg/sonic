"""Frame layout shared by transmitter and receiver.

A transmission is laid out in time as::

    | chirp | guard | header training | header data | payload training |
    | payload data | tail guard |

Everything about the header section is fixed by :func:`header_config`;
everything about the payload section is derived from the decoded header.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sonic.config import OFDMConfig, TAIL_GUARD, header_config
from sonic.fec.convolutional import coded_length
from sonic.ofdm.preamble import preamble_chirp, preamble_guard_samples, preamble_length
from sonic.protocol.header import HEADER_SIZE
from sonic.protocol.packets import packet_sizes


HEADER_REPEATS = 2  # the coded header is sent twice; LLRs are combined


def header_coded_bits() -> int:
    return coded_length(HEADER_SIZE * 8, "1/2")


def header_symbols_per_copy(hcfg: OFDMConfig) -> int:
    return int(np.ceil(header_coded_bits() / hcfg.bits_per_ofdm_symbol))


def header_symbol_count(hcfg: OFDMConfig) -> int:
    return HEADER_REPEATS * header_symbols_per_copy(hcfg)


def payload_coded_lengths(payload_length: int, cfg: OFDMConfig) -> list[int]:
    """Coded bit count of every packet, in order."""
    return [coded_length(n * 8, cfg.code_rate) for n in packet_sizes(payload_length, cfg.packet_size)]


def payload_symbol_count(payload_length: int, cfg: OFDMConfig) -> int:
    total = sum(payload_coded_lengths(payload_length, cfg))
    return int(np.ceil(total / cfg.bits_per_ofdm_symbol))


@dataclass
class FrameLayout:
    sample_rate: int
    preamble_start: int
    header_start: int
    n_header_symbols: int
    payload_start: int
    n_payload_symbols: int
    payload_end: int
    total_samples: int
    hcfg: OFDMConfig
    cfg: OFDMConfig

    def sections(self) -> list[dict]:
        fs = self.sample_rate
        ch = len(preamble_chirp(fs))
        g = preamble_guard_samples(fs)
        hs = self.hcfg.symbol_len
        ps = self.cfg.symbol_len
        return [
            {"name": "preamble", "start": self.preamble_start, "end": self.preamble_start + ch},
            {"name": "guard", "start": self.preamble_start + ch, "end": self.header_start},
            {
                "name": "header_training",
                "start": self.header_start,
                "end": self.header_start + self.hcfg.n_training * hs,
            },
            {
                "name": "header_data",
                "start": self.header_start + self.hcfg.n_training * hs,
                "end": self.payload_start,
            },
            {
                "name": "payload_training",
                "start": self.payload_start,
                "end": self.payload_start + self.cfg.n_training * ps,
            },
            {"name": "payload_data", "start": self.payload_start + self.cfg.n_training * ps, "end": self.payload_end},
            {"name": "tail_guard", "start": self.payload_end, "end": self.total_samples},
        ]


def frame_layout(payload_length: int, cfg: OFDMConfig, preamble_start: int = 0) -> FrameLayout:
    fs = cfg.sample_rate
    hcfg = header_config(fs)
    header_start = preamble_start + preamble_length(fs)
    n_h = header_symbol_count(hcfg)
    payload_start = header_start + (hcfg.n_training + n_h) * hcfg.symbol_len
    n_p = payload_symbol_count(payload_length, cfg)
    payload_end = payload_start + (cfg.n_training + n_p) * cfg.symbol_len
    total = payload_end + int(round(TAIL_GUARD * fs))
    return FrameLayout(fs, preamble_start, header_start, n_h, payload_start, n_p, payload_end, total, hcfg, cfg)
