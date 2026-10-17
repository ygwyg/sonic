import hashlib
import json
import os

from sonic.cli import main


def test_cli_encode_decode_analyze(tmp_path, python_source):
    src = tmp_path / "prog.py"
    src.write_bytes(python_source)
    wav = tmp_path / "signal.wav"
    out = tmp_path / "recovered.py"
    assert main(["encode", str(src), "--output", str(wav), "--json", str(tmp_path / "enc.json")]) == 0
    assert wav.exists() and (tmp_path / "enc.json").exists()
    assert main(["decode", str(wav), "--output", str(out), "--json", str(tmp_path / "dec.json")]) == 0
    assert out.read_bytes() == python_source
    assert hashlib.sha256(out.read_bytes()).hexdigest() == hashlib.sha256(python_source).hexdigest()
    d = json.loads((tmp_path / "dec.json").read_text())
    assert d["success"] and d["diagnostics"]["sha256"]["match"]
    assert main(["analyze", str(wav), "--json", str(tmp_path / "an.json")]) == 0
    an = json.loads((tmp_path / "an.json").read_text())
    assert "spectrum" in an and "spectrogram" in an


def test_cli_decode_failure_exit_code(tmp_path):
    from sonic.audio import write_wav
    import numpy as np

    wav = tmp_path / "noise.wav"
    write_wav(str(wav), np.random.default_rng(0).normal(0, 0.1, 48000), 48000)
    assert main(["decode", str(wav), "--output", str(tmp_path / "x")]) == 2
    assert not (tmp_path / "x").exists()


def test_cli_audio_qr(tmp_path, capsys):
    wav = tmp_path / "qr.wav"
    assert main(["qr", "encode", "--text", "https://example.com/?q=sonic ✓", "--output", str(wav)]) == 0
    assert main(["qr", "decode", "--input", str(wav)]) == 0
    assert "https://example.com/?q=sonic ✓" in capsys.readouterr().out


def test_cli_preset_overrides(tmp_path):
    src = tmp_path / "a.bin"
    src.write_bytes(os.urandom(300))
    wav = tmp_path / "a.wav"
    assert main(["encode", str(src), "-o", str(wav), "--preset", "fast", "--modulation", "qpsk", "--n-fft", "1024", "--cp-len", "128"]) == 0
    out = tmp_path / "a.out"
    assert main(["decode", str(wav), "-o", str(out)]) == 0
    assert out.read_bytes() == src.read_bytes()
