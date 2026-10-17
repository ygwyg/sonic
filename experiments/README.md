# Experiments

Reproducible experiment scripts. Each writes JSON/CSV into
`../benchmarks/results/` (or a directory you pass) and can be re-run with
different seeds, channels or trial counts. They are thin wrappers around
`sonic.benchmarking`; the CLI `sonic benchmark ...` runs the same code.

| script | question |
|---|---|
| `density_vs_bandwidth.py` | does carrier count change throughput at equal bandwidth? (no) and at equal *carrier spacing* but wider band? (yes, linearly) |
| `adaptive_vs_fixed.py` | adaptive bit loading vs best uniform modulation on frequency-selective channels |
| `cp_length_vs_reverb.py` | cyclic-prefix length vs reverberation time |
| `sro_tolerance.py` | sample-rate-offset tolerance per modulation |

Run from the repository root with `python experiments/<script>.py --help`.
