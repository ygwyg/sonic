# Sonic — high-density waveform data transmission engine

Sonic turns arbitrary bytes (source code, text, JSON, binaries) into audio
made of hundreds of **overlapping frequency carriers** (OFDM), writes or
plays it, and reconstructs the original data **byte-for-byte** from a WAV
file or a microphone recording, verified with SHA-256. It is also an
experiment platform: a reproducible benchmark runner, a synthetic channel
simulator, adaptive bit loading with measured thresholds, a code-aware
compression study, and a minimal web app for sending and receiving through
speakers and microphones. The engine also ships analysis code that shows
how the carriers sum into one signal and how the FFT separates them again.

```
INPUT → analysis → lossless compression → packets (CRC-32) → convolutional FEC
      → interleave → scramble → QAM mapping → pilots → IFFT (+cyclic prefix)
      → chirp preamble + robust header → WAV / speaker
      → microphone / WAV → chirp sync → channel estimate → equalise + track drift
      → soft demap → Viterbi → CRC → reassemble → decompress → SHA-256 → OUTPUT
```

Everything runs locally; no cloud services. Signal processing is plain
NumPy/SciPy and usable without the web interface.

## Status at a glance (all numbers measured, see `docs/research_log.md`)

| demonstration | result |
|---|---|
| 1. Digital loopback of a Python program | byte-identical, SHA-256 verified (`examples/demo_loopback.py`) |
| 2. Overlapping carriers + FFT separation | 341 simultaneous carriers, 0 bit errors recovered from one symbol (`examples/demo_overlap.py`) |
| 3. Audio QR | 60-char URL → 1.4 s of sound → decoded from file and through a synthetic noisy room |
| 4. Density experiment | 16 … 1024 carriers at equal bandwidth: identical PHY rate by construction, net throughput 7.7 → 6.5 kbit/s (64-QAM) due to framing granularity — carrier count does **not** add capacity |
| 5. Adaptive encoding | per-band bit loading beats the best uniform modulation on 4 of 6 synthetic channels (+2 … +28 %, at 10× lower raw BER), loses by 6 % on a flat channel and 2 % on a notched one (reported as-is) |
| Tests | 130 automated tests pass (`backend/tests`) |
| Hardware | MacBook Pro speaker → its own mic: decoded up to 64-QAM 3/4 (≈36 dB). Laptop → phone browser at 0.5 m: decoded (21.5 dB). At 2 m: **fails** (room echoes beyond the cyclic prefix). See `docs/research_log.md` H7 |

Headline throughput through WAV files (48 kHz, 2–10 kHz band, default
profile): QPSK 1/2 ≈ 5.6 kbit/s PHY, 64-QAM 3/4 ≈ 25 kbit/s PHY, up to
≈ 67 kbit/s net with the `fast` preset (1.5–14 kHz, 64-QAM 3/4) on a clean
channel. Robust preset (BPSK, 43 ms cyclic prefix) survives all synthetic
rooms except the deliberately hostile "difficult" one.

## Installation

Requirements: Python ≥ 3.12, Node ≥ 20 (for the web app only).

```bash
cd backend
pip install -e ".[all]"          # numpy scipy soundfile sounddevice zstandard fastapi uvicorn matplotlib pytest
# minimal engine only:
pip install -e .
```

`sounddevice` needs PortAudio for real audio (`apt install libportaudio2`
on Debian/Ubuntu); all file-based functionality works without it.

## Command line

```bash
sonic encode input.py --output signal.wav                 # auto compression, default profile
sonic encode photo.jpg -o s.wav --preset fast --modulation 16qam --code-rate 3/4
sonic decode signal.wav --output recovered.py             # exit code 2 + reason on failure
sonic analyze signal.wav --json analysis.json             # sync, header, SNR, spectrum
sonic qr encode --text "hello" -o hello.wav               # Audio QR mode
sonic qr decode --input recording.wav
sonic benchmark --channel awgn --snr 20                   # all experiments → benchmarks/results
sonic benchmark adaptive --trials 3 --plots               # one experiment + PNG charts
sonic benchmark calibrate                                 # measure bit-loading thresholds
sonic play signal.wav --gain 0.5                          # conservative default volume
sonic record --seconds 10 -o recording.wav
sonic serve --port 8000                                   # FastAPI backend (+ built frontend if present)
```

(`python -m sonic.cli …` works without installing the entry point.)

## Python API

```python
from sonic import encode, decode, OFDMConfig, PRESETS
from sonic.audio import write_wav, read_wav
from sonic.channel import apply_channel, get_channel

data = open("program.py", "rb").read()
wave, info = encode(data, OFDMConfig(modulation="16qam", code_rate="2/3"), filename="program.py")
write_wav("signal.wav", wave, info.sample_rate)
print(info.duration_s, info.net_bitrate, info.compression.algorithm, info.papr_db)

rx = apply_channel(wave, info.sample_rate, get_channel("quiet_room"))   # synthetic impairments
result = decode(rx, info.sample_rate, reference=info)                   # reference → raw BER in diagnostics
assert result.success and result.data == data
print(result.diagnostics["payload_section"]["snr_evm_mean_db"], result.diagnostics["raw_ber"])
```

Adaptive bit loading:

```python
import numpy as np
from sonic.adaptive import plan_bit_loading, apply_plan
from sonic.benchmarking import measure_channel_state
report, _ = measure_channel_state(OFDMConfig(), get_channel("quiet_room"))   # probe → 8-band SNR report (9 bytes)
plan = plan_bit_loading(OFDMConfig(), np.array(report.carrier_snr_db), n_bands=8, margin_db=1.0)
cfg = apply_plan(OFDMConfig(), plan)       # band plan travels in the header; receiver needs nothing else
```

## Web app

One page, two actions, like scanning a QR code: **Send** (type a message,
paste a link or drop a file, pick Fast / Balanced / Reliable, press Play)
and **Receive** (press Listen once; the page streams the microphone to the
backend over `/api/listen`, which detects the transmission, shows progress
and decodes it automatically). A received item shows its content, a short
set of link metrics (signal quality, speed, sound length, bytes on air,
clock difference, encoding, packets) and two figures: the received
constellation and signal quality by frequency.

```bash
# terminal 1
cd backend && sonic serve --port 8000
# terminal 2
cd frontend && npm install && npm run dev            # http://localhost:5173
# to receive on a phone on the same Wi-Fi (microphone access needs HTTPS):
cd frontend && SONIC_LAN=1 npm run dev               # https://<your-ip>:5173/#receive, accept the self-signed certificate
# production: npm run build  → backend serves frontend/dist at /
```

Microphone access is only requested when Listen is pressed; decoded content
is displayed as text and never executed.

## Repository layout

```
backend/sonic/      engine + CLI + API (see docs/architecture.md)
backend/tests/      130 pytest tests
frontend/           React + TypeScript + Vite web app (send / receive)
benchmarks/results/ measured results (JSON/CSV) and plots/*.png
experiments/        reproducible experiment scripts
examples/           demo scripts and sample audio (examples/audio/*.wav)
docs/               architecture, protocol, research log, limitations
```

## Physical layer in one paragraph

Real-valued OFDM at 48 kHz (16–96 kHz supported): carriers are FFT bins
inside a configurable band (DC/Nyquist excluded, conjugate symmetry gives
a real waveform via `irfft`), every 8th carrier is a known pilot, two
distinct known training symbols precede the data, a cyclic prefix absorbs
echoes, and one global peak normalisation sets the level (default 0.8 FS,
PAPR ≈ 13 dB thanks to scrambling). Modulations BPSK … 256-QAM (Gray,
unit energy) with exact max-log soft demapping; K=7 (171,133)
convolutional code at rates 1/2, 2/3, 3/4 with soft Viterbi decoding;
CRC-32 per packet and header; SHA-256 per transmission. The header always
uses a fixed robust configuration (1–7 kHz, 4096-point FFT, 21 ms prefix,
BPSK 1/2, sent twice and soft-combined), so the receiver never needs the
header to decode the header. Synchronisation uses a 100 ms chirp;
timing drift from sample-rate mismatch is tracked with a least-squares
regression and, if needed, a resampling second pass. Details:
`docs/protocol.md`, `docs/architecture.md`.

## Testing

```bash
cd backend && python -m pytest -q        # ≈ 2 min; 127 tests
```

Covers modulation mapping/demapping, FFT carrier separation, FEC under
noise, header/packet validation and corruption, compression round-trips
and bomb limits, loopback of every preset and modulation/rate, edge cases
(empty, 1 byte, random, Unicode, already-compressed, 60 kB, other sample
rates, two transmissions in one recording), noise resistance at several
SNRs, synthetic rooms, ±250 ppm drift, timing offset, multipath, frequency
offset, clipping, interference, invalid/truncated/silent/clipped inputs,
adaptive planning, and the CLI. Hardware playback/recording is not covered
by automated tests.

## Scientific stance

* Overlapping carriers organise a band; they do not create capacity.
  Experiments compare configurations at **equal bandwidth, average power,
  channel and reliability target**, and distinguish raw symbol rate, coded
  information rate, spectral efficiency, and *successfully reconstructed*
  application throughput.
* All displayed results come from actual executions; benchmark records
  contain every intermediate metric and the random seed used.
* Channel environments are synthetic models, clearly labelled as such.
* Bit-loading thresholds are measured on this receiver, not copied from
  textbook curves.

## Limitations and next steps

See `docs/limitations.md` (hardware unverified, synthetic channels, CP vs
echo tolerance, Viterbi speed, no encryption) and the "open questions"
section of `docs/research_log.md` (real-room validation, time-varying
drift, decision-directed tracking, LDPC, ultrasonic validation, ARQ).

## License

MIT.
