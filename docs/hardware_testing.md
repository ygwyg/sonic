# Hardware validation procedure (unverified in this repository)

The build environment used for this repository has no audio devices, so
the speaker/microphone path is implemented but **not validated**. This is
the procedure to validate it; please record results in
`docs/research_log.md`.

## Setup

* Two machines (or one machine with a loopback-free speaker/mic pair), both
  with `pip install -e "backend[all]"` and PortAudio installed.
* Start at conservative volume: `sonic play --gain 0.3`. Never exceed
  `--gain 1.0`; the CLI clips there and the dashboard volume defaults to 0.5.
* Use 48 kHz on both ends (`sonic record --sample-rate 48000`).

## Test 1 — Audio QR, 30–100 cm

```bash
# sender
sonic qr encode --text "hardware test 1" -o qr.wav
sonic play qr.wav --gain 0.4
# receiver (start first; 6 s is enough for a short message)
sonic record --seconds 6 -o rec.wav
sonic qr decode --input rec.wav
sonic analyze rec.wav        # sync score, SNR estimate, header
```

Expected: `sync score > 0.3`, payload EVM SNR > 8 dB, text recovered.
Record: distance, gain, room, success, SNR estimate.

## Test 2 — source file with each preset

```bash
sonic encode examples/hello.py -o robust.wav --preset robust
sonic encode examples/hello.py -o default.wav --preset default
sonic encode examples/hello.py -o fast.wav --preset fast
```

Play each; record with `--seconds 30`; `sonic decode rec.wav -o out.py`
and `cmp examples/hello.py out.py`. Expect `robust` to work in most rooms,
`default` in quiet rooms at < 2 m, `fast` only at short range with good
speakers (it needs ≈ 21 dB in-band SNR and uses up to 14 kHz).

## Test 3 — sample-rate mismatch

Phones and laptops commonly differ by 20–150 ppm. Check
`sonic decode --json d.json` → `diagnostics.payload_section.timing_drift_samples`
(last value / payload duration in samples ≈ ppm) and whether
`diagnostics.sro_compensation` was triggered.

## Test 4 — near-ultrasonic (optional)

`--preset ultrasonic` (17–21 kHz). Many speakers roll off above 16 kHz and
some microphones apply low-pass filtering; failure here is a hardware
limitation, not a decoder bug. Check the receiver's
`payload_section.channel_magnitude_db` to see the actual response.

## What to report

For each run: preset, distance, gain, room description, `sync score`,
`snr_evm_mean_db`, packets ok/total, success, and the estimated ppm.
Attach the recording if it failed; `sonic analyze` output is enough for
successes.
