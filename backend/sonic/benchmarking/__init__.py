"""Reproducible benchmarking of the Sonic modem."""

from sonic.benchmarking.datasets import Sample, standard_datasets, source_corpus
from sonic.benchmarking.runner import (
    calibrate_thresholds,
    config_for_carriers,
    default_adaptive_channels,
    experiment_adaptive,
    experiment_carrier_density,
    experiment_channels,
    experiment_compression,
    experiment_file_sizes,
    experiment_snr_sweep,
    measure_channel_state,
    records_to_csv,
    run_quick_suite,
    run_trial,
    summarize,
    write_results,
)

__all__ = [
    "Sample",
    "standard_datasets",
    "source_corpus",
    "calibrate_thresholds",
    "config_for_carriers",
    "default_adaptive_channels",
    "experiment_adaptive",
    "experiment_carrier_density",
    "experiment_channels",
    "experiment_compression",
    "experiment_file_sizes",
    "experiment_snr_sweep",
    "measure_channel_state",
    "records_to_csv",
    "run_quick_suite",
    "run_trial",
    "summarize",
    "write_results",
]
