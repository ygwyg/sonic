"""Reproducible benchmark datasets (generated from fixed seeds)."""

from __future__ import annotations

import json
import lzma
import os
from dataclasses import dataclass

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)


@dataclass
class Sample:
    name: str
    kind: str
    filename: str
    data: bytes


def _random_binary(n: int, seed: int) -> bytes:
    return np.random.default_rng(seed).integers(0, 256, n, dtype=np.uint8).tobytes()


def _compressible_text(n: int, seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    words = ["sonic", "waveform", "carrier", "ofdm", "signal", "the", "and", "of", "data", "audio", "frequency", "symbol"]
    out = []
    size = 0
    while size < n:
        line = " ".join(rng.choice(words, size=int(rng.integers(6, 14)))) + ".\n"
        out.append(line)
        size += len(line)
    return "".join(out).encode()[:n]


def _python_source() -> bytes:
    with open(os.path.join(PKG_ROOT, "receiver", "decoder.py"), "rb") as f:
        return f.read()


def _javascript_source() -> bytes:
    src = """// Sonic benchmark sample: a small event emitter and matrix helpers.
'use strict';

class Emitter {
  constructor() { this.handlers = new Map(); }
  on(name, fn) {
    if (!this.handlers.has(name)) this.handlers.set(name, []);
    this.handlers.get(name).push(fn);
    return () => this.off(name, fn);
  }
  off(name, fn) {
    const list = this.handlers.get(name) || [];
    const i = list.indexOf(fn);
    if (i >= 0) list.splice(i, 1);
  }
  emit(name, ...args) {
    for (const fn of this.handlers.get(name) || []) {
      try { fn(...args); } catch (err) { console.error(`handler for ${name} failed`, err); }
    }
  }
}

function matmul(a, b) {
  const n = a.length, m = b[0].length, k = b.length;
  const out = Array.from({ length: n }, () => new Array(m).fill(0));
  for (let i = 0; i < n; i++)
    for (let j = 0; j < m; j++) {
      let s = 0;
      for (let t = 0; t < k; t++) s += a[i][t] * b[t][j];
      out[i][j] = s;
    }
  return out;
}

function transpose(a) { return a[0].map((_, j) => a.map((row) => row[j])); }

async function fetchJson(url, init = {}) {
  const res = await fetch(url, { ...init, headers: { 'Content-Type': 'application/json', ...(init.headers || {}) } });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json();
}

module.exports = { Emitter, matmul, transpose, fetchJson };
"""
    return (src * 3).encode()


def _json_document(seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    records = []
    for i in range(120):
        records.append(
            {
                "id": i,
                "name": f"sensor-{int(rng.integers(100, 999))}",
                "enabled": bool(rng.integers(0, 2)),
                "readings": [round(float(x), 3) for x in rng.normal(20, 3, 8)],
                "tags": ["lab", "ofdm", "audio"][: int(rng.integers(1, 4))],
                "location": {"lat": round(float(rng.uniform(-90, 90)), 5), "lon": round(float(rng.uniform(-180, 180)), 5)},
            }
        )
    return json.dumps({"version": 1, "records": records}, indent=2).encode()


def _already_compressed(seed: int) -> bytes:
    return lzma.compress(_compressible_text(20000, seed))


def standard_datasets(size: int = 4096, seed: int = 1234) -> list[Sample]:
    """The fixed benchmark corpus. ``size`` bounds the synthetic samples."""
    return [
        Sample("random_binary", "binary", "random.bin", _random_binary(size, seed)),
        Sample("compressible_text", "text", "text.txt", _compressible_text(size, seed)),
        Sample("python_source", "code", "decoder.py", _python_source()[: max(size, 2048)]),
        Sample("javascript_source", "code", "emitter.js", _javascript_source()[: max(size, 2048)]),
        Sample("json_document", "json", "records.json", _json_document(seed)[: max(size, 2048)]),
        Sample("compressed_binary", "binary", "text.txt.xz", _already_compressed(seed)[: max(size, 1024)]),
    ]


def source_corpus() -> list[Sample]:
    """Real source files from this repository for the compression study."""
    samples = []
    roots = [
        (os.path.join(PKG_ROOT), ".py", "python"),
    ]
    for root, ext, lang in roots:
        for dirpath, _, files in os.walk(root):
            for fn in sorted(files):
                if fn.endswith(ext) and not fn.startswith("__"):
                    p = os.path.join(dirpath, fn)
                    with open(p, "rb") as f:
                        data = f.read()
                    if 1500 <= len(data) <= 60000:
                        samples.append(Sample(os.path.relpath(p, PKG_ROOT), lang, fn, data))
    samples.append(Sample("emitter.js", "javascript", "emitter.js", _javascript_source()))
    samples.append(Sample("records.json", "json", "records.json", _json_document(1234)))
    return samples
