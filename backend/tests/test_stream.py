"""Continuous listening: chunked audio in, transmissions out."""

import numpy as np
import pytest

from sonic.config import PRESETS
from sonic.receiver.stream import ListenSession
from sonic.transmitter import encode


def _stream(x: np.ndarray, fs: int, chunk_s: float = 0.25) -> list[dict]:
    s = ListenSession(fs)
    n = int(chunk_s * fs)
    events = []
    for i in range(0, x.size, n):
        s.feed(x[i : i + n])
        events.append(s.poll())
    for _ in range(3):  # drain
        events.append(s.poll())
    return events


def _noise(fs: int, seconds: float, rng, level=0.003) -> np.ndarray:
    return rng.normal(0, level, int(seconds * fs))


def test_receives_two_back_to_back_transmissions():
    rng = np.random.default_rng(1)
    cfg = PRESETS["default"]
    fs = cfg.sample_rate
    a, _ = encode(b"first message", cfg)
    b, _ = encode(b"second message, a little longer" * 4, cfg)
    x = np.concatenate([_noise(fs, 1.3, rng), a, _noise(fs, 0.7, rng), b, _noise(fs, 1.0, rng)])
    x[: x.size] += _noise(fs, x.size / fs, rng)
    events = _stream(x, fs)
    got = [e for e in events if e["type"] == "received"]
    assert [e["result"].data for e in got] == [b"first message", b"second message, a little longer" * 4]
    assert any(e["type"] == "receiving" and e.get("progress") for e in events)
    assert got[0]["summary"]["airtime_s"] > 0
    fig = got[0]["figures"]
    assert len(fig["snr_db"]) == len(fig["snr_frequencies_hz"])
    assert len(fig["channel_db"]) == len(fig["channel_hz"])
    assert fig["drift_samples"]


def test_noise_only_stays_listening_and_buffer_stays_small():
    rng = np.random.default_rng(2)
    fs = 48000
    s = ListenSession(fs)
    for _ in range(40):
        s.feed(_noise(fs, 0.25, rng, level=0.05))
        assert s.poll()["type"] == "listening"
    assert s._buf.size <= 2 * int(0.1 * fs) + 1


def test_listen_websocket_end_to_end():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from sonic.api.app import app

    cfg = PRESETS["default"]
    fs = cfg.sample_rate
    wave, _ = encode("héllo over the air".encode(), cfg)
    x = np.concatenate([np.zeros(fs // 2), wave, np.zeros(fs)])
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with TestClient(app).websocket_connect("/api/listen") as ws:
        ws.send_text('{"sample_rate": %d}' % fs)
        assert ws.receive_json()["type"] == "listening"
        n = fs // 10
        for i in range(0, pcm.size, n):
            ws.send_bytes(pcm[i : i + n].tobytes())
        for _ in range(40):  # keep the stream alive with silence until the result arrives
            ws.send_bytes(np.zeros(n, dtype="<i2").tobytes())
        events = []
        while True:
            e = ws.receive_json()
            events.append(e)
            if e["type"] in ("received", "failed", "error"):
                break
    assert e["type"] == "received", e
    assert e["text"] == "héllo over the air"
