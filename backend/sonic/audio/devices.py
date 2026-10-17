"""Speaker playback and microphone capture via ``sounddevice``.

Hardware access is optional: every function raises :class:`AudioDeviceError`
with a clear message when no device or the ``sounddevice`` package is not
available. Playback starts at a conservative level (``DEFAULT_PLAY_GAIN``)
and never exceeds ``MAX_PLAY_GAIN``; microphone capture is only started on
an explicit call (the API additionally requires the browser to ask the
user for permission).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

DEFAULT_PLAY_GAIN = 0.5
MAX_PLAY_GAIN = 1.0
MAX_RECORD_SECONDS = 600


class AudioDeviceError(RuntimeError):
    pass


def _sd():
    try:
        import sounddevice as sd  # noqa: WPS433 (optional import)
    except Exception as e:  # pragma: no cover - depends on host
        raise AudioDeviceError(f"sounddevice is not available: {e}") from e
    return sd


def list_devices() -> list[dict]:
    sd = _sd()
    try:
        devs = sd.query_devices()
    except Exception as e:  # pragma: no cover
        raise AudioDeviceError(f"cannot query audio devices: {e}") from e
    out = []
    for i, d in enumerate(devs):
        out.append(
            {
                "index": i,
                "name": d.get("name"),
                "max_input_channels": d.get("max_input_channels"),
                "max_output_channels": d.get("max_output_channels"),
                "default_samplerate": d.get("default_samplerate"),
            }
        )
    return out


def play(samples: np.ndarray, sample_rate: int, gain: float = DEFAULT_PLAY_GAIN, device: Optional[int] = None) -> None:
    """Blocking playback at a conservative gain (clipped to ``MAX_PLAY_GAIN``)."""
    sd = _sd()
    g = float(np.clip(gain, 0.0, MAX_PLAY_GAIN))
    x = np.clip(np.asarray(samples, dtype=np.float32) * g, -1.0, 1.0)
    try:
        sd.play(x, samplerate=sample_rate, device=device, blocking=True)
    except Exception as e:  # pragma: no cover
        raise AudioDeviceError(f"playback failed: {e}") from e


def record(seconds: float, sample_rate: int = 48000, device: Optional[int] = None) -> np.ndarray:
    """Blocking mono capture. Requires an explicit call (user intent)."""
    sd = _sd()
    if not 0 < seconds <= MAX_RECORD_SECONDS:
        raise AudioDeviceError(f"recording length must be in (0, {MAX_RECORD_SECONDS}] s")
    n = int(seconds * sample_rate)
    try:
        x = sd.rec(n, samplerate=sample_rate, channels=1, dtype="float32", device=device, blocking=True)
    except Exception as e:  # pragma: no cover
        raise AudioDeviceError(f"recording failed: {e}") from e
    return np.asarray(x, dtype=np.float64).reshape(-1)
