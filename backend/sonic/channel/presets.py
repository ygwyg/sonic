"""Named synthetic channel environments.

These are *synthetic* models chosen to span a plausible range of
difficulty. They are not measurements of real rooms.
"""

from __future__ import annotations

from sonic.channel.simulator import ChannelConfig

CHANNEL_PRESETS: dict[str, ChannelConfig] = {
    "ideal": ChannelConfig(name="ideal"),
    "awgn": ChannelConfig(name="awgn", snr_db=20.0),
    "quiet_room": ChannelConfig(
        name="quiet_room",
        snr_db=30.0,
        multipath=[(0.0021, 0.25), (0.0048, 0.12)],
        reverb_rt60_s=0.25,
        reverb_level=0.08,
        tilt_db_per_khz=-0.6,
        sample_rate_ppm=20.0,
        timing_offset_s=0.3,
    ),
    "noisy_room": ChannelConfig(
        name="noisy_room",
        snr_db=12.0,
        multipath=[(0.0018, 0.3), (0.0041, 0.18)],
        reverb_rt60_s=0.3,
        reverb_level=0.1,
        tilt_db_per_khz=-1.0,
        tones=[(3100.0, 0.15)],
        burst_level_db=-3.0,
        burst_duty=0.05,
        sample_rate_ppm=-35.0,
        timing_offset_s=0.5,
    ),
    "reverberant_room": ChannelConfig(
        name="reverberant_room",
        snr_db=22.0,
        multipath=[(0.0015, 0.5), (0.0036, 0.35), (0.0072, 0.2), (0.011, 0.1)],
        reverb_rt60_s=0.6,
        reverb_level=0.15,
        tilt_db_per_khz=-0.8,
        sample_rate_ppm=15.0,
        timing_offset_s=0.2,
    ),
    "difficult": ChannelConfig(
        name="difficult",
        snr_db=8.0,
        multipath=[(0.0012, 0.5), (0.0033, 0.4), (0.0065, 0.3)],
        reverb_rt60_s=0.5,
        reverb_level=0.15,
        tilt_db_per_khz=-1.5,
        notches=[(2600.0, 12.0, 150.0), (5200.0, 10.0, 200.0)],
        lowpass_hz=11000.0,
        highpass_hz=150.0,
        tones=[(4400.0, 0.2), (1900.0, 0.1)],
        burst_level_db=0.0,
        burst_duty=0.08,
        sample_rate_ppm=60.0,
        frequency_offset_hz=0.5,
        timing_offset_s=0.7,
        clip_level=0.9,
    ),
}


def get_channel(name: str, **overrides) -> ChannelConfig:
    if name not in CHANNEL_PRESETS:
        raise KeyError(f"unknown channel preset {name!r}; choose from {sorted(CHANNEL_PRESETS)}")
    base = CHANNEL_PRESETS[name].describe()
    base.update({k: v for k, v in overrides.items() if v is not None})
    return ChannelConfig.from_dict(base)
