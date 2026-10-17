/* Black-and-white SVG charts that follow the text colour. */

export function Constellation({ re, im }: { re: number[]; im: number[] }) {
  const mags = re.map((r, i) => Math.max(Math.abs(r), Math.abs(im[i]))).sort((a, b) => a - b);
  const ext = Math.max(1, (mags[Math.floor(mags.length * 0.99)] ?? 1) * 1.2);
  return (
    <svg className="fig fig-square" viewBox={`${-ext} ${-ext} ${2 * ext} ${2 * ext}`} role="img" aria-label="Received constellation">
      <line x1={-ext} x2={ext} y1={0} y2={0} className="fig-grid" />
      <line y1={-ext} y2={ext} x1={0} x2={0} className="fig-grid" />
      <g className="fig-dots">
        {re.map((r, i) => (
          <circle key={i} cx={r} cy={-im[i]} r={ext * 0.012} />
        ))}
      </g>
    </svg>
  );
}

const W = 600;
const H = 340;
const PAD = { l: 60, r: 8, t: 10, b: 30 };

export function ticks(lo: number, hi: number, target = 5): number[] {
  const raw = (hi - lo) / target;
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => (hi - lo) / s <= target) ?? 10 * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

/**
 * One line, binned to ~150 points (mean line plus a min–max band) so a few
 * hundred carriers stay readable. `xFormat` labels the x ticks.
 */
export function LineChart({ x, y, xFormat = String }: { x: number[]; y: number[]; xFormat?: (v: number) => string }) {
  if (!x.length || x.length !== y.length) return null;
  const x0 = x[0];
  const x1 = x[x.length - 1];
  const yt = ticks(Math.min(...y), Math.max(...y));
  const lo = Math.min(yt[0], ...y);
  const hi = Math.max(yt[yt.length - 1], ...y);
  const sx = (v: number) => PAD.l + ((v - x0) / (x1 - x0 || 1)) * (W - PAD.l - PAD.r);
  const sy = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo || 1)) * (H - PAD.t - PAD.b);

  const bins = Math.min(x.length, 150);
  const per = x.length / bins;
  const mean: string[] = [];
  const top: string[] = [];
  const bottom: string[] = [];
  for (let b = 0; b < bins; b++) {
    const a = Math.floor(b * per);
    const s = y.slice(a, Math.max(a + 1, Math.floor((b + 1) * per)));
    const px = sx(x[Math.min(x.length - 1, Math.floor((b + 0.5) * per))]).toFixed(1);
    mean.push(`${px},${sy(s.reduce((t, v) => t + v, 0) / s.length).toFixed(1)}`);
    top.push(`${px},${sy(Math.max(...s)).toFixed(1)}`);
    bottom.unshift(`${px},${sy(Math.min(...s)).toFixed(1)}`);
  }

  return (
    <svg className="fig" viewBox={`0 0 ${W} ${H}`} role="img">
      {yt.map((t) => (
        <g key={t}>
          <line x1={PAD.l} x2={W - PAD.r} y1={sy(t)} y2={sy(t)} className="fig-grid" />
          <text x={PAD.l - 8} y={sy(t) + 5} textAnchor="end" className="fig-label">
            {t}
          </text>
        </g>
      ))}
      {ticks(x0, x1, 4).map((t) => (
        <text key={t} x={sx(t)} y={H - 6} textAnchor="middle" className="fig-label">
          {xFormat(t)}
        </text>
      ))}
      {bins < x.length && <polygon points={[...top, ...bottom].join(" ")} className="fig-band" />}
      <polyline points={mean.join(" ")} className="fig-line" />
    </svg>
  );
}

/** Several unbinned series on shared axes; `strong` series draw solid, the rest faint. */
export function Lines({
  x,
  series,
  xFormat = String,
  height = H,
}: {
  x: number[];
  series: { y: number[]; strong?: boolean }[];
  xFormat?: (v: number) => string;
  height?: number;
}) {
  const all = series.flatMap((s) => s.y);
  if (!x.length || !all.length) return null;
  const yt = ticks(Math.min(...all), Math.max(...all), 4);
  const lo = Math.min(yt[0], ...all);
  const hi = Math.max(yt[yt.length - 1], ...all);
  const sx = (v: number) => PAD.l + ((v - x[0]) / (x[x.length - 1] - x[0] || 1)) * (W - PAD.l - PAD.r);
  const sy = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo || 1)) * (height - PAD.t - PAD.b);
  return (
    <svg className="fig" viewBox={`0 0 ${W} ${height}`} role="img">
      {yt.map((t) => (
        <g key={t}>
          <line x1={PAD.l} x2={W - PAD.r} y1={sy(t)} y2={sy(t)} className="fig-grid" />
          <text x={PAD.l - 8} y={sy(t) + 5} textAnchor="end" className="fig-label">
            {t}
          </text>
        </g>
      ))}
      {ticks(x[0], x[x.length - 1], 4).map((t) => (
        <text key={t} x={sx(t)} y={height - 6} textAnchor="middle" className="fig-label">
          {xFormat(t)}
        </text>
      ))}
      {series.map((s, i) => (
        <polyline
          key={i}
          points={s.y.map((v, j) => `${sx(x[j]).toFixed(1)},${sy(v).toFixed(1)}`).join(" ")}
          className={s.strong ? "fig-line" : "fig-line fig-faint"}
        />
      ))}
    </svg>
  );
}

/** Dots on labelled y ticks (for phase plots). */
export function Dots({
  x,
  y,
  yTicks,
  xFormat = String,
}: {
  x: number[];
  y: number[];
  yTicks: { v: number; label: string }[];
  xFormat?: (v: number) => string;
}) {
  if (!x.length) return null;
  const lo = yTicks[0].v;
  const hi = yTicks[yTicks.length - 1].v;
  const sx = (v: number) => PAD.l + ((v - x[0]) / (x[x.length - 1] - x[0] || 1)) * (W - PAD.l - PAD.r);
  const sy = (v: number) => PAD.t + 6 + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b - 12);
  return (
    <svg className="fig" viewBox={`0 0 ${W} ${H}`} role="img">
      {yTicks.map((t) => (
        <g key={t.v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={sy(t.v)} y2={sy(t.v)} className="fig-grid" />
          <text x={PAD.l - 8} y={sy(t.v) + 5} textAnchor="end" className="fig-label">
            {t.label}
          </text>
        </g>
      ))}
      {ticks(x[0], x[x.length - 1], 4).map((t) => (
        <text key={t} x={sx(t)} y={H - 6} textAnchor="middle" className="fig-label">
          {xFormat(t)}
        </text>
      ))}
      <g className="fig-dots">
        {x.map((v, i) => (
          <circle key={i} cx={sx(v)} cy={sy(y[i])} r={3} />
        ))}
      </g>
    </svg>
  );
}
