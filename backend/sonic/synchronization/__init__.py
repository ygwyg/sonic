"""Timing synchronisation, channel estimation and tracking."""

from sonic.synchronization.sync import SyncCandidate, detect_preambles, DEFAULT_THRESHOLD
from sonic.synchronization.equalizer import (
    SectionError,
    SectionResult,
    demodulate_section,
    estimate_channel,
    group_delay_samples,
)

__all__ = [
    "SyncCandidate",
    "detect_preambles",
    "DEFAULT_THRESHOLD",
    "SectionError",
    "SectionResult",
    "demodulate_section",
    "estimate_channel",
    "group_delay_samples",
]
