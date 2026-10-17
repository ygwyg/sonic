# Known limitations

**Validation scope**
- Every result in this repository comes from digital loopback or the
  synthetic channel simulator. No speaker/microphone test has been run in
  this environment (no audio hardware); `sonic play`/`sonic record` and the
  browser microphone path are implemented but **unverified on hardware**.
- The channel presets ("quiet room", "noisy room", …) are hand-designed
  impairment models, not measured rooms.

**Physical layer**
- Sample-rate mismatch is tracked by moving the FFT window; if the
  payload still fails and the tracker measured ≥ 25 ppm, the recording is
  resampled by the estimated ratio and decoded a second time (adds one
  decode's worth of time). Tested to ±300 ppm for all modulations; larger
  offsets, or drift that changes during a transmission, are not handled.
- No Doppler / time-variation tracking beyond per-symbol pilot phase and
  gain; moving transmitters or listeners are out of scope.
- Echo tolerance equals the cyclic prefix (5–43 ms depending on preset);
  longer reverberation becomes noise, which is reported honestly by the
  EVM-based SNR estimate.
- Only one transmission is decoded per call; multiple candidates are
  listed in diagnostics and selectable via `candidate_index`.
- The receiver needs the correct sample rate (from the WAV file or the
  capture device); it does not blindly detect it.
- The convolutional code's cliff is at ≈2 % raw BER; modern codes would
  gain 2–3 dB.

**Protocol**
- Payload ≤ 4 GiB by header field width, ≤ 16 MiB by default limits;
  packet count ≤ 65535.
- File names are truncated to 31 UTF-8 bytes.
- No encryption or authentication; SHA-256 verifies integrity only.
- Adaptive band plans are limited to 16 bands and one code rate per
  transmission; no per-band power control (equal power on enabled
  carriers).

**Software**
- Viterbi decoding is vectorised NumPy but still Python-looped over bits:
  ≈1 s per 16 KiB at rate 1/2. Large files take proportionally longer.
- `zstd`/`codeaware` require the optional `zstandard` package on both
  ends (the receiver reports a clear error otherwise).
- The FastAPI backend keeps benchmark jobs in memory; restart clears them.
- Energy consumption is not measured (no hardware counters available);
  the benchmark records leave that field empty rather than estimating it.
