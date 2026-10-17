import { useState } from "react";
import type { ChannelModel, Presets } from "../services/api";

interface Props {
  /** null = no simulated channel. */
  value: ChannelModel | null;
  onChange: (v: ChannelModel | null) => void;
  presets: Presets | null;
  /** Hide the enable toggle (channel always on). */
  alwaysOn?: boolean;
  compact?: boolean;
}

const CHANNEL_NAMES = ["ideal", "awgn", "quiet_room", "noisy_room", "reverberant_room", "difficult"];

/** Synthetic channel model editor (preset + SNR + optional impairments). */
export default function ChannelForm({ value, onChange, presets, alwaysOn = false, compact = false }: Props) {
  const [adv, setAdv] = useState(false);
  const names = presets ? Object.keys(presets.channels) : CHANNEL_NAMES;
  const enabled = value !== null;
  const preset = value?.preset ?? "awgn";
  const base = presets?.channels[preset];
  const set = (patch: Partial<ChannelModel>) => onChange({ ...(value ?? { preset }), ...patch });
  const num = (v: string): number | undefined => (v === "" ? undefined : Number(v));

  return (
    <div className="flex flex-col gap-3">
      {!alwaysOn && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} onChange={(e) => onChange(e.target.checked ? { preset: "awgn", snr_db: 20 } : null)} />
          Simulate a channel
          <span className="text-xs text-muted">(synthetic model, not a real acoustic measurement)</span>
        </label>
      )}
      {(enabled || alwaysOn) && (
        <>
          <div className={`grid gap-3 ${compact ? "grid-cols-2" : "grid-cols-1 sm:grid-cols-2"}`}>
            <div>
              <label className="label">Channel preset</label>
              <select className="input" value={preset} onChange={(e) => onChange({ preset: e.target.value, snr_db: presets?.channels[e.target.value]?.snr_db ?? undefined })}>
                {names.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">SNR (dB){base && base.snr_db === null && <span className="ml-1 text-muted">preset: noiseless</span>}</label>
              <input
                className="input"
                type="number"
                step={1}
                placeholder={base?.snr_db != null ? `preset (${base.snr_db})` : "none"}
                value={value?.snr_db ?? ""}
                onChange={(e) => set({ snr_db: num(e.target.value) })}
              />
            </div>
          </div>
          {!compact && (
            <>
              <button className="self-start text-xs text-accent hover:underline" type="button" onClick={() => setAdv((a) => !a)}>
                {adv ? "▾ Hide impairments" : "▸ More impairments"}
              </button>
              {adv && (
                <div className="grid grid-cols-2 gap-3 rounded-md border border-line bg-bg/40 p-3 md:grid-cols-4">
                  <Field label="Reverb RT60 (s)" ph={base?.reverb_rt60_s} value={value?.reverb_rt60_s} onChange={(v) => set({ reverb_rt60_s: v })} step={0.05} />
                  <Field label="Reverb level" ph={base?.reverb_level} value={value?.reverb_level} onChange={(v) => set({ reverb_level: v })} step={0.01} />
                  <Field label="Tilt (dB/kHz)" ph={base?.tilt_db_per_khz} value={value?.tilt_db_per_khz} onChange={(v) => set({ tilt_db_per_khz: v })} step={0.1} />
                  <Field label="Sample-rate error (ppm)" ph={base?.sample_rate_ppm} value={value?.sample_rate_ppm} onChange={(v) => set({ sample_rate_ppm: v })} step={1} />
                  <Field label="Frequency offset (Hz)" ph={base?.frequency_offset_hz} value={value?.frequency_offset_hz} onChange={(v) => set({ frequency_offset_hz: v })} step={0.5} />
                  <Field label="Timing offset (s)" ph={base?.timing_offset_s} value={value?.timing_offset_s} onChange={(v) => set({ timing_offset_s: v })} step={0.05} />
                  <Field label="Low-pass (Hz)" ph={base?.lowpass_hz} value={value?.lowpass_hz} onChange={(v) => set({ lowpass_hz: v })} step={100} />
                  <Field label="High-pass (Hz)" ph={base?.highpass_hz} value={value?.highpass_hz} onChange={(v) => set({ highpass_hz: v })} step={50} />
                  <Field label="Burst level (dB)" ph={base?.burst_level_db} value={value?.burst_level_db} onChange={(v) => set({ burst_level_db: v })} step={1} />
                  <Field label="Burst duty" ph={base?.burst_duty} value={value?.burst_duty} onChange={(v) => set({ burst_duty: v })} step={0.01} />
                  <Field label="Clip level" ph={base?.clip_level} value={value?.clip_level} onChange={(v) => set({ clip_level: v })} step={0.05} />
                  <Field label="Seed" ph={base?.seed} value={value?.seed} onChange={(v) => set({ seed: v })} step={1} />
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

function Field({
  label,
  ph,
  value,
  onChange,
  step,
}: {
  label: string;
  ph: number | null | undefined;
  value: number | null | undefined;
  onChange: (v: number | undefined) => void;
  step: number;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input
        className="input"
        type="number"
        step={step}
        placeholder={ph === null || ph === undefined ? "none" : `preset (${ph})`}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
      />
    </div>
  );
}
