"""Receiver: waveform -> sync -> header -> payload -> packets -> data.

A transmission that cannot be fully validated (header CRC, packet CRCs,
decompression, SHA-256) yields ``success=False`` and ``data=None``;
partial information is only exposed through ``diagnostics``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from sonic.compression import DEFAULT_MAX_OUTPUT, DecompressionError, decompress
from sonic.config import OFDMConfig, header_config
from sonic.fec import convolutional, deinterleave, descramble_llr
from sonic.ofdm import data_symbols_to_hard_bits, data_symbols_to_llr
from sonic.protocol import HEADER_SIZE, HeaderError, TransmissionHeader, bits_to_bytes, sha256, verify_packets
from sonic.protocol.layout import HEADER_REPEATS, frame_layout, header_coded_bits, header_symbols_per_copy, payload_coded_lengths
from sonic.synchronization import DEFAULT_THRESHOLD, SectionError, SectionResult, demodulate_section, detect_preambles

MAX_CONSTELLATION_POINTS = 4000


class DecodeError(ValueError):
    pass


@dataclass
class DecodeResult:
    success: bool
    data: Optional[bytes]
    error: Optional[str]
    header: Optional[TransmissionHeader]
    diagnostics: dict = field(default_factory=dict)
    decode_time_s: float = 0.0

    @property
    def text(self) -> Optional[str]:
        if self.data is None:
            return None
        return self.data.decode("utf-8", "replace")

    def describe(self) -> dict:
        return {
            "success": self.success,
            "error": self.error,
            "header": self.header.describe() if self.header else None,
            "decode_time_s": self.decode_time_s,
            "diagnostics": self.diagnostics,
        }


def _section_diag(sec: SectionResult, cfg: OFDMConfig, name: str) -> dict:
    pts = sec.symbols.reshape(-1)
    if pts.size > MAX_CONSTELLATION_POINTS:
        step = int(np.ceil(pts.size / MAX_CONSTELLATION_POINTS))
        pts = pts[::step]
    snr_t = sec.snr_training_db
    d = {
        "window_start": int(sec.start),
        "timing_refine_samples": int(sec.timing_refine),
        "n_symbols_requested": sec.n_symbols_requested,
        "n_symbols_available": sec.n_symbols_available,
        "truncated": sec.truncated,
        "channel_magnitude_db": (20 * np.log10(np.maximum(np.abs(sec.channel), 1e-12))).round(2).tolist(),
        "carriers": cfg.active_carriers.tolist(),
        "carrier_frequencies_hz": (cfg.active_carriers * cfg.carrier_spacing).round(2).tolist(),
        "snr_training_db": None if np.all(np.isnan(snr_t)) else np.nan_to_num(snr_t, nan=0.0).round(2).tolist(),
        "snr_training_mean_db": None if np.all(np.isnan(snr_t)) else float(np.nanmean(snr_t)),
        "snr_evm_db": None if sec.snr_evm_db is None else sec.snr_evm_db.round(2).tolist(),
        "snr_evm_mean_db": None if sec.snr_evm_db is None else float(np.mean(sec.snr_evm_db)),
        "timing_drift_samples": [round(x, 3) for x in sec.drift_samples],
        "common_phase_rad": [round(x, 4) for x in sec.phase_track],
        "gain_track": [round(x, 4) for x in sec.gain_track],
        "constellation": {"re": pts.real.round(4).tolist(), "im": pts.imag.round(4).tolist()},
    }
    return {name: d}


def _decode_header(samples: np.ndarray, start: int, hcfg: OFDMConfig, n_sym: int, diag: dict):
    sec = demodulate_section(samples, start, hcfg, n_sym)
    diag.update(_section_diag(sec, hcfg, "header_section"))
    if sec.truncated:
        raise DecodeError("recording ends before the header is complete")
    llr_all = data_symbols_to_llr(hcfg, sec.symbols, sec.noise_var)
    n_coded = header_coded_bits()
    per_copy = header_symbols_per_copy(hcfg) * hcfg.bits_per_ofdm_symbol
    llr = np.zeros(n_coded)
    for c in range(HEADER_REPEATS):  # combine the repeated copies
        llr += descramble_llr(llr_all[c * per_copy : (c + 1) * per_copy])[:n_coded]
    llr = deinterleave(llr)
    bits = convolutional.decode(llr, HEADER_SIZE * 8, "1/2")
    return TransmissionHeader.unpack(bits_to_bytes(bits), hcfg.sample_rate), sec


SRO_RETRY_MIN_PPM = 25.0


def decode(
    samples: np.ndarray,
    sample_rate: int,
    max_output: int = DEFAULT_MAX_OUTPUT,
    sync_threshold: float = DEFAULT_THRESHOLD,
    reference=None,
    candidate_index: int = 0,
    sro_compensation: bool = True,
) -> DecodeResult:
    """Decode one transmission from a mono recording.

    ``reference`` may be the :class:`~sonic.transmitter.TransmissionInfo`
    of the original encode; when given, raw and coded bit error rates are
    measured and added to the diagnostics.

    With ``sro_compensation`` (default), a payload that fails while the
    timing tracker measured a clear sample-rate offset is decoded a second
    time after band-limited resampling of the whole recording by the
    estimated ratio. This removes the inter-carrier interference that
    window tracking alone cannot, which matters for 64/256-QAM.
    """
    res = _decode_once(samples, sample_rate, max_output, sync_threshold, reference, candidate_index)
    if res.success or not sro_compensation or res.header is None:
        return res
    ppm = estimated_sro_ppm(res.diagnostics, res.header.config.symbol_len)
    if ppm is None or abs(ppm) < SRO_RETRY_MIN_PPM:
        return res
    from scipy.signal import resample

    x = _as_mono_float(samples)
    n_new = int(round(x.size / (1 + ppm * 1e-6)))
    if n_new < 16 or n_new > 4 * x.size:
        return res
    t0 = time.perf_counter()
    x2 = resample(x, n_new)
    res2 = _decode_once(x2, sample_rate, max_output, sync_threshold, reference, candidate_index)
    res2.diagnostics["sro_compensation"] = {
        "estimated_ppm": ppm,
        "resampled_to": n_new,
        "first_pass_error": res.error,
        "resample_time_s": time.perf_counter() - t0,
    }
    res2.decode_time_s += res.decode_time_s
    return res2 if res2.success or res2.header is not None else res


def estimated_sro_ppm(diag: dict, symbol_len: int) -> Optional[float]:
    """Sample-rate offset implied by the payload timing-drift track."""
    drift = diag.get("payload_section", {}).get("timing_drift_samples")
    if not drift or len(drift) < 8:
        return None
    y = np.asarray(drift, dtype=np.float64)
    t = np.arange(y.size) * symbol_len
    slope = np.polyfit(t, y, 1)[0]  # samples of drift per sample of time
    return float(slope * 1e6)


def _as_mono_float(samples) -> np.ndarray:
    x = np.asarray(samples)
    if x.ndim == 2:
        x = x.mean(axis=1)
    if np.issubdtype(x.dtype, np.integer):
        x = x.astype(np.float64) / float(np.iinfo(x.dtype).max)
    return x.astype(np.float64)


def _decode_once(
    samples: np.ndarray,
    sample_rate: int,
    max_output: int,
    sync_threshold: float,
    reference,
    candidate_index: int,
) -> DecodeResult:
    t0 = time.perf_counter()
    diag: dict = {}

    def fail(msg: str, header=None) -> DecodeResult:
        diag.setdefault("stage_failed", msg)
        return DecodeResult(False, None, msg, header, diag, time.perf_counter() - t0)

    try:
        x = np.asarray(samples)
    except Exception:
        return fail("input is not a numeric array")
    if x.ndim == 2:
        x = x.mean(axis=1)
    if x.ndim != 1:
        return fail("audio must be mono (1-D) or (n, channels)")
    if np.issubdtype(x.dtype, np.integer):
        x = x.astype(np.float64) / float(np.iinfo(x.dtype).max)
    x = x.astype(np.float64)
    if x.size == 0:
        return fail("recording is empty")
    if not np.all(np.isfinite(x)):
        return fail("recording contains non-finite samples")
    if sample_rate < 16000:
        return fail("sample rate must be >= 16 kHz")
    peak = float(np.max(np.abs(x)))
    diag["input"] = {
        "n_samples": int(x.size),
        "duration_s": x.size / sample_rate,
        "peak": peak,
        "rms": float(np.sqrt(np.mean(x**2))),
        "clipped_fraction": float(np.mean(np.abs(x) >= 0.999)) if peak >= 0.999 else 0.0,
    }
    if peak < 1e-6:
        return fail("recording is silent")

    # ---- synchronisation
    cands = detect_preambles(x, sample_rate, threshold=sync_threshold)
    diag["sync"] = {
        "candidates": [{"position": c.position, "score": round(c.score, 4)} for c in cands],
        "threshold": sync_threshold,
    }
    if not cands:
        return fail("no preamble found (no Sonic transmission detected)")
    if candidate_index >= len(cands):
        return fail(f"candidate {candidate_index} does not exist")
    cand = cands[candidate_index]
    diag["sync"]["selected"] = candidate_index

    # ---- header
    hcfg = header_config(sample_rate)
    lay0 = frame_layout(0, hcfg, preamble_start=cand.position)
    pre_advance = hcfg.cp_len // 4
    try:
        header, hsec = _decode_header(x, lay0.header_start - pre_advance, hcfg, lay0.n_header_symbols, diag)
    except SectionError as e:
        return fail(f"header: {e}")
    except DecodeError as e:
        return fail(str(e))
    except HeaderError as e:
        return fail(f"invalid header: {e}")
    diag["header"] = header.describe()
    cfg = header.config

    # ---- payload
    layout = frame_layout(header.payload_length, cfg, preamble_start=cand.position)
    diag["layout"] = {s["name"]: [s["start"], s["end"]] for s in layout.sections()}
    p_adv = min(cfg.cp_len // 4, 64)
    try:
        psec = demodulate_section(x, layout.payload_start - p_adv, cfg, layout.n_payload_symbols)
    except SectionError as e:
        return fail(f"payload: {e}", header)
    diag.update(_section_diag(psec, cfg, "payload_section"))

    coded_lengths = payload_coded_lengths(header.payload_length, cfg)
    llr_all = data_symbols_to_llr(cfg, psec.symbols, psec.noise_var)
    n_padded = layout.n_payload_symbols * cfg.bits_per_ofdm_symbol
    llr_all = descramble_llr(np.concatenate([llr_all, np.zeros(max(0, n_padded - llr_all.size))]))[: llr_all.size]
    if reference is not None:
        _reference_metrics(diag, cfg, psec, llr_all, reference)

    packets: list[bytes] = []
    pos = 0
    n_missing = 0
    for i, n_coded in enumerate(coded_lengths):
        chunk = llr_all[pos : pos + n_coded]
        pos += n_coded
        if chunk.size < n_coded:
            n_missing += 1
            packets.append(b"")  # missing -> CRC fails
            continue
        info_bits = convolutional.decode(deinterleave(chunk), _packet_info_bits(i, header, cfg), cfg.code_rate)
        packets.append(bits_to_bytes(info_bits))
    payload, report = verify_packets(packets)
    rep = report.describe()
    rep["missing"] = n_missing
    diag["packets"] = rep
    if payload is None:
        what = []
        if n_missing:
            what.append(f"{n_missing} packet(s) missing (recording truncated)")
        if report.crc_failed:
            what.append(f"{len(report.crc_failed)} packet(s) failed CRC")
        if report.index_mismatch:
            what.append(f"{len(report.index_mismatch)} packet(s) out of order")
        return fail("payload integrity failure: " + "; ".join(what), header)
    if len(payload) != header.payload_length:
        return fail("payload length mismatch", header)

    try:
        data = decompress(payload, header.compression, max_output=max_output)
    except DecompressionError as e:
        return fail(f"decompression failed: {e}", header)
    if len(data) != header.original_length:
        return fail("decompressed length does not match header", header)
    digest = sha256(data)
    diag["sha256"] = {"expected": header.sha256.hex(), "actual": digest.hex(), "match": digest == header.sha256}
    if digest != header.sha256:
        return fail("SHA-256 verification failed", header)
    return DecodeResult(True, data, None, header, diag, time.perf_counter() - t0)


def _packet_info_bits(i: int, header: TransmissionHeader, cfg: OFDMConfig) -> int:
    from sonic.protocol.packets import packet_sizes

    return packet_sizes(header.payload_length, cfg.packet_size)[i] * 8


def _reference_metrics(diag: dict, cfg: OFDMConfig, psec: SectionResult, llr_all: np.ndarray, ref) -> None:
    """Raw (pre-FEC) BER against the transmitter's coded bit stream."""
    try:
        from sonic.fec import scramble

        tx_bits = scramble(np.asarray(ref.coded_bit_stream, dtype=np.uint8))
        n_sym = psec.symbols.shape[0]
        B = cfg.bits_per_ofdm_symbol
        n = min(tx_bits.size, n_sym * B)
        hard = data_symbols_to_hard_bits(cfg, psec.symbols)[:n]
        errors = int(np.sum(hard != tx_bits[:n]))
        diag["raw_ber"] = errors / max(1, n)
        diag["raw_bit_errors"] = errors
        diag["raw_bits_compared"] = int(n)
        tx_syms = np.asarray(ref.data_symbols).reshape(-1)[: psec.symbols.size]
        rx_syms = psec.symbols.reshape(-1)[: tx_syms.size]
        if tx_syms.size:
            evm = np.sqrt(np.mean(np.abs(rx_syms - tx_syms) ** 2))
            diag["evm_rms"] = float(evm)
            diag["snr_from_evm_db"] = float(-20 * np.log10(max(evm, 1e-9)))
    except Exception as e:  # diagnostics must never break decoding
        diag["reference_error"] = str(e)
