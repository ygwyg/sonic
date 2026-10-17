"""FastAPI backend for the Sonic dashboard.

All processing is local. Uploaded audio and files are treated as untrusted:
they are size-limited, parsed with validating readers, and never executed.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sonic import __version__
from sonic.adaptive import apply_plan, best_fixed_config, plan_bit_loading
from sonic.analysis import analyze_waveform
from sonic.audio import WavError, read_wav, wav_bytes
from sonic.benchmarking import (
    experiment_adaptive,
    experiment_carrier_density,
    experiment_channels,
    experiment_compression,
    experiment_file_sizes,
    experiment_snr_sweep,
    measure_channel_state,
    records_to_csv,
    summarize,
)
from sonic.channel import CHANNEL_PRESETS, ChannelConfig, apply_channel, get_channel
from sonic.compression import available_algorithms
from sonic.config import CODE_RATES, MODULATIONS, OFDMConfig, PRESETS, header_config
from sonic.protocol import PayloadType
from sonic.receiver import decode
from sonic.receiver.stream import ListenSession
from sonic.transmitter import EncodeError, encode, estimate

MAX_UPLOAD_BYTES = int(os.environ.get("SONIC_MAX_UPLOAD_BYTES", 64 * 1024 * 1024))
MAX_PAYLOAD_BYTES = int(os.environ.get("SONIC_MAX_PAYLOAD_BYTES", 4 * 1024 * 1024))
RESULTS_DIR = os.environ.get("SONIC_RESULTS_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "..", "benchmarks", "results"))
FRONTEND_DIST = os.environ.get("SONIC_FRONTEND_DIST", os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "dist"))

app = FastAPI(title="Sonic", version=__version__, description="OFDM acoustic data transmission engine")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_executor = ThreadPoolExecutor(max_workers=2)
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


# ----------------------------------------------------------------- models


class ConfigModel(BaseModel):
    preset: Optional[str] = None
    sample_rate: Optional[int] = None
    n_fft: Optional[int] = None
    cp_len: Optional[int] = None
    f_low: Optional[float] = None
    f_high: Optional[float] = None
    pilot_spacing: Optional[int] = None
    modulation: Optional[str] = None
    code_rate: Optional[str] = None
    band_modulations: Optional[list[Optional[str]]] = None
    n_training: Optional[int] = None
    packet_size: Optional[int] = None

    def build(self) -> OFDMConfig:
        base = PRESETS.get(self.preset or "default", PRESETS["default"]).describe()
        for k, v in self.model_dump(exclude={"preset"}).items():
            if v is not None:
                base[k] = v
        if self.band_modulations is None and self.modulation is not None:
            base["band_modulations"] = []
        try:
            return OFDMConfig.from_dict(base)
        except ValueError as e:
            raise HTTPException(400, f"invalid configuration: {e}")


class ChannelModel(BaseModel):
    preset: Optional[str] = None
    snr_db: Optional[float] = None
    multipath: Optional[list[list[float]]] = None
    reverb_rt60_s: Optional[float] = None
    reverb_level: Optional[float] = None
    tilt_db_per_khz: Optional[float] = None
    notches: Optional[list[list[float]]] = None
    lowpass_hz: Optional[float] = None
    highpass_hz: Optional[float] = None
    sample_rate_ppm: Optional[float] = None
    frequency_offset_hz: Optional[float] = None
    timing_offset_s: Optional[float] = None
    tones: Optional[list[list[float]]] = None
    burst_level_db: Optional[float] = None
    burst_duty: Optional[float] = None
    clip_level: Optional[float] = None
    seed: Optional[int] = None

    def build(self) -> ChannelConfig:
        base = CHANNEL_PRESETS.get(self.preset or "ideal", CHANNEL_PRESETS["ideal"]).describe()
        for k, v in self.model_dump(exclude={"preset"}).items():
            if v is not None:
                base[k] = v
        try:
            return ChannelConfig.from_dict(base)
        except (TypeError, ValueError) as e:
            raise HTTPException(400, f"invalid channel: {e}")


class EstimateRequest(BaseModel):
    config: ConfigModel = Field(default_factory=ConfigModel)
    n_bytes: int = Field(ge=0, le=MAX_PAYLOAD_BYTES)


class EncodeJsonRequest(BaseModel):
    text: str = ""
    config: ConfigModel = Field(default_factory=ConfigModel)
    compression: str = "auto"
    payload_type: str = "text"
    amplitude: float = Field(0.8, gt=0, le=1.0)
    channel: Optional[ChannelModel] = None


class QrEncodeRequest(BaseModel):
    text: str = Field(..., max_length=4000)
    amplitude: float = Field(0.6, gt=0, le=1.0)
    payload_type: str = "text"


class BenchmarkRequest(BaseModel):
    experiment: str
    trials: int = Field(2, ge=1, le=10)
    snrs: Optional[list[float]] = None
    modulations: Optional[list[str]] = None
    carrier_counts: Optional[list[int]] = None
    channel: Optional[ChannelModel] = None
    payload_bytes: int = Field(1024, ge=16, le=65536)


class AdaptiveRequest(BaseModel):
    channel: ChannelModel = Field(default_factory=ChannelModel)
    config: ConfigModel = Field(default_factory=ConfigModel)
    n_bands: int = Field(8, ge=1, le=16)
    margin_db: float = Field(1.0, ge=0, le=10)
    payload_bytes: int = Field(2048, ge=16, le=65536)


# ---------------------------------------------------------------- helpers


async def _read_upload(f: UploadFile, limit: int) -> bytes:
    data = await f.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"upload exceeds {limit} bytes")
    return data


def _clip_from_upload(data: bytes):
    try:
        return read_wav(data)
    except WavError as e:
        raise HTTPException(400, f"invalid audio file: {e}")


def _wav_b64(samples: np.ndarray, fs: int) -> str:
    return base64.b64encode(wav_bytes(samples, fs)).decode("ascii")


def _decode_payload(res) -> dict:
    out = res.describe()
    if res.success and res.data is not None:
        out["data_base64"] = base64.b64encode(res.data).decode("ascii")
        try:
            out["text"] = res.data.decode("utf-8")
        except UnicodeDecodeError:
            out["text"] = None
    return out


def _run_encode(data: bytes, cfg: OFDMConfig, compression: str, payload_type: str, amplitude: float, filename: str, channel: Optional[ChannelConfig]):
    try:
        wave, info = encode(data, cfg, compression=compression, payload_type=payload_type, filename=filename, amplitude=amplitude, max_input_bytes=MAX_PAYLOAD_BYTES)
    except (EncodeError, KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    out = {"info": info.describe(), "wav_base64": _wav_b64(wave, cfg.sample_rate), "analysis": analyze_waveform(wave, cfg.sample_rate, info)}
    if channel is not None:
        rx = apply_channel(wave, cfg.sample_rate, channel)
        res = decode(rx, cfg.sample_rate, reference=info)
        out["channel"] = channel.describe()
        out["received_wav_base64"] = _wav_b64(np.clip(rx, -1, 1), cfg.sample_rate)
        out["decode"] = _decode_payload(res)
        out["received_analysis"] = analyze_waveform(np.clip(rx, -1, 1), cfg.sample_rate)
    return out


# -------------------------------------------------------------- endpoints


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__, "time": time.time()}


@app.get("/api/presets")
def presets():
    return {
        "ofdm": {k: v.describe() for k, v in PRESETS.items()},
        "header": header_config(48000).describe(),
        "channels": {k: v.describe() for k, v in CHANNEL_PRESETS.items()},
        "modulations": list(MODULATIONS),
        "code_rates": list(CODE_RATES),
        "compression": available_algorithms(),
        "payload_types": [p.name.lower() for p in PayloadType],
        "limits": {"max_payload_bytes": MAX_PAYLOAD_BYTES, "max_upload_bytes": MAX_UPLOAD_BYTES},
    }


@app.post("/api/config/describe")
def describe_config(cfg: ConfigModel):
    return cfg.build().describe()


@app.post("/api/estimate")
def estimate_endpoint(req: EstimateRequest):
    cfg = req.config.build()
    return {"config": cfg.describe(), "estimate": estimate(cfg, req.n_bytes)}


@app.post("/api/encode")
async def encode_json(req: EncodeJsonRequest):
    cfg = req.config.build()
    data = req.text.encode("utf-8")
    chan = req.channel.build() if req.channel else None
    return await asyncio.get_event_loop().run_in_executor(_executor, _run_encode, data, cfg, req.compression, req.payload_type, req.amplitude, "", chan)


@app.post("/api/encode/file")
async def encode_file(
    file: UploadFile = File(...),
    config: str = Form("{}"),
    compression: str = Form("auto"),
    payload_type: str = Form("binary"),
    amplitude: float = Form(0.8),
    channel: str = Form(""),
):
    data = await _read_upload(file, MAX_PAYLOAD_BYTES)
    try:
        cfg = ConfigModel(**json.loads(config or "{}")).build()
        chan = ChannelModel(**json.loads(channel)).build() if channel else None
    except (json.JSONDecodeError, TypeError) as e:
        raise HTTPException(400, f"bad config: {e}")
    return await asyncio.get_event_loop().run_in_executor(_executor, _run_encode, data, cfg, compression, payload_type, amplitude, file.filename or "", chan)


@app.post("/api/decode")
async def decode_endpoint(file: UploadFile = File(...), channel: str = Form("")):
    data = await _read_upload(file, MAX_UPLOAD_BYTES)
    save_dir = os.environ.get("SONIC_SAVE_UPLOADS")
    if save_dir:  # dev aid for over-the-air tests: keep every uploaded recording
        os.makedirs(save_dir, exist_ok=True)
        with open(os.path.join(save_dir, f"{time.strftime('%Y%m%d-%H%M%S')}-{os.path.basename(file.filename or 'upload.wav')}"), "wb") as fh:
            fh.write(data)
    clip = _clip_from_upload(data)
    x = clip.samples
    chan = None
    if channel:
        try:
            chan = ChannelModel(**json.loads(channel)).build()
        except (json.JSONDecodeError, TypeError) as e:
            raise HTTPException(400, f"bad channel: {e}")

    def work():
        xx = apply_channel(x, clip.sample_rate, chan) if chan else x
        res = decode(xx, clip.sample_rate)
        out = _decode_payload(res)
        out["input"] = {"sample_rate": clip.sample_rate, "channels": clip.channels, "duration_s": clip.duration_s}
        return out

    return await asyncio.get_event_loop().run_in_executor(_executor, work)


@app.post("/api/analyze")
async def analyze_endpoint(file: UploadFile = File(...)):
    data = await _read_upload(file, MAX_UPLOAD_BYTES)
    clip = _clip_from_upload(data)

    def work():
        out = analyze_waveform(clip.samples, clip.sample_rate)
        res = decode(clip.samples, clip.sample_rate)
        out["decode"] = res.describe()
        return out

    return await asyncio.get_event_loop().run_in_executor(_executor, work)


@app.post("/api/channel/apply")
async def channel_apply(file: UploadFile = File(...), channel: str = Form("{}")):
    data = await _read_upload(file, MAX_UPLOAD_BYTES)
    clip = _clip_from_upload(data)
    try:
        chan = ChannelModel(**json.loads(channel or "{}")).build()
    except (json.JSONDecodeError, TypeError) as e:
        raise HTTPException(400, f"bad channel: {e}")

    def work():
        rx = np.clip(apply_channel(clip.samples, clip.sample_rate, chan), -1, 1)
        res = decode(rx, clip.sample_rate)
        return {"wav_base64": _wav_b64(rx, clip.sample_rate), "decode": _decode_payload(res), "channel": chan.describe()}

    return await asyncio.get_event_loop().run_in_executor(_executor, work)


@app.post("/api/qr/encode")
async def qr_encode(req: QrEncodeRequest):
    cfg = PRESETS["audioqr"]
    data = req.text.encode("utf-8")
    return await asyncio.get_event_loop().run_in_executor(_executor, _run_encode, data, cfg, "auto", req.payload_type, req.amplitude, "", None)


@app.post("/api/qr/decode")
async def qr_decode(file: UploadFile = File(...)):
    data = await _read_upload(file, MAX_UPLOAD_BYTES)
    clip = _clip_from_upload(data)

    def work():
        res = decode(clip.samples, clip.sample_rate)
        out = _decode_payload(res)
        out.pop("diagnostics", None)
        out["summary"] = _short_diag(res)
        return out

    return await asyncio.get_event_loop().run_in_executor(_executor, work)


def _short_diag(res) -> dict:
    d = res.diagnostics
    ps = d.get("payload_section", {})
    return {
        "sync_score": (d.get("sync", {}).get("candidates") or [{}])[0].get("score"),
        "snr_db": ps.get("snr_evm_mean_db"),
        "packets": d.get("packets"),
        "sha256": d.get("sha256"),
    }


@app.post("/api/adaptive/plan")
async def adaptive_plan(req: AdaptiveRequest):
    cfg = req.config.build()
    chan = req.channel.build()

    def work():
        from sonic.benchmarking import run_trial, standard_datasets

        try:
            report, probe = measure_channel_state(cfg, chan)
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        snr = np.array(report.carrier_snr_db)
        plan = plan_bit_loading(cfg, snr, n_bands=req.n_bands, margin_db=req.margin_db)
        acfg = apply_plan(cfg, plan)
        fcfg, fplan = best_fixed_config(cfg, snr, margin_db=req.margin_db)
        data = standard_datasets(req.payload_bytes)[0].data
        trials = {}
        for name, c in (("fixed_default", cfg.with_modulation("qpsk", "1/2")), ("fixed_best", fcfg), ("adaptive", acfg)):
            trials[name] = run_trial(data, c, chan, seed=0, compression="none", label=name)
        return {
            "report": {"n_bands": report.n_bands, "band_snr_db": report.band_snr_db, "carrier_snr_db": report.carrier_snr_db, "carrier_frequencies_hz": report.carrier_frequencies_hz, "overhead_bytes": report.overhead_bytes, "probe": probe},
            "plan": plan.describe(),
            "fixed_best": fplan,
            "configs": {"fixed_default": cfg.with_modulation("qpsk", "1/2").describe(), "fixed_best": fcfg.describe(), "adaptive": acfg.describe()},
            "trials": trials,
        }

    return await asyncio.get_event_loop().run_in_executor(_executor, work)


# ---------------------------------------------------------------- benchmarks


def _run_benchmark_job(job_id: str, req: BenchmarkRequest) -> None:
    job = _jobs[job_id]

    def progress(ev: dict) -> None:
        with _jobs_lock:
            job["progress"] = {k: v for k, v in ev.items() if k != "last"}
            if "last" in ev:
                job["records"].append(ev["last"])
            job["updated"] = time.time()

    try:
        chan = req.channel.build() if req.channel else ChannelConfig(name="awgn", snr_db=20.0)
        exp = req.experiment
        if exp == "snr_sweep":
            recs = experiment_snr_sweep(snrs=req.snrs or [0, 3, 6, 9, 12, 15, 18, 21, 24], modulations=req.modulations or ("bpsk", "qpsk", "16qam", "64qam"), trials=req.trials, payload_bytes=req.payload_bytes, progress=progress)
            summ = summarize(recs, ["modulation", "code_rate", "snr_db"])
        elif exp == "carrier_density":
            recs = experiment_carrier_density(carrier_counts=req.carrier_counts or (16, 32, 64, 128, 256, 512, 1024), modulations=req.modulations or ("qpsk", "16qam", "64qam"), channel=chan, trials=req.trials, payload_bytes=req.payload_bytes, progress=progress)
            summ = summarize(recs, ["target_carriers", "modulation"])
        elif exp == "file_sizes":
            recs = experiment_file_sizes(channel=chan, trials=req.trials, progress=progress)
            summ = summarize(recs, ["source_bytes"])
        elif exp == "channels":
            recs = experiment_channels(trials=req.trials, payload_bytes=req.payload_bytes, progress=progress)
            summ = summarize(recs, ["channel", "preset"])
        elif exp == "compression":
            recs = experiment_compression(progress=progress)
            summ = None
        elif exp == "adaptive":
            recs = experiment_adaptive(trials=req.trials, payload_bytes=req.payload_bytes, progress=progress)
            summ = summarize([r for r in recs if "scheme" in r and r.get("scheme") != "probe"], ["channel", "scheme"])
        else:
            raise ValueError(f"unknown experiment {exp!r}")
        with _jobs_lock:
            job["records"] = recs
            job["summary"] = summ
            job["status"] = "done"
    except Exception as e:  # report, never crash the server
        with _jobs_lock:
            job["status"] = "error"
            job["error"] = str(e)
    finally:
        with _jobs_lock:
            job["updated"] = time.time()


@app.post("/api/benchmark/start")
def benchmark_start(req: BenchmarkRequest):
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {"id": job_id, "status": "running", "request": req.model_dump(), "records": [], "summary": None, "progress": {}, "created": time.time(), "updated": time.time()}
    _executor.submit(_run_benchmark_job, job_id, req)
    return {"job_id": job_id}


@app.get("/api/benchmark/jobs")
def benchmark_jobs():
    with _jobs_lock:
        return [{k: v for k, v in j.items() if k not in ("records", "summary")} for j in _jobs.values()]


@app.get("/api/benchmark/{job_id}")
def benchmark_get(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "no such job")
        return json.loads(json.dumps(job, default=str))


@app.get("/api/benchmark/{job_id}/export")
def benchmark_export(job_id: str, format: str = "json"):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "no such job")
        recs = list(job["records"])
        summ = job.get("summary")
    if format == "csv":
        return PlainTextResponse(records_to_csv(recs), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=sonic-{job_id}.csv"})
    return {"job_id": job_id, "records": recs, "summary": summ}


@app.websocket("/api/benchmark/ws/{job_id}")
async def benchmark_ws(ws: WebSocket, job_id: str):
    await ws.accept()
    last_sent = 0
    try:
        while True:
            with _jobs_lock:
                job = _jobs.get(job_id)
                if not job:
                    await ws.send_json({"error": "no such job"})
                    break
                status = job["status"]
                n = len(job["records"])
                new = job["records"][last_sent:n]
                prog = dict(job["progress"])
            if new or status != "running":
                await ws.send_json({"status": status, "progress": prog, "records": new, "error": job.get("error")})
                last_sent = n
            if status != "running":
                break
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        return
    finally:
        try:
            await ws.close()
        except Exception:
            pass


LISTEN_POLL_S = 0.3
LISTEN_MAX_S = 15 * 60


@app.websocket("/api/listen")
async def listen_ws(ws: WebSocket):
    """Continuous receive. First message: {"sample_rate": n} as text; then
    binary frames of mono little-endian int16 PCM. The server replies with
    JSON events: listening, receiving (with progress), received, failed."""
    await ws.accept()
    loop = asyncio.get_event_loop()
    try:
        hello = json.loads(await ws.receive_text())
        fs = int(hello.get("sample_rate", 0))
        if not 16000 <= fs <= 192000:
            await ws.send_json({"type": "error", "error": "sample_rate must be 16-192 kHz"})
            return
        session = ListenSession(fs)
        await ws.send_json({"type": "listening"})
        started = time.monotonic()
        since_poll = 0  # samples fed since the last poll; polls are paced by audio, not wall time
        last_type = "listening"
        while time.monotonic() - started < LISTEN_MAX_S:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                return
            if msg.get("bytes"):
                pcm = np.frombuffer(msg["bytes"], dtype="<i2")
                session.feed(pcm.astype(np.float64) / 32768.0)
                since_poll += pcm.size
            if since_poll < LISTEN_POLL_S * fs:
                continue
            since_poll = 0
            event = await loop.run_in_executor(_executor, session.poll)
            res = event.pop("result", None)
            if res is not None and res.success:
                event.update({k: v for k, v in _decode_payload(res).items() if k in ("data_base64", "text")})
            if event["type"] != "listening" or last_type != "listening":
                await ws.send_json(event)
            last_type = event["type"]
        await ws.send_json({"type": "error", "error": "listening session timed out"})
    except (WebSocketDisconnect, RuntimeError):
        return
    except (ValueError, json.JSONDecodeError) as e:
        try:
            await ws.send_json({"type": "error", "error": f"bad listen stream: {e}"})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


@app.get("/api/results")
def stored_results():
    """Benchmark result files produced by ``sonic benchmark`` (from disk)."""
    out = {}
    if os.path.isdir(RESULTS_DIR):
        for fn in sorted(os.listdir(RESULTS_DIR)):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(RESULTS_DIR, fn)) as f:
                        out[fn[:-5]] = json.load(f)
                except (OSError, json.JSONDecodeError):
                    continue
    return out


@app.get("/api/results/plots")
def stored_plots():
    d = os.path.join(RESULTS_DIR, "plots")
    if not os.path.isdir(d):
        return []
    return sorted(fn for fn in os.listdir(d) if fn.endswith(".png"))


@app.get("/api/results/plots/{name}")
def stored_plot(name: str):
    if "/" in name or ".." in name or not name.endswith(".png"):
        raise HTTPException(400, "bad name")
    p = os.path.join(RESULTS_DIR, "plots", name)
    if not os.path.exists(p):
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png")


# Serve the built frontend when present (production mode).
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
