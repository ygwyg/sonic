"""Continuous listening: feed microphone audio in chunks, get transmissions out.

A :class:`ListenSession` keeps a rolling buffer. While nothing has been
heard it only retains enough audio to catch a chirp that straddles two
chunks. Once a preamble is found the buffer is re-based on it, the header
is decoded as soon as it has fully arrived (which fixes the frame length),
and the full decode runs once the whole frame is buffered. Every
:meth:`ListenSession.poll` returns an event describing the current state.
"""

from __future__ import annotations

import threading
from typing import Optional

import numpy as np

from sonic.config import header_config
from sonic.ofdm.preamble import preamble_chirp, preamble_length
from sonic.protocol import HeaderError
from sonic.protocol.layout import FrameLayout, frame_layout
from sonic.receiver.decoder import DecodeError, DecodeResult, _decode_header, decode, estimated_sro_ppm
from sonic.synchronization import SectionError, detect_preambles

MAX_FRAME_S = 120.0  # refuse to wait for frames longer than this
LEAD_IN_S = 0.05  # audio kept before a detected chirp
REPORT_SCORE = 0.2  # weaker sync hits that fail are dropped silently (likely false alarms)


class ListenSession:
    def __init__(self, sample_rate: int):
        self.sample_rate = int(sample_rate)
        self._hcfg = header_config(self.sample_rate)
        self._chirp_len = len(preamble_chirp(self.sample_rate))
        self._lock = threading.Lock()
        self._pending: list[np.ndarray] = []
        self._buf = np.zeros(0, dtype=np.float64)
        self._pos: Optional[int] = None  # chirp start within _buf
        self._score = 0.0
        self._layout: Optional[FrameLayout] = None
        self._header = None

    def feed(self, samples: np.ndarray) -> None:
        x = np.asarray(samples, dtype=np.float64).reshape(-1)
        if x.size:
            with self._lock:
                self._pending.append(x)

    def _drain(self) -> np.ndarray:
        with self._lock:
            pending, self._pending = self._pending, []
        if pending:
            self._buf = np.concatenate([self._buf, *pending])
        return self._buf

    def _reset(self, keep_from: int) -> None:
        self._buf = self._buf[max(0, keep_from) :]
        self._pos = None
        self._layout = None
        self._header = None
        self._score = 0.0

    def poll(self) -> dict:
        x = self._drain()
        fs = self.sample_rate

        if self._pos is None:
            cands = detect_preambles(x, fs) if x.size >= self._chirp_len else []
            if not cands:
                # keep just enough to catch a chirp split across chunks
                self._buf = x[-(2 * self._chirp_len) :]
                return {"type": "listening"}
            first = min(cands, key=lambda c: c.position)
            lead = int(LEAD_IN_S * fs)
            self._buf = x[max(0, first.position - lead) :]
            self._pos = min(lead, first.position)
            self._score = first.score
            x = self._buf

        pos = self._pos
        if self._layout is None:
            lay0 = frame_layout(0, self._hcfg, preamble_start=pos)
            if x.size < lay0.payload_start + self._hcfg.symbol_len:
                return {"type": "receiving", "progress": None}
            try:
                header, _ = _decode_header(x, lay0.header_start - self._hcfg.cp_len // 4, self._hcfg, lay0.n_header_symbols, {})
            except (HeaderError, DecodeError, SectionError) as e:
                return self._fail(f"header: {e}", pos + self._chirp_len)
            layout = frame_layout(header.payload_length, header.config, preamble_start=pos)
            if (layout.total_samples - pos) / fs > MAX_FRAME_S:
                return self._fail("transmission too long", pos + self._chirp_len)
            self._header, self._layout = header, layout

        lay = self._layout
        total = lay.total_samples - pos
        have = x.size - pos
        if have < total:
            return {
                "type": "receiving",
                "progress": max(0.0, min(1.0, have / total)),
                "remaining_s": (total - have) / fs,
                "header": self._header.describe(),
            }

        end = lay.total_samples
        res = decode(x[:end], fs)
        event = self.result_event(res, lay, pos)
        self._reset(end - preamble_length(fs) // 2)
        if not res.success and self._score < REPORT_SCORE:
            return {"type": "listening"}
        return event

    def _fail(self, error: str, drop_to: int) -> dict:
        score = self._score
        self._reset(drop_to)
        if score < REPORT_SCORE:
            return {"type": "listening"}
        return {"type": "failed", "error": error, "sync_score": score}

    def result_event(self, res: DecodeResult, lay: FrameLayout, pos: int) -> dict:
        d = res.diagnostics
        ps = d.get("payload_section", {})
        cfg = res.header.config if res.header else lay.cfg
        airtime = (lay.total_samples - pos) / self.sample_rate
        summary = {
            "snr_db": ps.get("snr_evm_mean_db"),
            "airtime_s": airtime,
            "net_bitrate_bps": res.header.original_length * 8 / airtime if res.header and airtime > 0 else None,
            "sro_ppm": estimated_sro_ppm(d, cfg.symbol_len),
            "sync_score": self._score,
            "decode_time_s": res.decode_time_s,
            "config": cfg.describe(),
            "packets": d.get("packets"),
        }
        figures = {
            "constellation": ps.get("constellation"),
            "snr_frequencies_hz": (cfg.enabled_data_carriers * cfg.carrier_spacing).round(1).tolist(),
            "snr_db": ps.get("snr_evm_db"),
        }
        return {
            "type": "received" if res.success else "failed",
            "error": res.error,
            "header": res.header.describe() if res.header else None,
            "summary": summary,
            "figures": figures,
            "result": res,
        }
