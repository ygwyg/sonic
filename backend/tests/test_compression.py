import lzma
import os
import zlib

import pytest

from sonic.compression import (
    DecompressionError,
    available_algorithms,
    choose_compression,
    compress,
    decompress,
    detect_language,
)


@pytest.mark.parametrize("algo", available_algorithms())
def test_roundtrip_all_algorithms(algo, python_source):
    out = compress(python_source, algo)
    assert decompress(out, algo) == python_source


@pytest.mark.parametrize("algo", available_algorithms())
def test_roundtrip_edge_inputs(algo):
    for data in (b"", b"a", os.urandom(1000), "ünïcödé ✓ 日本語".encode()):
        assert decompress(compress(data, algo), algo) == data


def test_auto_bypasses_incompressible():
    data = os.urandom(4000)
    ch = choose_compression(data, "auto")
    assert ch.algorithm == "none" and ch.data == data
    ch = choose_compression(lzma.compress(b"hello " * 1000), "zlib")
    assert ch.algorithm == "none"


def test_auto_picks_smallest(python_source):
    ch = choose_compression(python_source, "auto")
    assert ch.algorithm != "none"
    assert len(ch.data) == min(ch.candidates.values())


def test_codeaware_beats_or_matches_generic_on_small_python():
    src = (
        "import os\nimport sys\n\ndef main(argv=None):\n    parser = argparse.ArgumentParser()\n"
        "    args = parser.parse_args(argv)\n    return 0\n\nif __name__ == '__main__':\n    sys.exit(main())\n"
    ).encode()
    ca = len(compress(src, "codeaware", language="python"))
    z = len(compress(src, "zlib"))
    assert ca < z


def test_decompression_bomb_limit():
    bomb = zlib.compress(b"\0" * 5_000_000, 9)
    with pytest.raises(DecompressionError):
        decompress(bomb, "zlib", max_output=1_000_000)
    bomb = lzma.compress(b"\0" * 5_000_000)
    with pytest.raises(DecompressionError):
        decompress(bomb, "lzma", max_output=1_000_000)


def test_corrupted_streams_raise():
    for algo in available_algorithms():
        if algo == "none":
            continue
        with pytest.raises(DecompressionError):
            decompress(b"\xff\x00garbage", algo)


def test_language_detection(python_source):
    assert detect_language(python_source, "x.py") == "python"
    assert detect_language(python_source) == "python"
    assert detect_language(b'{"a": 1, "b": [1,2]}') == "json"
    assert detect_language(b"const x = () => 1;\nfunction f() { return require('x'); }\n") == "javascript"
    assert detect_language(os.urandom(100)) == "generic"
