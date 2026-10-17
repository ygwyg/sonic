"""Transmitter: bytes -> compressed payload -> packets -> FEC -> symbols ->
OFDM waveform.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from sonic.config import OFDMConfig, header_config
from sonic.compression import choose_compression, CompressionChoice
from sonic.compression.codeaware import detect_language
from sonic.fec import convolutional, interleave, scramble
from sonic.ofdm import (
    bits_to_data_symbols,
    build_symbols,
    carriers_to_time,
    pad_bits,
    papr_db,
    preamble_chirp,
    preamble_guard_samples,
    training_rows,
)
from sonic.protocol import PayloadType, TransmissionHeader, bytes_to_bits, sha256, split_packets
from sonic.protocol.layout import HEADER_REPEATS, FrameLayout, frame_layout

DEFAULT_AMPLITUDE = 0.8
MAX_INPUT_BYTES = 16 * 1024 * 1024


class EncodeError(ValueError):
    pass


@dataclass
class TransmissionInfo:
    sample_rate: int
    config: OFDMConfig
    header: TransmissionHeader
    layout: FrameLayout
    compression: CompressionChoice
    n_samples: int
    duration_s: float
    peak: float
    rms: float
    papr_db: float
    info_bits: int
    coded_bits: int
    encode_time_s: float
    # reference data for benchmarking (not transmitted)
    payload_bits: np.ndarray = field(repr=False)
    coded_bit_stream: np.ndarray = field(repr=False)
    data_symbols: np.ndarray = field(repr=False)
    header_symbols: np.ndarray = field(repr=False)

    @property
    def net_bitrate(self) -> float:
        """Original (uncompressed) payload bits per second of audio."""
        return 8 * self.header.original_length / self.duration_s if self.duration_s else 0.0

    @property
    def transmitted_bitrate(self) -> float:
        """Transmitted payload bits (after compression) per second."""
        return 8 * self.header.payload_length / self.duration_s if self.duration_s else 0.0

    def describe(self) -> dict:
        return {
            "sample_rate": self.sample_rate,
            "n_samples": self.n_samples,
            "duration_s": self.duration_s,
            "peak": self.peak,
            "rms": self.rms,
            "papr_db": self.papr_db,
            "info_bits": self.info_bits,
            "coded_bits": self.coded_bits,
            "encode_time_s": self.encode_time_s,
            "net_bitrate_bps": self.net_bitrate,
            "transmitted_bitrate_bps": self.transmitted_bitrate,
            "compression": {
                "algorithm": self.compression.algorithm,
                "original_size": self.compression.original_size,
                "compressed_size": len(self.compression.data),
                "ratio": self.compression.ratio,
                "candidates": self.compression.candidates,
            },
            "header": self.header.describe(),
            "config": self.config.describe(),
            "sections": self.layout.sections(),
            "n_header_symbols": self.layout.n_header_symbols,
            "n_payload_symbols": self.layout.n_payload_symbols,
        }


def _section_bits(coded: np.ndarray, cfg: OFDMConfig, rng: np.random.Generator, repeats: int = 1):
    bits = pad_bits(coded, cfg.bits_per_ofdm_symbol, rng)
    syms = bits_to_data_symbols(cfg, scramble(bits))
    if repeats > 1:
        syms = np.tile(syms, (repeats, 1))
    rows = build_symbols(cfg, syms)
    rows = np.concatenate([training_rows(cfg), rows], axis=0)
    return bits, syms, carriers_to_time(cfg, rows, cfg.active_carriers).reshape(-1)


def encode_packets(payload: bytes, cfg: OFDMConfig) -> tuple[np.ndarray, np.ndarray]:
    """Return (info bits, coded+interleaved bit stream) for all packets."""
    info_parts, coded_parts = [], []
    for pkt in split_packets(payload, cfg.packet_size):
        bits = bytes_to_bits(pkt)
        info_parts.append(bits)
        coded_parts.append(interleave(convolutional.encode(bits, cfg.code_rate)))
    return np.concatenate(info_parts), np.concatenate(coded_parts)


def encode(
    data: bytes,
    config: Optional[OFDMConfig] = None,
    compression: str = "auto",
    payload_type: PayloadType | str = PayloadType.BINARY,
    filename: str = "",
    amplitude: float = DEFAULT_AMPLITUDE,
    seed: int = 0,
    max_input_bytes: int = MAX_INPUT_BYTES,
) -> tuple[np.ndarray, TransmissionInfo]:
    """Encode ``data`` into a float64 mono waveform in ``[-amplitude, amplitude]``.

    Returns ``(samples, info)``. ``info`` carries everything needed to
    benchmark the decode (reference bits, layout, timings).
    """
    t0 = time.perf_counter()
    cfg = config or OFDMConfig()
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise EncodeError("data must be bytes")
    data = bytes(data)
    if len(data) > max_input_bytes:
        raise EncodeError(f"input exceeds limit of {max_input_bytes} bytes")
    if not 0 < amplitude <= 1.0:
        raise EncodeError("amplitude must be in (0, 1]")
    if isinstance(payload_type, str):
        payload_type = PayloadType[payload_type.upper()]

    language = detect_language(data, filename) if compression in ("auto", "codeaware") else None
    choice = choose_compression(data, compression, language=language)
    payload = choice.data

    header = TransmissionHeader(
        original_length=len(data),
        payload_length=len(payload),
        packet_size=cfg.packet_size,
        n_packets=max(1, (len(payload) + cfg.packet_size - 1) // cfg.packet_size),
        sha256=sha256(data),
        config=cfg,
        payload_type=payload_type,
        compression=choice.algorithm,
        filename=filename,
    )
    header_bytes = header.pack()

    fs = cfg.sample_rate
    hcfg = header_config(fs)
    rng = np.random.default_rng(seed)

    # --- header section (fixed robust config)
    h_coded = interleave(convolutional.encode(bytes_to_bits(header_bytes), "1/2"))
    _, h_syms, h_wave = _section_bits(h_coded, hcfg, rng, repeats=HEADER_REPEATS)

    # --- payload section
    info_bits, coded = encode_packets(payload, cfg)
    p_bits, p_syms, p_wave = _section_bits(coded, cfg, rng)

    layout = frame_layout(len(payload), cfg)
    # Scale the chirp to the same RMS power as the OFDM sections so the
    # preamble neither dominates the peak normalisation below (a unit chirp
    # would leave the ~12 dB PAPR data sections 10 dB under full scale) nor
    # skews the average-power accounting used for SNR.
    ofdm = np.concatenate([h_wave, p_wave])
    ofdm_rms = max(float(np.sqrt(np.mean(ofdm**2))), 1e-12)
    chirp = preamble_chirp(fs) * (ofdm_rms * np.sqrt(2.0))
    guard = np.zeros(preamble_guard_samples(fs))
    tail = np.zeros(layout.total_samples - layout.payload_end)
    wave = np.concatenate([chirp, guard, h_wave, p_wave, tail])
    assert wave.size == layout.total_samples, (wave.size, layout.total_samples)

    # Normalise once, globally. A global scale factor does not affect
    # decoding because the receiver estimates the channel gain.
    peak = float(np.max(np.abs(wave)))
    if peak > 0:
        wave = wave * (amplitude / peak)
    info = TransmissionInfo(
        sample_rate=fs,
        config=cfg,
        header=header,
        layout=layout,
        compression=choice,
        n_samples=wave.size,
        duration_s=wave.size / fs,
        peak=float(np.max(np.abs(wave))),
        rms=float(np.sqrt(np.mean(wave**2))),
        papr_db=papr_db(wave),
        info_bits=int(info_bits.size),
        coded_bits=int(coded.size),
        encode_time_s=time.perf_counter() - t0,
        payload_bits=info_bits,
        coded_bit_stream=p_bits,
        data_symbols=p_syms,
        header_symbols=h_syms,
    )
    return wave, info


def estimate(config: OFDMConfig, n_bytes: int) -> dict:
    """Duration/throughput estimate for ``n_bytes`` of (post-compression) payload."""
    layout = frame_layout(n_bytes, config)
    duration = layout.total_samples / config.sample_rate
    return {
        "payload_bytes": n_bytes,
        "duration_s": duration,
        "n_samples": layout.total_samples,
        "n_header_symbols": layout.n_header_symbols,
        "n_payload_symbols": layout.n_payload_symbols,
        "net_bitrate_bps": 8 * n_bytes / duration if duration else 0.0,
        "info_bitrate_bps": config.info_bitrate,
        "raw_bitrate_bps": config.raw_bitrate,
        "spectral_efficiency": config.spectral_efficiency,
    }
