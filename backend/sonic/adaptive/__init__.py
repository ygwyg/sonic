"""Adaptive modulation: channel feedback and deterministic bit loading."""

from sonic.adaptive.bitloading import (
    DEFAULT_THRESHOLDS,
    BitLoadingPlan,
    ChannelStateReport,
    apply_plan,
    band_effective_snr,
    best_fixed_config,
    map_snr_to_config,
    plan_bit_loading,
)

__all__ = [
    "DEFAULT_THRESHOLDS",
    "BitLoadingPlan",
    "ChannelStateReport",
    "apply_plan",
    "band_effective_snr",
    "best_fixed_config",
    "map_snr_to_config",
    "plan_bit_loading",
]
