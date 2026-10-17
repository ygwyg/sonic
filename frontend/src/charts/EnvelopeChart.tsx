import { useMemo } from "react";
import { Area, CartesianGrid, ComposedChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Section, WaveformAnalysis } from "../services/api";
import { downsample, sectionLabel } from "../services/format";
import { SECTION_COLORS, SERIES, TOOLTIP_STYLE } from "./theme";

interface Props {
  waveform: WaveformAnalysis;
  sections?: Section[] | null;
  height?: number;
  color?: string;
  maxPoints?: number;
  showLegend?: boolean;
}

/** Time-domain min/max envelope with optional colored section bands. */
export default function EnvelopeChart({ waveform, sections, height = 220, color = SERIES[0], maxPoints = 1500, showLegend = true }: Props) {
  const sr = waveform.sample_rate || 1;
  const rows = useMemo(() => {
    const { index, min, max } = waveform.envelope;
    const n = Math.min(index.length, min.length, max.length);
    const all = Array.from({ length: n }, (_, i) => ({ t: index[i] / sr, range: [min[i], max[i]] as [number, number] }));
    return downsample(all, maxPoints);
  }, [waveform, sr, maxPoints]);

  const peak = Math.max(0.05, Math.abs(waveform.peak || 1));
  const secs = (sections ?? []).filter((s) => s.end > s.start);

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 4, bottom: 18 }}>
          <CartesianGrid strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            domain={[0, waveform.duration_s]}
            tickFormatter={(v: number) => v.toFixed(2)}
            label={{ value: "time (s)", position: "insideBottom", offset: -10, fill: "#7a8595", fontSize: 11 }}
            stroke="#262d38"
          />
          <YAxis
            domain={[-peak, peak]}
            tickFormatter={(v: number) => v.toFixed(2)}
            width={52}
            label={{ value: "amplitude", angle: -90, position: "insideLeft", offset: 12, fill: "#7a8595", fontSize: 11, style: { textAnchor: "middle" } }}
            stroke="#262d38"
          />
          {secs.map((s) => (
            <ReferenceArea
              key={`${s.name}-${s.start}`}
              x1={s.start / sr}
              x2={s.end / sr}
              fill={SECTION_COLORS[s.name] ?? "#7a8595"}
              fillOpacity={0.12}
              stroke={SECTION_COLORS[s.name] ?? "#7a8595"}
              strokeOpacity={0.35}
              ifOverflow="hidden"
            />
          ))}
          <Tooltip
            {...TOOLTIP_STYLE}
            formatter={(v: [number, number]) => [`${v[0].toFixed(3)} … ${v[1].toFixed(3)}`, "min … max"]}
            labelFormatter={(v: number) => `t = ${v.toFixed(4)} s`}
          />
          <Area dataKey="range" stroke={color} fill={color} fillOpacity={0.5} strokeWidth={1} isAnimationActive={false} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
      {showLegend && secs.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink2">
          {secs.map((s) => (
            <span key={`${s.name}-${s.start}`} className="inline-flex items-center gap-1">
              <span className="inline-block h-2 w-3 rounded-sm" style={{ background: SECTION_COLORS[s.name] ?? "#7a8595" }} />
              {sectionLabel(s.name)} <span className="num text-muted">{((s.end - s.start) / sr).toFixed(2)}s</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
