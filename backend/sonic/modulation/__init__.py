"""Digital modulation: Gray-coded BPSK/QPSK/M-QAM mapping and soft demapping."""

from sonic.modulation.qam import (
    Constellation,
    get_constellation,
    modulate,
    demodulate_hard,
    demodulate_soft,
)

__all__ = ["Constellation", "get_constellation", "modulate", "demodulate_hard", "demodulate_soft"]
