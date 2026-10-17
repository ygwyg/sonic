"""Audio file and device I/O."""

from sonic.audio.wav import AudioClip, WavError, read_wav, wav_bytes, write_wav
from sonic.audio.devices import (
    DEFAULT_PLAY_GAIN,
    MAX_PLAY_GAIN,
    AudioDeviceError,
    list_devices,
    play,
    record,
)

__all__ = [
    "AudioClip",
    "WavError",
    "read_wav",
    "wav_bytes",
    "write_wav",
    "DEFAULT_PLAY_GAIN",
    "MAX_PLAY_GAIN",
    "AudioDeviceError",
    "list_devices",
    "play",
    "record",
]
