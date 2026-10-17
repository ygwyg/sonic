/* Two small black-and-white figures drawn as SVG so they follow the text colour. */

export function Constellation({ re, im }: { re: number[]; im: number[] }) {
  const mags = re.map((r, i) => Math.max(Math.abs(r), Math.abs(im[i]))).sort((a, b) => a - b);
  const ext = Math.max(1, (mags[Math.floor(mags.length * 0.99)] ?? 1) * 1.2);
  return (
    <svg className="fig fig-square" viewBox={`${-ext} ${-ext} ${2 * ext} ${2 * ext}`} role="img" aria-label="Constellation of received symbols">
      <line x1={-ext} x2={ext} y1={0} y2={0} className="fig-axis" />
      <line y1={-ext} y2={ext} x1={0} x2={0} className="fig-axis" />
      <g className="fig-dots">
        {re.map((r, i) => (
          <circle key={i} cx={r} cy={-im[i]} r={ext * 0.012} />
        ))}
      </g>
    </svg>
  );
}

const W = 600;
const H = 260;
const PAD = { l: 34, r: 8, t: 10, b: 28 };

export function SnrByFrequency({ hz, db }: { hz: number[]; db: number[] }) {
  if (!hz.length || hz.length !== db.length) return null;
  const f0 = hz[0];
  const f1 = hz[hz.length - 1];
  const top = Math.max(40, Math.ceil(Math.max(...db) / 20) * 20);
  const x = (f: number) => PAD.l + ((f - f0) / (f1 - f0 || 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - Math.max(0, Math.min(top, v)) / top) * (H - PAD.t - PAD.b);

  // bin to roughly one point per 4 px: mean line plus a min–max band
  const bins = Math.min(hz.length, 150);
  const per = hz.length / bins;
  const mean: string[] = [];
  const hi: string[] = [];
  const lo: string[] = [];
  for (let b = 0; b < bins; b++) {
    const s = db.slice(Math.floor(b * per), Math.max(Math.floor(b * per) + 1, Math.floor((b + 1) * per)));
    const fx = x(hz[Math.min(hz.length - 1, Math.floor((b + 0.5) * per))]).toFixed(1);
    mean.push(`${fx},${y(s.reduce((a, v) => a + v, 0) / s.length).toFixed(1)}`);
    hi.push(`${fx},${y(Math.max(...s)).toFixed(1)}`);
    lo.unshift(`${fx},${y(Math.min(...s)).toFixed(1)}`);
  }
  const kTicks: number[] = [];
  const step = f1 - f0 > 6000 ? 2000 : 1000;
  for (let k = Math.ceil(f0 / step) * step; k <= f1; k += step) kTicks.push(k);
  const dbStep = top > 50 ? 20 : 10;
  const dbTicks = Array.from({ length: Math.floor(top / dbStep) + 1 }, (_, i) => i * dbStep);

  return (
    <svg className="fig" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Signal quality by frequency">
      {dbTicks.map((t) => (
        <g key={t}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="fig-grid" />
          <text x={PAD.l - 6} y={y(t) + 4} textAnchor="end" className="fig-label">
            {t}
          </text>
        </g>
      ))}
      {kTicks.map((k) => (
        <text key={k} x={x(k)} y={H - 8} textAnchor="middle" className="fig-label">
          {k / 1000} kHz
        </text>
      ))}
      <polygon points={[...hi, ...lo].join(" ")} className="fig-band" />
      <polyline points={mean.join(" ")} className="fig-line" />
      <text x={PAD.l + 4} y={PAD.t + 12} className="fig-label">
        dB
      </text>
    </svg>
  );
}
