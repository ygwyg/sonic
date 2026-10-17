"""Lossless compression codecs with decompression-bomb protection.

Supported algorithms: ``none``, ``zlib``, ``lzma``, ``zstd`` (if the
``zstandard`` package is installed) and ``codeaware`` (see
:mod:`sonic.compression.codeaware`). ``auto`` tries the candidates and
keeps the smallest result, falling back to ``none`` when compression would
grow the payload (e.g. already-compressed input).
"""

from __future__ import annotations

import lzma
import zlib
from dataclasses import dataclass
from typing import Iterable, Optional

try:  # optional dependency
    import zstandard as _zstd
except Exception:  # pragma: no cover - depends on environment
    _zstd = None

DEFAULT_MAX_OUTPUT = 64 * 1024 * 1024  # 64 MiB


class DecompressionError(ValueError):
    """Raised when decompression fails or would exceed the size limit."""


def available_algorithms() -> list[str]:
    algos = ["none", "zlib", "lzma", "codeaware"]
    if _zstd is not None:
        algos.insert(3, "zstd")
    return algos


def zstd_available() -> bool:
    return _zstd is not None


def compress(data: bytes, algorithm: str, language: Optional[str] = None) -> bytes:
    if algorithm == "none":
        return bytes(data)
    if algorithm == "zlib":
        return zlib.compress(data, 9)
    if algorithm == "lzma":
        return lzma.compress(data, preset=9 | lzma.PRESET_EXTREME)
    if algorithm == "zstd":
        if _zstd is None:
            raise ValueError("zstandard is not installed")
        return _zstd.ZstdCompressor(level=19).compress(data)
    if algorithm == "codeaware":
        from sonic.compression.codeaware import compress_codeaware

        return compress_codeaware(data, language=language)
    raise ValueError(f"unknown compression algorithm {algorithm!r}")


def decompress(data: bytes, algorithm: str, max_output: int = DEFAULT_MAX_OUTPUT) -> bytes:
    """Decompress with a hard cap on the output size."""
    try:
        if algorithm == "none":
            if len(data) > max_output:
                raise DecompressionError("payload exceeds size limit")
            return bytes(data)
        if algorithm == "zlib":
            d = zlib.decompressobj()
            out = d.decompress(data, max_output + 1)
            if len(out) > max_output or d.unconsumed_tail:
                raise DecompressionError("zlib output exceeds size limit")
            out += d.flush()
            if not d.eof:
                raise DecompressionError("truncated zlib stream")
            return out
        if algorithm == "lzma":
            d = lzma.LZMADecompressor()
            out = d.decompress(data, max_length=max_output + 1)
            if len(out) > max_output or not d.eof:
                raise DecompressionError("lzma output exceeds size limit or stream truncated")
            return out
        if algorithm == "zstd":
            if _zstd is None:
                raise DecompressionError("zstandard is not installed; cannot decode zstd payload")
            d = _zstd.ZstdDecompressor()
            try:
                return d.decompress(data, max_output_size=max_output)
            except _zstd.ZstdError as e:
                raise DecompressionError(f"zstd: {e}") from e
        if algorithm == "codeaware":
            from sonic.compression.codeaware import decompress_codeaware

            return decompress_codeaware(data, max_output=max_output)
    except DecompressionError:
        raise
    except Exception as e:  # zlib.error, lzma.LZMAError, ValueError...
        raise DecompressionError(f"{algorithm}: {e}") from e
    raise DecompressionError(f"unknown compression algorithm {algorithm!r}")


@dataclass
class CompressionChoice:
    algorithm: str
    data: bytes
    original_size: int
    candidates: dict[str, int]

    @property
    def ratio(self) -> float:
        return self.original_size / max(1, len(self.data))


def choose_compression(
    data: bytes,
    algorithm: str = "auto",
    candidates: Optional[Iterable[str]] = None,
    language: Optional[str] = None,
) -> CompressionChoice:
    """Compress with a given algorithm, or pick the best of several.

    Compression is bypassed (``none``) whenever it would not shrink the
    payload, so already-compressed files are never inflated.
    """
    if algorithm != "auto":
        if algorithm == "none":
            return CompressionChoice("none", bytes(data), len(data), {"none": len(data)})
        out = compress(data, algorithm, language=language)
        sizes = {"none": len(data), algorithm: len(out)}
        if len(out) >= len(data):
            return CompressionChoice("none", bytes(data), len(data), sizes)
        return CompressionChoice(algorithm, out, len(data), sizes)
    cands = list(candidates) if candidates else [a for a in available_algorithms() if a != "none"]
    best_name, best = "none", bytes(data)
    sizes = {"none": len(data)}
    for name in cands:
        try:
            out = compress(data, name, language=language)
        except ValueError:
            continue
        sizes[name] = len(out)
        if len(out) < len(best):
            best_name, best = name, out
    return CompressionChoice(best_name, best, len(data), sizes)
