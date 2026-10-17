"""OFDM configuration objects, carrier allocation and named presets.

A :class:`OFDMConfig` fully describes how payload symbols are placed on
frequency carriers. The receiver learns the payload configuration from the
transmission header, which is itself always sent using the fixed
:func:`header_config` so that there is no circular dependency between
"what are the parameters" and "how do I read the parameters".
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Optional, Sequence

import numpy as np

# Modulation identifiers ----------------------------------------------------

MODULATIONS: tuple[str, ...] = ("bpsk", "qpsk", "16qam", "64qam", "256qam")
BITS_PER_SYMBOL: dict[str, int] = {
    "bpsk": 1,
    "qpsk": 2,
    "16qam": 4,
    "64qam": 6,
    "256qam": 8,
}
# Code used in headers; 0 means "carrier band disabled".
MODULATION_CODES: dict[str, int] = {m: i + 1 for i, m in enumerate(MODULATIONS)}
CODE_TO_MODULATION: dict[int, Optional[str]] = {0: None, **{v: k for k, v in MODULATION_CODES.items()}}

CODE_RATES: tuple[str, ...] = ("1/2", "2/3", "3/4")
CODE_RATE_VALUES: dict[str, float] = {"1/2": 0.5, "2/3": 2 / 3, "3/4": 0.75}
CODE_RATE_CODES: dict[str, int] = {r: i + 1 for i, r in enumerate(CODE_RATES)}
CODE_TO_RATE: dict[int, str] = {v: k for k, v in CODE_RATE_CODES.items()}

MAX_BANDS = 16
MIN_SAMPLE_RATE = 16000


@dataclass(frozen=True)
class OFDMConfig:
    """Physical-layer configuration for one OFDM transmission.

    Parameters
    ----------
    sample_rate:
        Audio sample rate in Hz. 48 kHz is the primary target.
    n_fft:
        FFT size. Carrier spacing is ``sample_rate / n_fft``.
    cp_len:
        Cyclic prefix length in samples. Must be shorter than the channel
        impulse response you want to tolerate... but it costs
        ``cp_len / (n_fft + cp_len)`` of the raw throughput.
    f_low, f_high:
        Frequency band (Hz) in which carriers are placed. Carriers at DC
        and at Nyquist are never used.
    pilot_spacing:
        Every ``pilot_spacing``-th active carrier carries a known pilot.
    modulation:
        Default modulation for all data carriers.
    code_rate:
        Convolutional code rate (``"1/2"``, ``"2/3"`` or ``"3/4"``).
    band_modulations:
        Optional per-band modulation list for adaptive bit loading. Data
        carriers are split into ``len(band_modulations)`` contiguous bands;
        ``None`` disables a band. When empty, ``modulation`` is used for all
        carriers.
    n_training:
        Number of identical known training symbols preceding the data.
    packet_size:
        Payload bytes per packet (before CRC and index are added).
    """

    sample_rate: int = 48000
    n_fft: int = 2048
    cp_len: int = 512
    f_low: float = 2000.0
    f_high: float = 10000.0
    pilot_spacing: int = 8
    modulation: str = "qpsk"
    code_rate: str = "1/2"
    band_modulations: tuple[Optional[str], ...] = field(default_factory=tuple)
    n_training: int = 2
    packet_size: int = 256

    # ------------------------------------------------------------ validation
    def __post_init__(self) -> None:
        if self.sample_rate < MIN_SAMPLE_RATE:
            raise ValueError(f"sample_rate must be >= {MIN_SAMPLE_RATE} Hz")
        if self.n_fft < 16 or self.n_fft % 2:
            raise ValueError("n_fft must be an even integer >= 16")
        if not 0 <= self.cp_len < self.n_fft:
            raise ValueError("cp_len must satisfy 0 <= cp_len < n_fft")
        if not 0 < self.f_low < self.f_high <= self.sample_rate / 2:
            raise ValueError("require 0 < f_low < f_high <= Nyquist")
        if self.pilot_spacing < 2:
            raise ValueError("pilot_spacing must be >= 2")
        if self.modulation not in MODULATIONS:
            raise ValueError(f"unknown modulation {self.modulation!r}")
        if self.code_rate not in CODE_RATES:
            raise ValueError(f"unknown code_rate {self.code_rate!r}")
        if len(self.band_modulations) > MAX_BANDS:
            raise ValueError(f"at most {MAX_BANDS} bands are supported")
        for m in self.band_modulations:
            if m is not None and m not in MODULATIONS:
                raise ValueError(f"unknown band modulation {m!r}")
        if not 1 <= self.n_training <= 8:
            raise ValueError("n_training must be in 1..8")
        if not 1 <= self.packet_size <= 4096:
            raise ValueError("packet_size must be in 1..4096")
        if len(self.active_carriers) < 2 * self.pilot_spacing:
            raise ValueError(
                "band too narrow for this FFT size: "
                f"{len(self.active_carriers)} carriers, need >= {2 * self.pilot_spacing}"
            )
        if self.band_modulations and all(m is None for m in self.band_modulations):
            raise ValueError("all carrier bands are disabled")

    # ------------------------------------------------------------- geometry
    @cached_property
    def carrier_spacing(self) -> float:
        return self.sample_rate / self.n_fft

    @cached_property
    def symbol_len(self) -> int:
        """Samples per OFDM symbol including cyclic prefix."""
        return self.n_fft + self.cp_len

    @cached_property
    def symbol_duration(self) -> float:
        return self.symbol_len / self.sample_rate

    @cached_property
    def active_carriers(self) -> np.ndarray:
        """FFT bin indices used for pilots and data (DC/Nyquist excluded)."""
        k_lo = int(np.ceil(self.f_low / self.carrier_spacing))
        k_hi = int(np.floor(self.f_high / self.carrier_spacing))
        k_lo = max(k_lo, 1)
        k_hi = min(k_hi, self.n_fft // 2 - 1)
        return np.arange(k_lo, k_hi + 1, dtype=np.int64)

    @cached_property
    def pilot_carriers(self) -> np.ndarray:
        return self.active_carriers[:: self.pilot_spacing]

    @cached_property
    def data_carriers(self) -> np.ndarray:
        mask = np.ones(len(self.active_carriers), dtype=bool)
        mask[:: self.pilot_spacing] = False
        return self.active_carriers[mask]

    @cached_property
    def n_bands(self) -> int:
        return max(1, len(self.band_modulations))

    @cached_property
    def band_of_data_carrier(self) -> np.ndarray:
        """Band index for each data carrier (contiguous split)."""
        n = len(self.data_carriers)
        return np.minimum((np.arange(n) * self.n_bands) // n, self.n_bands - 1)

    @cached_property
    def data_carrier_modulations(self) -> list[Optional[str]]:
        if not self.band_modulations:
            return [self.modulation] * len(self.data_carriers)
        return [self.band_modulations[b] for b in self.band_of_data_carrier]

    @cached_property
    def enabled_data_carriers(self) -> np.ndarray:
        mods = self.data_carrier_modulations
        return self.data_carriers[[m is not None for m in mods]]

    @cached_property
    def bits_per_data_carrier(self) -> np.ndarray:
        return np.array([0 if m is None else BITS_PER_SYMBOL[m] for m in self.data_carrier_modulations], dtype=np.int64)

    @cached_property
    def bits_per_ofdm_symbol(self) -> int:
        """Coded bits carried by one OFDM symbol."""
        return int(self.bits_per_data_carrier.sum())

    @cached_property
    def occupied_bandwidth(self) -> float:
        """Bandwidth spanned by active carriers in Hz."""
        return len(self.active_carriers) * self.carrier_spacing

    # ---------------------------------------------------------- throughput
    @cached_property
    def raw_bitrate(self) -> float:
        """Coded bits per second on data carriers (no FEC, no framing)."""
        return self.bits_per_ofdm_symbol / self.symbol_duration

    @cached_property
    def info_bitrate(self) -> float:
        """Information bits per second after FEC (no framing overhead)."""
        return self.raw_bitrate * CODE_RATE_VALUES[self.code_rate]

    @cached_property
    def spectral_efficiency(self) -> float:
        """Information bits per second per Hz of occupied bandwidth."""
        return self.info_bitrate / self.occupied_bandwidth

    # -------------------------------------------------------------- helpers
    def with_modulation(self, modulation: str, code_rate: Optional[str] = None) -> "OFDMConfig":
        return replace(self, modulation=modulation, band_modulations=(), code_rate=code_rate or self.code_rate)

    def with_bands(self, band_modulations: Sequence[Optional[str]]) -> "OFDMConfig":
        return replace(self, band_modulations=tuple(band_modulations))

    def describe(self) -> dict:
        return {
            "sample_rate": self.sample_rate,
            "n_fft": self.n_fft,
            "cp_len": self.cp_len,
            "f_low": self.f_low,
            "f_high": self.f_high,
            "pilot_spacing": self.pilot_spacing,
            "modulation": self.modulation,
            "code_rate": self.code_rate,
            "band_modulations": list(self.band_modulations),
            "n_training": self.n_training,
            "packet_size": self.packet_size,
            "carrier_spacing_hz": self.carrier_spacing,
            "n_active_carriers": int(len(self.active_carriers)),
            "n_pilot_carriers": int(len(self.pilot_carriers)),
            "n_data_carriers": int(len(self.data_carriers)),
            "n_enabled_data_carriers": int(len(self.enabled_data_carriers)),
            "bits_per_ofdm_symbol": self.bits_per_ofdm_symbol,
            "symbol_duration_s": self.symbol_duration,
            "occupied_bandwidth_hz": self.occupied_bandwidth,
            "raw_bitrate_bps": self.raw_bitrate,
            "info_bitrate_bps": self.info_bitrate,
            "spectral_efficiency_bps_per_hz": self.spectral_efficiency,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OFDMConfig":
        kwargs = {}
        for k in (
            "sample_rate",
            "n_fft",
            "cp_len",
            "f_low",
            "f_high",
            "pilot_spacing",
            "modulation",
            "code_rate",
            "n_training",
            "packet_size",
        ):
            if k in d and d[k] is not None:
                kwargs[k] = d[k]
        if d.get("band_modulations"):
            kwargs["band_modulations"] = tuple(d["band_modulations"])
        return cls(**kwargs)


# ------------------------------------------------------------ fixed header

def header_config(sample_rate: int = 48000) -> OFDMConfig:
    """The fixed, robust configuration used for the transmission header.

    It only depends on the sample rate (known from the WAV container or the
    recording device). 1--7 kHz, 4096-point FFT (85 ms symbols, so
    reverberation beyond the 21 ms cyclic prefix is a small fraction of the
    symbol energy), BPSK, rate 1/2.
    """
    return OFDMConfig(
        sample_rate=sample_rate,
        n_fft=4096,
        cp_len=1024,
        f_low=1000.0,
        f_high=7000.0,
        pilot_spacing=8,
        modulation="bpsk",
        code_rate="1/2",
        n_training=2,
        packet_size=256,
    )


# Preamble chirp parameters (shared by transmitter and receiver).
PREAMBLE_F0 = 1000.0
PREAMBLE_F1 = 7000.0
PREAMBLE_DURATION = 0.1  # seconds
PREAMBLE_GUARD = 0.02  # seconds of silence after the chirp
TAIL_GUARD = 0.02


# ---------------------------------------------------------------- presets

PRESETS: dict[str, OFDMConfig] = {
    # Balanced default for file transfer through WAV files or a good room.
    "default": OFDMConfig(),
    # Short, very robust bursts for Audio QR mode.
    "audioqr": OFDMConfig(
        n_fft=1024,
        cp_len=256,
        f_low=1000.0,
        f_high=7000.0,
        pilot_spacing=8,
        modulation="qpsk",
        code_rate="1/2",
        packet_size=64,
    ),
    # Maximum robustness for bad acoustic channels.
    "robust": OFDMConfig(
        n_fft=4096,
        cp_len=2048,
        f_low=1500.0,
        f_high=7000.0,
        pilot_spacing=4,
        modulation="bpsk",
        code_rate="1/2",
        packet_size=128,
    ),
    # High throughput for clean digital or near-ideal acoustic channels.
    "fast": OFDMConfig(
        n_fft=2048,
        cp_len=256,
        f_low=1500.0,
        f_high=14000.0,
        pilot_spacing=16,
        modulation="64qam",
        code_rate="3/4",
        packet_size=512,
    ),
    # Experimental near-ultrasonic band (hardware dependent!).
    "ultrasonic": OFDMConfig(
        n_fft=2048,
        cp_len=512,
        f_low=17000.0,
        f_high=21000.0,
        pilot_spacing=8,
        modulation="qpsk",
        code_rate="1/2",
        packet_size=128,
    ),
}
