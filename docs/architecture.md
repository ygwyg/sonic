# Sonic architecture

```
backend/sonic/
├── config.py          OFDMConfig (geometry, carrier plan, presets, fixed header config)
├── modulation/        Gray-coded BPSK … 256-QAM, exact max-log soft demapping
├── fec/               K=7 convolutional code + punctured rates, soft Viterbi,
│                      CRC-32, pseudo-random interleaver, scrambler
├── protocol/          versioned header, packet framing, frame layout
├── compression/       zlib / lzma / zstd / code-aware (static language dictionaries),
│                      decompression-bomb limits
├── ofdm/              IFFT/FFT symbol generation, pilots, training, bit↔carrier
│                      mapping with per-carrier bit loading, chirp preamble
├── synchronization/   preamble detection, channel estimation, equaliser,
│                      timing-drift tracking, per-symbol noise weighting
├── transmitter/       encode(): bytes → waveform (+ TransmissionInfo for benchmarks)
├── receiver/          decode(): waveform → bytes with full diagnostics
├── channel/           synthetic impairment simulator and named environments
├── adaptive/          channel-state report, deterministic bit loading, fixed baseline
├── analysis.py        explorer data (envelope, spectrum, spectrogram, carrier split)
├── benchmarking/      datasets, trial runner, experiments, summaries, PNG plots
├── audio/             WAV I/O (validating), speaker/mic via sounddevice (optional)
├── api/               FastAPI backend (+ WebSocket progress)
└── cli.py             `sonic encode|decode|analyze|qr|benchmark|play|record|serve`
```

The signal-processing engine has no dependency on the web layer; the
`sonic` package is usable from Python or the CLI without the frontend.

## Transmit pipeline

1. **Compression** (`compression.choose_compression`): `auto` tries every
   available codec and keeps the smallest; it falls back to `none` when
   compression would grow the payload (already-compressed inputs).
2. **Header** (`protocol.TransmissionHeader`): lengths, SHA-256, payload
   type, compression, full payload PHY configuration, CRC-32.
3. **Packets** (`protocol.split_packets`): `index | data | CRC-32`.
4. **FEC** (`fec.convolutional`): per packet, terminated, punctured to the
   configured rate, interleaved.
5. **Mapping** (`ofdm.mapping`): pad to a whole OFDM symbol, scramble, map
   bits to constellation points carrier-by-carrier (bit loading aware).
6. **OFDM** (`ofdm.modem`): insert pilots, build the Hermitian spectrum,
   IFFT (`numpy.fft.irfft`), prepend the cyclic prefix.
7. **Framing**: chirp (scaled to OFDM RMS) + guard + header section (fixed
   config, two copies) + payload section + tail guard; one global peak
   normalisation (`amplitude`, default 0.8 FS).

## Receive pipeline

1. **Input validation**: mono/stereo, int/float, finite, non-silent.
2. **Sync** (`synchronization.detect_preambles`): normalised matched filter
   against the chirp; multiple transmissions in one recording are listed
   as candidates.
3. **Header section** (`synchronization.demodulate_section` with the fixed
   header config): training-based channel + noise estimate, window-start
   refinement from the channel's group delay, per-symbol pilot fit
   (common phase, timing slope via weighted least squares, gain), soft
   demapping, copy combining, de-scramble/de-interleave, Viterbi, CRC.
4. **Payload section**: same machinery with the header's configuration.
   A least-squares drift tracker predicts the timing offset of each
   symbol; the FFT window follows it in whole samples (so sample-rate
   mismatch cannot walk the window out of the cyclic prefix) and a
   fractional correction is applied only when the regression is
   demonstrably accurate.
5. **Noise weighting**: LLRs are scaled by a per-carrier noise estimate
   (from training) times a per-symbol factor (from pilot residuals), so
   notched carriers and burst-hit symbols are discounted by the decoder.
6. **Packets → payload → decompression (size-capped) → SHA-256**. Any
   failure returns `success=False` with the failing stage; no data is
   emitted.

## Key design decisions

* **Fixed header configuration** removes the circular dependency between
  "what are the parameters" and "how do I decode the parameters".
* **Real-valued OFDM** via Hermitian symmetry: only bins 1..N/2−1 carry
  data; DC and Nyquist are always zero.
* **Scrambling** is essential: structured payloads (zero padding, sparse
  files) otherwise put the same value on hundreds of carriers and create
  >20 dB PAPR spikes that dominate peak normalisation.
* **Distinct training sequences** make reverberation beyond the cyclic
  prefix visible to the noise estimator.
* **Equal-bandwidth carrier experiments** change the FFT size, not the
  band, so the information rate is identical by construction and only
  channel effects can differ.
* **Measured thresholds** for adaptive bit loading come from
  `sonic benchmark calibrate` runs on the real receiver, not textbook curves.
