import { Bar, BarChart, CartesianGrid, ErrorBar, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SERIES, TOOLTIP_STYLE } from "./theme";

export interface BarSeries {
  key: string;
  name: string;
  color?: string;
  errorKey?: string;
}

interface Props {
  data: Record<string, unknown>[];
  xKey: string;
  series: BarSeries[];
  xLabel: string;
  yLabel: string;
  height?: number;
  yFormatter?: (v: number) => string;
  yDomain?: [number | string, number | string];
  yScale?: "linear" | "log";
}

/** Grouped bar chart (one bar per series per category) with optional error bars. */
export default function GroupedBarChart({
  data,
  xKey,
  series,
  xLabel,
  yLabel,
  height = 260,
  yFormatter = (v) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(2)),
  yDomain,
  yScale = "linear",
}: Props) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 20 }} barCategoryGap="20%" barGap={2}>
        <CartesianGrid strokeDasharray="2 4" vertical={false} />
        <XAxis
          dataKey={xKey}
          type="category"
          label={{ value: xLabel, position: "insideBottom", offset: -12, fill: "#7a8595", fontSize: 11 }}
          stroke="#262d38"
          interval={0}
          tick={{ fontSize: 10 }}
        />
        <YAxis
          width={60}
          scale={yScale}
          domain={yDomain ?? (yScale === "log" ? ["auto", "auto"] : [0, "auto"])}
          allowDataOverflow={yScale === "log"}
          tickFormatter={yFormatter}
          label={{ value: yLabel, angle: -90, position: "insideLeft", offset: 12, fill: "#7a8595", fontSize: 11, style: { textAnchor: "middle" } }}
          stroke="#262d38"
        />
        <Tooltip {...TOOLTIP_STYLE} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v: number) => (typeof v === "number" ? yFormatter(v) : "—")} />
        {series.length > 1 && <Legend verticalAlign="top" align="right" wrapperStyle={{ fontSize: 11, paddingBottom: 6 }} />}
        {series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color ?? SERIES[i % SERIES.length]} radius={[3, 3, 0, 0]} isAnimationActive={false} maxBarSize={48}>
            {s.errorKey && <ErrorBar dataKey={s.errorKey} width={4} strokeWidth={1} stroke="#e8ebef" direction="y" />}
          </Bar>
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
