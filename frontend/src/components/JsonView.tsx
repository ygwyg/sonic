import { useState } from "react";

interface Props {
  data: unknown;
  name?: string;
  /** Depth at which nodes start collapsed. */
  collapseDepth?: number;
  depth?: number;
}

/** Collapsible JSON tree. Long arrays are summarised rather than rendered. */
export default function JsonView({ data, name, collapseDepth = 1, depth = 0 }: Props) {
  const isObj = data !== null && typeof data === "object";
  const [open, setOpen] = useState(depth < collapseDepth);

  if (!isObj) {
    return (
      <div className="num flex gap-2 text-xs" style={{ paddingLeft: depth * 12 }}>
        {name !== undefined && <span className="text-muted">{name}:</span>}
        <span style={{ color: typeof data === "string" ? "var(--s3)" : "var(--ink)" }}>{formatScalar(data)}</span>
      </div>
    );
  }

  const isArr = Array.isArray(data);
  const entries = isArr ? (data as unknown[]).map((v, i) => [String(i), v] as const) : Object.entries(data as Record<string, unknown>);
  const summary = isArr ? `[${entries.length}]` : `{${entries.length}}`;
  const numericArray = isArr && entries.length > 24 && entries.every(([, v]) => typeof v === "number");

  return (
    <div className="num text-xs" style={{ paddingLeft: depth * 12 }}>
      <button className="flex items-center gap-1 text-ink2 hover:text-ink" onClick={() => setOpen((o) => !o)}>
        <span className="inline-block w-3 text-muted">{open ? "▾" : "▸"}</span>
        {name !== undefined && <span className="text-muted">{name}:</span>}
        <span className="text-muted">{summary}</span>
      </button>
      {open && (
        <div>
          {numericArray ? (
            <div className="pl-4 text-muted">
              number[{entries.length}] (min {fmtNum(Math.min(...(data as number[])))}, max {fmtNum(Math.max(...(data as number[])))})
            </div>
          ) : (
            entries.slice(0, 200).map(([k, v]) => <JsonView key={k} name={k} data={v} depth={depth + 1} collapseDepth={collapseDepth} />)
          )}
          {!numericArray && entries.length > 200 && <div className="pl-4 text-muted">… {entries.length - 200} more</div>}
        </div>
      )}
    </div>
  );
}

function formatScalar(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return fmtNum(v);
  if (typeof v === "string") return v.length > 120 ? `"${v.slice(0, 117)}…"` : `"${v}"`;
  return String(v);
}

function fmtNum(v: number): string {
  if (!Number.isFinite(v)) return "—";
  if (Number.isInteger(v)) return String(v);
  return Math.abs(v) < 0.001 || Math.abs(v) > 1e6 ? v.toExponential(3) : v.toFixed(4);
}
