"""Sonic: high-density OFDM acoustic data transmission engine.

The public Python API is intentionally small:

>>> from sonic import encode, decode, OFDMConfig
>>> wave, info = encode(b"hello", OFDMConfig())
>>> result = decode(wave, sample_rate=info.sample_rate)
>>> assert result.data == b"hello"
"""

from sonic.config import OFDMConfig, PRESETS, header_config

__version__ = "0.1.0"

__all__ = [
    "OFDMConfig",
    "PRESETS",
    "header_config",
    "encode",
    "decode",
    "TransmissionInfo",
    "DecodeResult",
    "__version__",
]


def __getattr__(name: str):
    # Lazy imports keep `import sonic` cheap and avoid import cycles.
    if name in ("encode", "TransmissionInfo"):
        from sonic import transmitter

        return getattr(transmitter, name)
    if name in ("decode", "DecodeResult"):
        from sonic import receiver

        return getattr(receiver, name)
    raise AttributeError(name)
