"""WAV file I/O with validation. Uploaded files are untrusted input."""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
import soundfile as sf

MAX_WAV_BYTES = 256 * 1024 * 1024
MAX_WAV_SECONDS = 20 * 60


class WavError(ValueError):
    pass


@dataclass
class AudioClip:
    samples: np.ndarray  # float64 mono in [-1, 1]
    sample_rate: int
    channels: int
    duration_s: float


def write_wav(path_or_buffer, samples: np.ndarray, sample_rate: int, subtype: str = "PCM_16") -> None:
    """Write mono PCM WAV. Samples are clipped to [-1, 1] (never silently scaled)."""
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim != 1:
        raise WavError("only mono output is supported")
    if np.max(np.abs(x), initial=0.0) > 1.0:
        x = np.clip(x, -1.0, 1.0)
    sf.write(path_or_buffer, x, sample_rate, subtype=subtype, format="WAV")


def wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    write_wav(buf, samples, sample_rate)
    return buf.getvalue()


def read_wav(path_or_buffer, max_bytes: int = MAX_WAV_BYTES, max_seconds: float = MAX_WAV_SECONDS) -> AudioClip:
    """Read any soundfile-supported file as mono float64."""
    if isinstance(path_or_buffer, (bytes, bytearray)):
        if len(path_or_buffer) > max_bytes:
            raise WavError("audio file exceeds size limit")
        path_or_buffer = io.BytesIO(path_or_buffer)
    try:
        with sf.SoundFile(path_or_buffer) as f:
            sr = int(f.samplerate)
            ch = int(f.channels)
            frames = int(f.frames)
            if sr <= 0 or ch <= 0:
                raise WavError("invalid audio header")
            if frames / sr > max_seconds:
                raise WavError(f"audio longer than {max_seconds:.0f} s limit")
            data = f.read(dtype="float64", always_2d=True)
    except WavError:
        raise
    except Exception as e:  # soundfile.LibsndfileError, RuntimeError...
        raise WavError(f"cannot read audio: {e}") from e
    mono = data.mean(axis=1) if ch > 1 else data[:, 0]
    if not np.all(np.isfinite(mono)):
        raise WavError("audio contains non-finite samples")
    return AudioClip(samples=mono, sample_rate=sr, channels=ch, duration_s=len(mono) / sr)
