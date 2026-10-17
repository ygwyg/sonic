import type { ReactNode } from "react";

interface Props {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: string;
  tone?: "default" | "good" | "warn" | "bad";
}

const TONES = {
  default: "text-ink",
  good: "text-good",
  warn: "text-warn",
  bad: "text-bad",
};

/** A compact labelled numeric readout; values are monospace. */
export default function NumberStat({ label, value, unit, hint, tone = "default" }: Props) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-bg/60 px-3 py-2">
      <div className="truncate text-[11px] uppercase tracking-wider text-muted" title={hint}>
        {label}
      </div>
      <div className={`num truncate text-base ${TONES[tone]}`}>
        {value}
        {unit && <span className="ml-1 text-xs text-muted">{unit}</span>}
      </div>
    </div>
  );
}

export function StatGrid({ children, cols = 4 }: { children: ReactNode; cols?: 2 | 3 | 4 | 5 | 6 }) {
  const cls = {
    2: "grid-cols-2",
    3: "grid-cols-2 sm:grid-cols-3",
    4: "grid-cols-2 sm:grid-cols-4",
    5: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5",
    6: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-6",
  }[cols];
  return <div className={`grid gap-2 ${cls}`}>{children}</div>;
}
