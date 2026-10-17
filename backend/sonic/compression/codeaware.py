"""Experimental source-code-aware compression (strictly lossless).

Idea
----
General-purpose compressors start with an empty model and must "learn"
that ``return``, ``function``, ``self.``, ``import`` ... are frequent by
seeing them in the input. For small source files that learning cost is a
large fraction of the output. Sonic ships small *static* per-language
dictionaries (bundled text corpora of keywords, idioms and common library
names). Both transmitter and receiver have the same dictionary, so nothing
extra is transmitted; the compressor simply starts with a primed model.

Format
------
``b"CA" | version(1) | backend(1) | language(1) | corpus_crc32(4) | stream``

* backend 1 = zstandard with a content dictionary, 2 = zlib with ``zdict``.
* The corpus CRC lets the receiver refuse data compressed against a
  different dictionary version instead of silently producing garbage.

This is a *content-aware prior*, not a syntax transform: comments,
whitespace and formatting are preserved byte for byte because the stream
is an ordinary zstd/zlib stream. The measured gain is reported honestly
by the benchmark suite (it is modest, and largest for small files).
"""

from __future__ import annotations

import re
import zlib
from functools import lru_cache
from importlib import resources
from typing import Optional

try:
    import zstandard as _zstd
except Exception:  # pragma: no cover
    _zstd = None

from sonic.fec.crc import crc32

FORMAT_MAGIC = b"CA"
FORMAT_VERSION = 1
BACKEND_ZSTD = 1
BACKEND_ZLIB = 2

LANGUAGES: dict[str, int] = {
    "generic": 0,
    "python": 1,
    "javascript": 2,
    "typescript": 3,
    "go": 4,
    "rust": 5,
    "c": 6,
    "cpp": 7,
    "json": 8,
}
_ID_TO_LANGUAGE = {v: k for k, v in LANGUAGES.items()}

EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".json": "json",
}


def detect_language(data: bytes, filename: Optional[str] = None) -> str:
    """Guess the source language from the file name, then from content."""
    if filename:
        lower = filename.lower()
        for ext, lang in EXTENSIONS.items():
            if lower.endswith(ext):
                return lang
    head = data[:4096].decode("utf-8", "ignore")
    stripped = head.lstrip()
    if stripped.startswith(("{", "[")) and ('"' in stripped[:200]):
        return "json"
    scores = {
        "python": len(re.findall(r"\bdef \w+\(|\bimport \w+|\bself\b|:\n\s+", head)),
        "javascript": len(re.findall(r"\bconst \w+|\bfunction\b|=>|\brequire\(|console\.", head)),
        "typescript": len(re.findall(r"\binterface \w+|: (?:string|number|boolean)\b|\bexport (?:type|interface)\b", head)),
        "go": len(re.findall(r"\bfunc \w+|\bpackage \w+|:=", head)),
        "rust": len(re.findall(r"\bfn \w+|\blet mut\b|\bimpl\b|->", head)),
        "c": len(re.findall(r"#include <|\bprintf\(|\bsizeof\(", head)),
        "cpp": len(re.findall(r"std::|\btemplate\s*<|\bnamespace\b", head)),
    }
    if scores["typescript"] > 0 and scores["javascript"] > 0:
        scores["typescript"] += scores["javascript"]
    lang, score = max(scores.items(), key=lambda kv: kv[1])
    return lang if score >= 2 else "generic"


@lru_cache(maxsize=None)
def corpus(language: str) -> bytes:
    """Static dictionary corpus for a language (bundled with the package)."""
    name = f"{language}.txt"
    pkg = resources.files("sonic.compression").joinpath("dictionaries")
    generic = pkg.joinpath("generic.txt").read_bytes()
    try:
        specific = pkg.joinpath(name).read_bytes()
    except FileNotFoundError:
        specific = b""
    # Most-relevant content goes last: zlib's window and zstd's dictionary
    # both favour recent bytes.
    return generic + b"\n" + specific


def compress_codeaware(data: bytes, language: Optional[str] = None, filename: Optional[str] = None) -> bytes:
    lang = language or detect_language(data, filename)
    if lang not in LANGUAGES:
        lang = "generic"
    corp = corpus(lang)
    header = FORMAT_MAGIC + bytes([FORMAT_VERSION])
    if _zstd is not None:
        cdict = _zstd.ZstdCompressionDict(corp, dict_type=_zstd.DICT_TYPE_RAWCONTENT)
        stream = _zstd.ZstdCompressor(level=19, dict_data=cdict).compress(data)
        backend = BACKEND_ZSTD
    else:
        c = zlib.compressobj(9, zlib.DEFLATED, 15, 9, zlib.Z_DEFAULT_STRATEGY, zdict=corp[-32768:])
        stream = c.compress(data) + c.flush()
        backend = BACKEND_ZLIB
    return header + bytes([backend, LANGUAGES[lang]]) + crc32(corp).to_bytes(4, "big") + stream


def decompress_codeaware(blob: bytes, max_output: int) -> bytes:
    from sonic.compression.codecs import DecompressionError

    if len(blob) < 9 or blob[:2] != FORMAT_MAGIC:
        raise DecompressionError("not a code-aware stream")
    if blob[2] != FORMAT_VERSION:
        raise DecompressionError(f"unsupported code-aware version {blob[2]}")
    backend, lang_id = blob[3], blob[4]
    if lang_id not in _ID_TO_LANGUAGE:
        raise DecompressionError(f"unknown language id {lang_id}")
    corp = corpus(_ID_TO_LANGUAGE[lang_id])
    if int.from_bytes(blob[5:9], "big") != crc32(corp):
        raise DecompressionError("dictionary version mismatch between transmitter and receiver")
    stream = blob[9:]
    if backend == BACKEND_ZSTD:
        if _zstd is None:
            raise DecompressionError("zstandard not installed; cannot decode")
        cdict = _zstd.ZstdCompressionDict(corp, dict_type=_zstd.DICT_TYPE_RAWCONTENT)
        try:
            return _zstd.ZstdDecompressor(dict_data=cdict).decompress(stream, max_output_size=max_output)
        except _zstd.ZstdError as e:
            raise DecompressionError(f"zstd: {e}") from e
    if backend == BACKEND_ZLIB:
        d = zlib.decompressobj(zdict=corp[-32768:])
        out = d.decompress(stream, max_output + 1)
        if len(out) > max_output or d.unconsumed_tail:
            raise DecompressionError("output exceeds size limit")
        out += d.flush()
        if not d.eof:
            raise DecompressionError("truncated stream")
        return out
    raise DecompressionError(f"unknown backend {backend}")
