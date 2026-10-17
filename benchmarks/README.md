# Benchmark results

Produced by

```bash
cd backend
python -m sonic.cli benchmark all --trials 3 --out ../benchmarks/results --plots
python -m sonic.cli benchmark calibrate --trials 3 --out ../benchmarks/results
```

Every file contains `meta` (date, channel, trials), `records` (one row per
actual encode → channel → decode execution, with all metrics) and, where
applicable, `summary` (grouped means with 95 % confidence intervals).
CSV twins of each JSON are provided for spreadsheets.

| file | experiment | grouping |
|---|---|---|
| `snr_sweep.*` | BER / throughput / success vs SNR, AWGN, 4 modulations | modulation, code rate, SNR |
| `carrier_density.*` | 16 … 1024 carriers at equal bandwidth and power | carriers, modulation |
| `file_sizes.*` | transmission time vs file size | size |
| `channels.*` | 4 presets × 5 synthetic channels | channel, preset |
| `compression.*` | zlib / lzma / zstd / code-aware on real source files | sample, algorithm |
| `adaptive.*` | adaptive bit loading vs fixed baselines | channel, scheme |
| `thresholds.json` | measured SNR thresholds used by the bit loader | modulation, rate |
| `plots/*.png` | matplotlib charts of the above | |

Metric definitions (see `sonic/benchmarking/runner.py`):

* `raw_bitrate_bps` – coded bits on data carriers per second
* `info_bitrate_bps` – after FEC (physical-layer information rate)
* `gross_bitrate_bps` – payload bits / audio duration if everything decodes
* `net_bitrate_bps` – same, but **0 when the file did not reconstruct**
* `spectral_efficiency` – info bit/s per Hz of occupied bandwidth
* `raw_ber` – bit errors before FEC against the transmitted coded stream
* `snr_est_db` – receiver's EVM-based in-band SNR estimate

SNR in channel configs is white noise over the full Nyquist band relative
to the average signal power; in-band SNR is higher by 10·log10(fs/2 / BW)
(≈4.8 dB for 8 kHz at 48 kHz).

Interpretation and discussion: `docs/research_log.md`.
