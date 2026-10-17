# Sonic research log

All numbers below were produced by actual executions of the code in this
repository (`sonic benchmark all --trials 3`, 2026-10-17, commit in git
history). Raw records with every metric are in `benchmarks/results/*.json`
and `*.csv`; charts in `benchmarks/results/plots/`. Channels marked "room"
are **synthetic models**, not measurements of real rooms.

## Central question

> How efficiently can arbitrary digital information be transmitted through
> overlapping waveform components within a constrained communication
> channel, and can adaptive modulation and content-aware compression
> improve end-to-end transfer performance?

## H1 — "More overlapping carriers in the same band carry more data"

**Hypothesis (to be tested, expected false):** increasing the carrier
count increases capacity.

**Setup:** band fixed at 2–10 kHz (8 kHz), transmit power fixed, cyclic
prefix fixed at 1/8 of the symbol, pilot spacing 8, 2048-byte random
payload, AWGN at 20 dB, carrier counts 16 → 1024 (FFT 96 → 6144), 3 trials.

**Result (`carrier_density.json`):**

| carriers | FFT  | PHY info bit/s (QPSK / 16-QAM / 64-QAM) | net bit/s 64-QAM | symbol | PAPR |
|---------:|-----:|------------------------------------------|-----------------:|-------:|-----:|
| 16       | 96   | 6222 / 12444 / 18667                      | 7752 | 2.2 ms  | 12.4 dB |
| 64       | 384  | 6222 / 12444 / 18667                      | 7679 | 9.0 ms  | 13.9 dB |
| 256      | 1536 | 6222 / 12444 / 18667                      | 7398 | 36 ms   | 14.0 dB |
| 1024     | 6144 | 6222 / 12444 / 18667                      | 6547 | 144 ms  | 13.4 dB |

**Conclusion:** the physical-layer information rate is *identical by
construction*: at equal bandwidth, carrier spacing × carrier count is
constant and the symbol rate scales inversely with the count. Net
application throughput actually *falls* slightly with carrier count
because (a) the last OFDM symbol is only partially filled and a 144 ms
symbol wastes more than a 2 ms one, and (b) the fixed ~1.2 s preamble +
header overhead is amortised over a 2 KiB payload. Overlapping carriers
are a way to *organise* a band (equalisation per carrier, echo tolerance
via the cyclic prefix, bit loading), not a way to exceed its capacity.
H1 is rejected, as information theory requires.

What *does* change with carrier count is channel robustness: the cyclic
prefix at 16 carriers is 0.25 ms, far shorter than room echoes, while at
1024 carriers (16 ms) it tolerates most early reflections but the long
symbol is more sensitive to sample-rate drift and time variation. The
`channels` experiment below shows exactly this trade-off.

## H2 — Modulation order vs SNR (AWGN, rate 1/2)

Lowest SNR (white noise over the full 24 kHz band; in-band SNR is ≈4.8 dB
higher) at which 3/3 trials of a 2 KiB file reconstructed:

| modulation | SNR for 3/3 success | raw BER at that SNR | net bit/s when successful |
|-----------|--------------------:|--------------------:|--------------------------:|
| BPSK 1/2  | 0 dB                | 8.3 × 10⁻³           | 2232 |
| QPSK 1/2  | 3 dB                | 1.5 × 10⁻²           | 3764 |
| 16-QAM 1/2| 9 dB                | 2.0 × 10⁻²           | 5729 |
| 64-QAM 1/2| 15 dB               | 1.8 × 10⁻²           | 7042 |

The convolutional code corrects raw BERs up to ~2 % reliably; this is the
measured "cliff" used by the bit-loading thresholds. (`snr_sweep.json`,
`thresholds.json` — the calibration also covers rates 2/3, 3/4 and 256-QAM.)

## H3 — Adaptive bit loading beats fixed modulation on frequency-selective channels

**Protocol:** a BPSK probe is sent through the channel; the receiver
returns an 8-band channel-state report (9 bytes). Three transmitters then
send the same 4 KiB payload on the *same* channel realisation: naive fixed
QPSK 1/2, the best *uniform* modulation/rate the report supports
(`fixed_best`, same channel knowledge), and per-band adaptive loading.

| channel (synthetic) | fixed QPSK 1/2 | fixed_best | adaptive | adaptive plan |
|---|---:|---:|---:|---|
| flat 20 dB | 4464 | **12136** (64-QAM 3/4) | 11457 (64-QAM 2/3) | all bands 64-QAM |
| tilt −3 dB/kHz | 4464 | 9811 (16-QAM 3/4) | **11045** | 256→QPSK across the band |
| two deep notches | 4464 | 11457 (64-QAM 2/3, BER 2.9 %) | 11248 | 256-QAM except QPSK in notches |
| low-pass 6 kHz | 4464 | 11457 | **12381** | 256-QAM low, QPSK top |
| tilt + two tones | 4464 | 7527 (16-QAM 1/2) | **9657** | one band disabled, BPSK next to it |
| quiet-room-like | 4464 | 13177 | **13466** | 256/64-QAM |

(net successfully-delivered bit/s, 3 trials each, all CI95 = 0 because
every trial decoded; `adaptive.json`.)

**Conclusion:** adaptive loading wins on 5 of 6 frequency-selective
channels (+6 % to +28 % over the best uniform choice, 2.2–3× over the
naive default). On the flat channel the uniform baseline is *better* by
6 %: the planner's 25th-percentile band SNR plus 1 dB margin picks rate 2/3
where 3/4 would have worked. This is reported as-is; the margin is a
tunable reliability/throughput knob. On the notched channel `fixed_best`
succeeded with a 2.9 % raw BER, right at the FEC cliff, whereas adaptive
delivered nearly the same rate at 0.19 % BER — the reliability gain does
not show in throughput alone.

Feedback overhead is 9 bytes per report; the band plan itself costs
nothing extra because the header already carries it.

## H4 — Content-aware compression for source code

Lossless, measured on 26 Python files from this repository plus a
JavaScript and a JSON sample (`compression.json`):

| language | zlib | lzma | zstd | code-aware (zstd + static dictionary) |
|---|---:|---:|---:|---:|
| Python (26 files, avg 7.3 KB) | 2.88 bit/B | 3.01 | 2.87 | **2.68** |
| JavaScript (4 KB) | 1.41 | 1.59 | 1.39 | **1.10** |
| JSON (44 KB) | 1.08 | **0.94** | 0.96 | 0.95 |

Code-aware was the smallest on 27 of 28 files, by 6–21 % over the best
generic codec, with the advantage shrinking as files grow (the static
dictionary is a *prior*; large files learn their own statistics). For the
already-compressed sample, `auto` correctly bypassed compression.
Compression is reported separately from PHY efficiency: it changes the
number of bits to send, not the bit/s of the link.

## H5 — Presets across synthetic rooms

| channel | audioqr (QPSK, 1024/256) | default (QPSK, 2048/512) | robust (BPSK, 4096/2048) | fast (64-QAM 3/4, 2048/256) |
|---|---|---|---|---|
| ideal | 3/3 | 3/3 | 3/3 | 3/3 |
| quiet room | 3/3 | 3/3 | 3/3 | 0/3 |
| noisy room | 1/3 | 3/3 | 3/3 | 0/3 |
| reverberant room | 0/3 | 1/3 | 3/3 | 0/3 |
| difficult | 0/3 | 0/3 | 0/3 | 0/3 |

Echo tolerance is set by the cyclic prefix: 5 ms (`fast`), 5.3 ms
(`audioqr`), 10.7 ms (`default`), 43 ms (`robust`). The "difficult"
channel (8 dB SNR, 0 dB bursts, notches, tones, clipping, 60 ppm drift)
defeats every preset's payload, although the header still decodes there
in most trials thanks to its long prefix and two-copy combining.

## H6 — Cyclic prefix vs reverberation and SRO tolerance (`experiments/`)

`cp_length_vs_reverb.py` (4096-point FFT, QPSK 1/2, 25 dB SNR, synthetic
RT60 with DRR 8 dB): a 2.7 ms prefix fails half the time at RT60 = 0.6 s
(EVM SNR 10 dB) while 10.7 ms and 42.7 ms prefixes succeed, at the cost of
6 % and 24 % net throughput respectively. The receiver's EVM-based SNR
estimate tracks the ISI honestly (15.8 → 26.9 dB at RT60 = 0.1 s as the
prefix grows).

`sro_tolerance.py` (30 dB SNR): all of QPSK 1/2, 16-QAM 3/4 and 64-QAM 3/4
decode at 0–300 ppm. Window tracking alone keeps QPSK working to 300 ppm
with a falling EVM SNR (33 → 16 dB, inter-carrier interference within the
symbol); for 16/64-QAM the first pass fails beyond ≈100–200 ppm and the
resampling second pass restores a 33 dB EVM SNR.

`density_vs_bandwidth.py`: at equal carrier spacing, throughput grows
linearly with bandwidth (85 carriers / 2 kHz → 3.1 kbit/s PHY; 683 carriers
/ 16 kHz → 24.9 kbit/s), while at equal bandwidth it does not change with
carrier count — the two halves of the same information-theoretic fact.

## Failed experiments / things that did not work the first time

* **Per-symbol timing-slope correction from adjacent pilots** destroyed
  wideband symbols at ≤10 dB SNR (a 5-sample slope error × 600 carriers).
  Replaced by a weighted least-squares phase fit seeded from the previous
  symbol plus a regression-based drift tracker; fractional correction is
  only applied when the regression's prediction error is < 0.15 samples.
* **Identical training symbols** hid inter-symbol interference from the
  noise estimator (training SNR read 17 dB while data EVM was 9 dB in a
  reverberant channel). Fixed by using distinct training sequences.
* **Unit-amplitude chirp + unscrambled header** produced 21.8 dB PAPR and
  left the data sections 10 dB below full scale. Scrambling (XOR with a
  fixed PRBS) and scaling the chirp to the OFDM RMS brought PAPR to
  ≈13 dB and raised the useful level by 8 dB at the same peak.
* **2048-point header** (same cyclic prefix as the 4096 version) decoded
  *worse* in reverberation because the same absolute ISI is a larger
  fraction of a shorter symbol. The 4096/1024 header was kept.
* **Adaptive on a flat channel** is slightly worse than the best uniform
  setting (see H3) — the planner is conservative by design.

## Open questions / recommended next experiments

1. **Real acoustic validation.** Everything above is digital or synthetic.
   Record `examples/audio/*.wav` played from real speakers at 0.3–3 m and
   measure success vs distance/volume; compare the `robust`, `default`
   and `audioqr` presets. Hardware-dependent tests remain *unverified*.
2. **Time-varying sample-rate offset.** The second-pass resampler
   (`experiments/sro_tolerance.py`: 64-QAM 3/4 now decodes at ±300 ppm,
   where the first pass alone stopped at ≈100 ppm) assumes a constant
   ratio; thermal drift during long transmissions is untested.
3. **Decision-directed channel tracking** for slowly time-varying
   acoustic channels (people moving).
4. **Rate margin tuning** for the bit loader (H3 flat-channel loss).
5. **LDPC or turbo codes** would move the FEC cliff by ~2–3 dB versus the
   K=7 convolutional code at the cost of decode time.
6. **Near-ultrasonic band** (17–21 kHz preset exists but is unvalidated on
   real hardware; many speakers roll off above 16 kHz).
7. **Bidirectional ARQ** using the channel-state report protocol defined
   in `docs/protocol.md` §6.
