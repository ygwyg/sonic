import numpy as np

from sonic.adaptive import (
    ChannelStateReport,
    apply_plan,
    band_effective_snr,
    best_fixed_config,
    map_snr_to_config,
    plan_bit_loading,
)
from sonic.benchmarking import measure_channel_state, run_trial
from sonic.channel import ChannelConfig
from sonic.config import OFDMConfig


def test_channel_state_report_bytes():
    r = ChannelStateReport(n_bands=4, band_snr_db=[3.2, 10.0, 25.5, 40.0])
    raw = r.to_bytes()
    assert len(raw) == r.overhead_bytes == 5
    back = ChannelStateReport.from_bytes(raw)
    assert back.band_snr_db == [3.0, 10.0, 25.5, 40.0]


def test_band_effective_snr_percentile():
    snr = np.concatenate([np.full(50, 20.0), np.full(50, 5.0)])
    eff = band_effective_snr(snr, 2)
    assert eff.tolist() == [20.0, 5.0]


def test_plan_disables_bad_bands_and_loads_good_ones():
    cfg = OFDMConfig()
    n = len(cfg.data_carriers)
    snr = np.linspace(30, -5, n)  # strong tilt: great at low frequencies, dead at the top
    plan = plan_bit_loading(cfg, snr, n_bands=8, margin_db=1.0)
    mods = plan.band_modulations
    assert mods[0] in ("64qam", "256qam")
    assert mods[-1] is None
    assert plan.expected_info_bitrate_bps > 0
    new = apply_plan(cfg, plan)
    assert new.band_modulations == tuple(mods)
    assert new.code_rate == plan.code_rate
    fixed, desc = best_fixed_config(cfg, snr)
    assert fixed.band_modulations == ()
    assert fixed.info_bitrate <= plan.expected_info_bitrate_bps


def test_plan_flat_channel_matches_fixed():
    cfg = OFDMConfig()
    snr = np.full(len(cfg.data_carriers), 20.0)
    plan = plan_bit_loading(cfg, snr, n_bands=4)
    assert len(set(plan.band_modulations)) == 1
    fixed, _ = best_fixed_config(cfg, snr)
    assert fixed.modulation == plan.band_modulations[0]


def test_map_snr_interpolates():
    cfg = OFDMConfig()
    out = map_snr_to_config(cfg, [10.0, 20.0], [2000.0, 10000.0])
    assert out.size == len(cfg.data_carriers)
    assert out[0] < out[-1]


def test_probe_and_adaptive_transmission_on_tilted_channel():
    cfg = OFDMConfig()
    ch = ChannelConfig(name="tilt", snr_db=26.0, tilt_db_per_khz=-3.0)
    report, info = measure_channel_state(cfg, ch)
    assert info["probe_success"]
    assert report.band_snr_db[0] > report.band_snr_db[-1]
    plan = plan_bit_loading(cfg, np.array(report.carrier_snr_db), n_bands=8)
    acfg = apply_plan(cfg, plan)
    rec = run_trial(b"adaptive payload " * 100, acfg, ch, compression="none")
    assert rec["success"], rec["error"]
    assert rec["net_bitrate_bps"] > cfg.with_modulation("qpsk", "1/2").info_bitrate * 0.5
