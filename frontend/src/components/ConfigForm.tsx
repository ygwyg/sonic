import { useState } from "react";
import type { ConfigModel, Presets } from "../services/api";
import { fmtHz } from "../services/format";

interface Props {
  value: ConfigModel;
  onChange: (v: ConfigModel) => void;
  presets: Presets | null;
  /** Show the advanced section expanded initially. */
  advancedOpen?: boolean;
}

const N_FFT_OPTIONS = [256, 512, 1024, 2048, 4096, 8192];

/** OFDM configuration editor. Fields left blank fall back to the preset. */
export default function ConfigForm({ value, onChange, presets, advancedOpen = false }: Props) {
  const [adv, setAdv] = useState(advancedOpen);
  const presetNames = presets ? Object.keys(presets.ofdm) : ["default", "audioqr", "robust", "fast", "ultrasonic"];
  const base = presets?.ofdm[value.preset ?? "default"];
  const set = (patch: Partial<ConfigModel>) => onChange({ ...value, ...patch });
  const sr = value.sample_rate ?? base?.sample_rate ?? 48000;
  const fLow = value.f_low ?? base?.f_low ?? 2000;
  const fHigh = value.f_high ?? base?.f_high ?? 10000;
  const nyq = sr / 2;

  const num = (v: string): number | undefined => (v === "" ? undefined : Number(v));

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <label className="label">Preset</label>
          <select
            className="input"
            value={value.preset ?? "default"}
            onChange={(e) =>
              // Switching preset clears overrides so the preset's own values apply.
              onChange({ preset: e.target.value })
            }
          >
            {presetNames.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Modulation</label>
          <select className="input" value={value.modulation ?? ""} onChange={(e) => set({ modulation: e.target.value || undefined, band_modulations: undefined })}>
            <option value="">preset ({base?.modulation ?? "—"})</option>
            {(presets?.modulations ?? ["bpsk", "qpsk", "16qam", "64qam", "256qam"]).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Code rate</label>
          <select className="input" value={value.code_rate ?? ""} onChange={(e) => set({ code_rate: e.target.value || undefined })}>
            <option value="">preset ({base?.code_rate ?? "—"})</option>
            {(presets?.code_rates ?? ["1/2", "2/3", "3/4"]).map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
      </div>

      <button className="self-start text-xs text-accent hover:underline" onClick={() => setAdv((a) => !a)} type="button">
        {adv ? "▾ Hide advanced" : "▸ Advanced OFDM parameters"}
      </button>

      {adv && (
        <div className="grid grid-cols-1 gap-3 rounded-md border border-line bg-bg/40 p-3 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label className="label">FFT size (n_fft)</label>
            <select className="input" value={value.n_fft ?? ""} onChange={(e) => set({ n_fft: num(e.target.value) })}>
              <option value="">preset ({base?.n_fft ?? "—"})</option>
              {N_FFT_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Cyclic prefix (cp_len, samples)</label>
            <input
              className="input"
              type="number"
              min={0}
              step={16}
              placeholder={`preset (${base?.cp_len ?? "—"})`}
              value={value.cp_len ?? ""}
              onChange={(e) => set({ cp_len: num(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Pilot spacing (carriers)</label>
            <input
              className="input"
              type="number"
              min={2}
              max={64}
              placeholder={`preset (${base?.pilot_spacing ?? "—"})`}
              value={value.pilot_spacing ?? ""}
              onChange={(e) => set({ pilot_spacing: num(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">
              Low band edge <span className="num text-ink">{fmtHz(fLow)}</span>
            </label>
            <input
              type="range"
              className="range"
              min={100}
              max={Math.max(200, Math.min(nyq - 200, fHigh - 100))}
              step={50}
              value={fLow}
              onChange={(e) => set({ f_low: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">
              High band edge <span className="num text-ink">{fmtHz(fHigh)}</span>
            </label>
            <input
              type="range"
              className="range"
              min={Math.min(nyq, fLow + 100)}
              max={nyq}
              step={50}
              value={fHigh}
              onChange={(e) => set({ f_high: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Packet size (bytes)</label>
            <input
              className="input"
              type="number"
              min={16}
              max={4096}
              step={16}
              placeholder={`preset (${base?.packet_size ?? "—"})`}
              value={value.packet_size ?? ""}
              onChange={(e) => set({ packet_size: num(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Training symbols</label>
            <input
              className="input"
              type="number"
              min={1}
              max={8}
              placeholder={`preset (${base?.n_training ?? "—"})`}
              value={value.n_training ?? ""}
              onChange={(e) => set({ n_training: num(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Sample rate (Hz)</label>
            <select className="input" value={value.sample_rate ?? ""} onChange={(e) => set({ sample_rate: num(e.target.value) })}>
              <option value="">preset ({base?.sample_rate ?? "—"})</option>
              {[22050, 44100, 48000, 96000].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button className="btn" type="button" onClick={() => onChange({ preset: value.preset })}>
              Reset overrides
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
