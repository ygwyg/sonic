/* Number formatting helpers. Null/undefined/NaN always render as an em dash;
 * nothing here invents a value. */

export const DASH = "—";

export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

export function fmt(v: unknown, digits = 2): string {
  if (!isNum(v)) return DASH;
  return v.toFixed(digits);
}

export function fmtInt(v: unknown): string {
  if (!isNum(v)) return DASH;
  return Math.round(v).toLocaleString();
}

export function fmtHz(v: unknown, digits = 0): string {
  if (!isNum(v)) return DASH;
  if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(Math.max(digits, 2))} kHz`;
  return `${v.toFixed(digits)} Hz`;
}

export function fmtBps(v: unknown): string {
  if (!isNum(v)) return DASH;
  if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(2)} kbit/s`;
  return `${v.toFixed(0)} bit/s`;
}

export function fmtS(v: unknown, digits = 2): string {
  if (!isNum(v)) return DASH;
  if (v < 1) return `${(v * 1000).toFixed(0)} ms`;
  return `${v.toFixed(digits)} s`;
}

export function fmtDb(v: unknown, digits = 1): string {
  if (!isNum(v)) return DASH;
  return `${v.toFixed(digits)} dB`;
}

export function fmtPct(v: unknown, digits = 1): string {
  if (!isNum(v)) return DASH;
  return `${(v * 100).toFixed(digits)} %`;
}

export function fmtSci(v: unknown): string {
  if (!isNum(v)) return DASH;
  if (v === 0) return "0";
  return v.toExponential(2);
}

export function shortHash(h: string | null | undefined, n = 12): string {
  if (!h) return DASH;
  return `${h.slice(0, n)}…`;
}

/** Evenly downsample a numeric array to at most `max` points (keeps endpoints). */
export function downsample<T>(arr: T[], max: number): T[] {
  if (arr.length <= max) return arr;
  const step = (arr.length - 1) / (max - 1);
  const out: T[] = [];
  for (let i = 0; i < max; i++) out.push(arr[Math.round(i * step)]);
  return out;
}

/** Downsample paired x/y arrays into recharts rows, min/max preserving per bucket. */
export function bucketMinMax(x: number[], y: number[], max: number): { x: number; y: number }[] {
  const n = Math.min(x.length, y.length);
  if (n <= max) return Array.from({ length: n }, (_, i) => ({ x: x[i], y: y[i] }));
  const buckets = Math.floor(max / 2);
  const size = n / buckets;
  const out: { x: number; y: number }[] = [];
  for (let b = 0; b < buckets; b++) {
    const s = Math.floor(b * size);
    const e = Math.min(n, Math.floor((b + 1) * size));
    let iMin = s;
    let iMax = s;
    for (let i = s; i < e; i++) {
      if (y[i] < y[iMin]) iMin = i;
      if (y[i] > y[iMax]) iMax = i;
    }
    const first = Math.min(iMin, iMax);
    const second = Math.max(iMin, iMax);
    out.push({ x: x[first], y: y[first] });
    if (second !== first) out.push({ x: x[second], y: y[second] });
  }
  return out;
}

export function sectionLabel(name: string): string {
  return name.replace(/_/g, " ");
}
