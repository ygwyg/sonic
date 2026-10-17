import { CartesianGrid, ErrorBar, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SERIES, TOOLTIP_STYLE } from "./theme";

export interface LineSeries {
  key: string;
  name: string;
  color?: string;
  /** Key holding the ± error (ci95) for this series. */
  errorKey?: string;
  dashed?: boolean;
  dot?: boolean;
}

interface Props {
  data: Record<string, unknown>[];
  xKey: string;
  series: LineSeries[];
  xLabel: string;
  yLabel: string;
  height?: number;
  yScale?: "linear" | "log";
  xScale?: "linear" | "log";
  yDomain?: [number | string, number | string];
  xDomain?: [number | string, number | string];
  xType?: "number" | "category";
  yFormatter?: (v: number) => string;
  xFormatter?: (v: number) => string;
  connectNulls?: boolean;
}

/** Distinct x values, used as explicit ticks on a log x axis. */
function logTicks(data: Record<string, unknown>[], xKey: string): number[] {
  const xs = new Set<number>();
  for (const r of data) {
    const v = r[xKey];
    if (typeof v === "number" && v > 0) xs.add(v);
  }
  return Array.from(xs).sort((a, b) => a - b);
}

/** Generic multi-series line chart with optional ±ci95 error bars. */
export default function LineSeriesChart({
  data,
  xKey,
  series,
  xLabel,
  yLabel,
  height = 260,
  yScale = "linear",
  xScale = "linear",
  yDomain,
  xDomain,
  xType = "number",
  yFormatter = (v) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(2)),
  xFormatter,
  connectNulls = true,
}: Props) {
  const yd = yDomain ?? (yScale === "log" ? ["auto", "auto"] : [0, "auto"]);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 20 }}>
        <CartesianGrid strokeDasharray="2 4" />
        <XAxis
          dataKey={xKey}
          type={xType}
          scale={xType === "number" ? xScale : undefined}
          ticks={xScale === "log" && xType === "number" ? logTicks(data, xKey) : undefined}
          domain={xDomain ?? (xType === "number" ? ["dataMin", "dataMax"] : undefined)}
          tickFormatter={xFormatter}
          label={{ value: xLabel, position: "insideBottom", offset: -12, fill: "#7a8595", fontSize: 11 }}
          stroke="#262d38"
          allowDuplicatedCategory={false}
        />
        <YAxis
          width={60}
          scale={yScale}
          domain={yd}
          allowDataOverflow={yScale === "log"}
          tickFormatter={yFormatter}
          label={{ value: yLabel, angle: -90, position: "insideLeft", offset: 12, fill: "#7a8595", fontSize: 11, style: { textAnchor: "middle" } }}
          stroke="#262d38"
        />
        <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => (typeof v === "number" ? yFormatter(v) : "—")} />
        {series.length > 1 && <Legend verticalAlign="top" align="right" wrapperStyle={{ fontSize: 11, paddingBottom: 6 }} />}
        {series.map((s, i) => (
          <Line
            key={s.key}
            dataKey={s.key}
            name={s.name}
            stroke={s.color ?? SERIES[i % SERIES.length]}
            strokeWidth={2}
            strokeDasharray={s.dashed ? "6 4" : undefined}
            dot={s.dot === false ? false : { r: 3, strokeWidth: 0, fill: s.color ?? SERIES[i % SERIES.length] }}
            activeDot={{ r: 5 }}
            isAnimationActive={false}
            connectNulls={connectNulls}
          >
            {s.errorKey && <ErrorBar dataKey={s.errorKey} width={4} strokeWidth={1} stroke={s.color ?? SERIES[i % SERIES.length]} direction="y" />}
          </Line>
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
