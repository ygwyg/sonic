"""Lossless compression codecs and the experimental code-aware compressor."""

from sonic.compression.codecs import (
    DEFAULT_MAX_OUTPUT,
    CompressionChoice,
    DecompressionError,
    available_algorithms,
    choose_compression,
    compress,
    decompress,
    zstd_available,
)
from sonic.compression.codeaware import detect_language, LANGUAGES

__all__ = [
    "DEFAULT_MAX_OUTPUT",
    "CompressionChoice",
    "DecompressionError",
    "available_algorithms",
    "choose_compression",
    "compress",
    "decompress",
    "zstd_available",
    "detect_language",
    "LANGUAGES",
]
