import { useMemo } from "react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SpectrumAnalysis } from "../services/api";
import { bucketMinMax } from "../services/format";
import { SERIES, TOOLTIP_STYLE } from "./theme";

interface Props {
  spectrum: SpectrumAnalysis;
  /** Optional [low, high] band in Hz to highlight. */
  band?: [number, number] | null;
  height?: number;
  color?: string;
  maxPoints?: number;
}

/** Averaged power spectrum (dB vs Hz). */
export default function SpectrumChart({ spectrum, band, height = 220, color = SERIES[0], maxPoints = 1600 }: Props) {
  const rows = useMemo(() => bucketMinMax(spectrum.frequency_hz, spectrum.power_db, maxPoints), [spectrum, maxPoints]);
  const fMax = spectrum.frequency_hz.length ? spectrum.frequency_hz[spectrum.frequency_hz.length - 1] : 1;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rows} margin={{ top: 8, right: 12, left: 4, bottom: 18 }}>
        <CartesianGrid strokeDasharray="2 4" />
        <XAxis
          dataKey="x"
          type="number"
          domain={[0, fMax]}
          tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`}
          label={{ value: "frequency (Hz)", position: "insideBottom", offset: -10, fill: "#7a8595", fontSize: 11 }}
          stroke="#262d38"
        />
        <YAxis
          width={48}
          domain={["auto", "auto"]}
          tickFormatter={(v: number) => v.toFixed(0)}
          label={{ value: "power (dB)", angle: -90, position: "insideLeft", offset: 12, fill: "#7a8595", fontSize: 11, style: { textAnchor: "middle" } }}
          stroke="#262d38"
        />
        {band && <ReferenceArea x1={band[0]} x2={band[1]} fill={SERIES[2]} fillOpacity={0.08} stroke={SERIES[2]} strokeOpacity={0.3} />}
        <Tooltip
          {...TOOLTIP_STYLE}
          formatter={(v: number) => [`${v.toFixed(1)} dB`, "power"]}
          labelFormatter={(v: number) => `${v.toFixed(0)} Hz`}
        />
        <Line dataKey="y" stroke={color} dot={false} strokeWidth={1.25} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
