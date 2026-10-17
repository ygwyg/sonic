"""Command-line interface: ``sonic encode|decode|analyze|benchmark|qr|play|record|serve``."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional

import numpy as np

from sonic.config import CODE_RATES, MODULATIONS, OFDMConfig, PRESETS


def _config_from_args(args) -> OFDMConfig:
    cfg = PRESETS[args.preset]
    overrides = {}
    for k in ("sample_rate", "n_fft", "cp_len", "f_low", "f_high", "pilot_spacing", "modulation", "code_rate", "packet_size"):
        v = getattr(args, k, None)
        if v is not None:
            overrides[k] = v
    if overrides:
        d = {**cfg.describe(), **overrides}
        cfg = OFDMConfig.from_dict(d)
    return cfg


def _add_config_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--preset", default="default", choices=sorted(PRESETS))
    p.add_argument("--sample-rate", dest="sample_rate", type=int)
    p.add_argument("--n-fft", dest="n_fft", type=int)
    p.add_argument("--cp-len", dest="cp_len", type=int)
    p.add_argument("--f-low", dest="f_low", type=float)
    p.add_argument("--f-high", dest="f_high", type=float)
    p.add_argument("--pilot-spacing", dest="pilot_spacing", type=int)
    p.add_argument("--modulation", choices=MODULATIONS)
    p.add_argument("--code-rate", dest="code_rate", choices=CODE_RATES)
    p.add_argument("--packet-size", dest="packet_size", type=int)


def cmd_encode(args) -> int:
    from sonic.audio import write_wav
    from sonic.transmitter import encode

    with open(args.input, "rb") as f:
        data = f.read()
    cfg = _config_from_args(args)
    wave, info = encode(
        data,
        cfg,
        compression=args.compression,
        filename=os.path.basename(args.input),
        amplitude=args.amplitude,
    )
    write_wav(args.output, wave, cfg.sample_rate)
    d = info.describe()
    print(f"wrote {args.output}: {info.duration_s:.2f} s, {info.n_samples} samples @ {cfg.sample_rate} Hz")
    print(f"payload {len(data)} B -> {d['compression']['compressed_size']} B ({d['compression']['algorithm']}), "
          f"{d['header']['n_packets']} packets, net {info.net_bitrate:.0f} bit/s, PAPR {info.papr_db:.1f} dB")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(d, f, indent=1)
    return 0


def cmd_decode(args) -> int:
    from sonic.audio import read_wav
    from sonic.receiver import decode

    clip = read_wav(args.input)
    res = decode(clip.samples, clip.sample_rate, max_output=args.max_output)
    d = res.describe()
    if args.json:
        with open(args.json, "w") as f:
            json.dump(d, f, indent=1)
    if not res.success:
        print(f"DECODE FAILED: {res.error}", file=sys.stderr)
        if res.header:
            print(f"header: {res.header.filename or '(no name)'} {res.header.original_length} B, "
                  f"packets ok {d['diagnostics'].get('packets', {}).get('n_ok')}/{res.header.n_packets}", file=sys.stderr)
        return 2
    out = args.output or res.header.filename or "recovered.bin"
    with open(out, "wb") as f:
        f.write(res.data)
    ps = d["diagnostics"].get("payload_section", {})
    print(f"wrote {out}: {len(res.data)} B, SHA-256 verified ({res.header.sha256.hex()[:16]}...), "
          f"compression {res.header.compression}, est. SNR {ps.get('snr_evm_mean_db', float('nan')):.1f} dB, "
          f"decode {res.decode_time_s:.2f} s")
    return 0


def cmd_analyze(args) -> int:
    from sonic.analysis import analyze_waveform, spectrum, waveform_summary
    from sonic.audio import read_wav
    from sonic.receiver import decode
    from sonic.synchronization import detect_preambles

    clip = read_wav(args.input)
    x, fs = clip.samples, clip.sample_rate
    ws = waveform_summary(x, fs, n_points=50)
    print(f"{args.input}: {ws['duration_s']:.3f} s, {fs} Hz, peak {ws['peak']:.3f}, rms {ws['rms']:.3f}, PAPR {ws['papr_db']:.1f} dB")
    cands = detect_preambles(x, fs)
    print(f"preambles: {[(c.position, round(c.score, 3)) for c in cands]}")
    sp = spectrum(x, fs, max_points=64)
    peak_f = sp["frequency_hz"][int(np.argmax(sp["power_db"]))]
    print(f"spectral peak near {peak_f:.0f} Hz")
    if cands:
        res = decode(x, fs)
        h = res.diagnostics.get("header")
        if h:
            c = h["config"]
            print(f"header: v{h['version']} {h['payload_type']} {h['original_length']} B (tx {h['payload_length']} B, {h['compression']}), "
                  f"{h['n_packets']} packets; payload {c['modulation']} r={c['code_rate']} n_fft={c['n_fft']} cp={c['cp_len']} "
                  f"{c['f_low']:.0f}-{c['f_high']:.0f} Hz, {c['n_active_carriers']} carriers")
            if c["band_modulations"]:
                print(f"adaptive bands: {c['band_modulations']}")
        ps = res.diagnostics.get("payload_section", {})
        if ps:
            print(f"payload SNR (training/EVM): {ps.get('snr_training_mean_db')}/{ps.get('snr_evm_mean_db')} dB, "
                  f"timing drift at end {ps.get('timing_drift_samples', [0])[-1] if ps.get('timing_drift_samples') else 0:.2f} samples")
        print(f"decode: {'OK' if res.success else 'FAILED: ' + str(res.error)}")
    if args.json:
        full = analyze_waveform(x, fs)
        with open(args.json, "w") as f:
            json.dump(full, f)
        print(f"wrote {args.json}")
    return 0


def cmd_qr(args) -> int:
    from sonic.audio import read_wav, write_wav
    from sonic.protocol import PayloadType
    from sonic.receiver import decode
    from sonic.transmitter import encode

    cfg = PRESETS["audioqr"]
    if args.action == "encode":
        text = args.text if args.text is not None else sys.stdin.read()
        wave, info = encode(text.encode("utf-8"), cfg, compression="auto", payload_type=PayloadType.TEXT, amplitude=args.amplitude)
        write_wav(args.output, wave, cfg.sample_rate)
        print(f"wrote {args.output}: {info.duration_s:.2f} s for {len(text.encode())} bytes of text")
        return 0
    clip = read_wav(args.input)
    res = decode(clip.samples, clip.sample_rate)
    if not res.success:
        print(f"DECODE FAILED: {res.error}", file=sys.stderr)
        return 2
    print(res.text)
    return 0


def cmd_play(args) -> int:
    from sonic.audio import AudioDeviceError, play, read_wav

    clip = read_wav(args.input)
    try:
        play(clip.samples, clip.sample_rate, gain=args.gain)
    except AudioDeviceError as e:
        print(f"cannot play: {e}", file=sys.stderr)
        return 3
    return 0


def cmd_record(args) -> int:
    from sonic.audio import AudioDeviceError, record, write_wav

    try:
        x = record(args.seconds, args.sample_rate)
    except AudioDeviceError as e:
        print(f"cannot record: {e}", file=sys.stderr)
        return 3
    write_wav(args.output, x, args.sample_rate)
    print(f"wrote {args.output}")
    return 0


def cmd_benchmark(args) -> int:
    from sonic.benchmarking import (
        calibrate_thresholds,
        experiment_adaptive,
        experiment_carrier_density,
        experiment_channels,
        experiment_compression,
        experiment_file_sizes,
        experiment_snr_sweep,
        summarize,
        write_results,
    )
    from sonic.channel import ChannelConfig, get_channel

    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()

    def progress(ev: dict) -> None:
        if "done" in ev:
            last = ev.get("last", {})
            print(f"\r[{ev['experiment']}] {ev['done']}/{ev['total']}  last: {last.get('modulation', '')} "
                  f"{'ok' if last.get('success') else 'FAIL'} net={last.get('net_bitrate_bps', 0):.0f}      ", end="", flush=True)
        else:
            print(f"\r[{ev.get('experiment')}] {ev}      ", end="", flush=True)

    channel = ChannelConfig(name="awgn", snr_db=args.snr) if args.channel == "awgn" else get_channel(args.channel, snr_db=args.snr)
    meta = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "channel": channel.describe(), "trials": args.trials}
    which = args.experiment
    if which in ("snr", "all"):
        recs = experiment_snr_sweep(snrs=args.snrs, trials=args.trials, progress=progress)
        write_results(recs, os.path.join(out_dir, "snr_sweep.json"), summarize(recs, ["modulation", "code_rate", "snr_db"]), meta)
        print()
    if which in ("carriers", "all"):
        recs = experiment_carrier_density(channel=channel, trials=args.trials, progress=progress)
        write_results(recs, os.path.join(out_dir, "carrier_density.json"), summarize(recs, ["target_carriers", "modulation"]), meta)
        print()
    if which in ("sizes", "all"):
        recs = experiment_file_sizes(channel=channel, trials=args.trials, progress=progress)
        write_results(recs, os.path.join(out_dir, "file_sizes.json"), summarize(recs, ["source_bytes"]), meta)
        print()
    if which in ("channels", "all"):
        recs = experiment_channels(trials=args.trials, progress=progress)
        write_results(recs, os.path.join(out_dir, "channels.json"), summarize(recs, ["channel", "preset"]), meta)
        print()
    if which in ("compression", "all"):
        recs = experiment_compression(progress=progress)
        write_results(recs, os.path.join(out_dir, "compression.json"), None, meta)
        print()
    if which in ("adaptive", "all"):
        recs = experiment_adaptive(trials=args.trials, progress=progress)
        write_results(recs, os.path.join(out_dir, "adaptive.json"), summarize(recs, ["channel", "scheme"]), meta)
        print()
    if which == "calibrate":
        res = calibrate_thresholds(trials=args.trials, progress=progress)
        with open(os.path.join(out_dir, "thresholds.json"), "w") as f:
            json.dump(res, f, indent=1)
        print()
    if args.plots:
        from sonic.benchmarking.plots import make_all_plots

        made = make_all_plots(out_dir, os.path.join(out_dir, "plots"))
        print(f"plots: {made}")
    print(f"benchmark finished in {time.time() - t0:.1f} s; results in {out_dir}")
    return 0


def cmd_serve(args) -> int:
    try:
        import uvicorn
    except ImportError:
        print("uvicorn/fastapi not installed: pip install 'sonic-modem[api]'", file=sys.stderr)
        return 3
    uvicorn.run("sonic.api.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sonic", description="Sonic OFDM acoustic data modem")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("encode", help="encode a file into a WAV transmission")
    e.add_argument("input")
    e.add_argument("--output", "-o", required=True)
    e.add_argument("--compression", default="auto", choices=["auto", "none", "zlib", "lzma", "zstd", "codeaware"])
    e.add_argument("--amplitude", type=float, default=0.8)
    e.add_argument("--json", help="write transmission info JSON")
    _add_config_args(e)
    e.set_defaults(func=cmd_encode)

    d = sub.add_parser("decode", help="decode a WAV transmission into the original file")
    d.add_argument("input")
    d.add_argument("--output", "-o")
    d.add_argument("--max-output", dest="max_output", type=int, default=64 * 1024 * 1024)
    d.add_argument("--json", help="write decode diagnostics JSON")
    d.set_defaults(func=cmd_decode)

    a = sub.add_parser("analyze", help="inspect a WAV file (sync, header, SNR)")
    a.add_argument("input")
    a.add_argument("--json", help="write full explorer analysis JSON")
    a.set_defaults(func=cmd_analyze)

    q = sub.add_parser("qr", help="Audio QR: short text <-> sound")
    q.add_argument("action", choices=["encode", "decode"])
    q.add_argument("--text", "-t")
    q.add_argument("--input", "-i")
    q.add_argument("--output", "-o", default="audioqr.wav")
    q.add_argument("--amplitude", type=float, default=0.6)
    q.set_defaults(func=cmd_qr)

    pl = sub.add_parser("play", help="play a WAV through the speakers (conservative gain)")
    pl.add_argument("input")
    pl.add_argument("--gain", type=float, default=0.5)
    pl.set_defaults(func=cmd_play)

    r = sub.add_parser("record", help="record from the microphone to a WAV")
    r.add_argument("--seconds", type=float, default=10.0)
    r.add_argument("--sample-rate", dest="sample_rate", type=int, default=48000)
    r.add_argument("--output", "-o", default="recording.wav")
    r.set_defaults(func=cmd_record)

    b = sub.add_parser("benchmark", help="run reproducible experiments")
    b.add_argument("experiment", nargs="?", default="all", choices=["all", "snr", "carriers", "sizes", "channels", "compression", "adaptive", "calibrate"])
    b.add_argument("--channel", default="awgn")
    b.add_argument("--snr", type=float, default=20.0)
    b.add_argument("--snrs", type=float, nargs="+", default=[0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30])
    b.add_argument("--trials", type=int, default=3)
    b.add_argument("--out", default="benchmarks/results")
    b.add_argument("--plots", action="store_true", help="render PNG charts with matplotlib")
    b.set_defaults(func=cmd_benchmark)

    s = sub.add_parser("serve", help="run the FastAPI backend")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    s.set_defaults(func=cmd_serve)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
