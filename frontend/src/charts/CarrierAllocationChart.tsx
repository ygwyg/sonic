import { useMemo, useState } from "react";
import type { Allocation } from "../services/api";
import { roleColor } from "./theme";

interface Props {
  allocation: Allocation;
  /** Full frequency axis extent in Hz (default: sample-rate Nyquist derived from n_fft*spacing/2). */
  fMax?: number;
  label?: string;
  height?: number;
}

/**
 * Carrier allocation strip: each active carrier is a tick colored by role
 * (pilot / modulation / disabled); the guard bands are shaded.
 */
export default function CarrierAllocationChart({ allocation, fMax, label, height = 72 }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const nyquist = fMax ?? (allocation.n_fft * allocation.carrier_spacing_hz) / 2;
  const W = 1000;
  const H = height;
  const axisH = 18;
  const plotH = H - axisH;
  const x = (f: number) => (f / nyquist) * W;

  const roles = useMemo(() => {
    const set = new Map<string, number>();
    allocation.roles.forEach((r) => set.set(r, (set.get(r) ?? 0) + 1));
    return Array.from(set.entries());
  }, [allocation]);

  const fLow = allocation.frequencies_hz[0] ?? 0;
  const fHigh = allocation.frequencies_hz[allocation.frequencies_hz.length - 1] ?? nyquist;
  const barW = Math.max(0.8, (allocation.carrier_spacing_hz / nyquist) * W * 0.9);
  const ticks = Array.from({ length: 9 }, (_, i) => (nyquist * i) / 8);

  return (
    <div className="w-full">
      {label && <div className="mb-1 text-xs text-ink2">{label}</div>}
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" className="block overflow-visible" onMouseLeave={() => setHover(null)}>
        {/* guard bands */}
        <rect x={0} y={0} width={x(fLow)} height={plotH} fill="#7a8595" fillOpacity={0.12} />
        <rect x={x(fHigh)} y={0} width={W - x(fHigh)} height={plotH} fill="#7a8595" fillOpacity={0.12} />
        {/* carriers */}
        {allocation.frequencies_hz.map((f, i) => (
          <rect
            key={i}
            x={x(f) - barW / 2}
            y={hover === i ? 2 : 8}
            width={barW}
            height={hover === i ? plotH - 2 : plotH - 8}
            fill={roleColor(allocation.roles[i])}
            onMouseEnter={() => setHover(i)}
          />
        ))}
        {/* axis */}
        <line x1={0} x2={W} y1={plotH} y2={plotH} stroke="#262d38" />
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={plotH} y2={plotH + 3} stroke="#262d38" />
            <text x={x(t)} y={plotH + 13} textAnchor="middle" fontSize={10} fill="#7a8595" fontFamily="ui-monospace, monospace">
              {t >= 1000 ? `${(t / 1000).toFixed(t % 1000 ? 1 : 0)}k` : t.toFixed(0)}
            </text>
          </g>
        ))}
      </svg>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink2">
        <span className="text-muted">frequency (Hz) ·</span>
        {roles.map(([r, n]) => (
          <span key={r} className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-3 rounded-sm" style={{ background: roleColor(r) }} />
            {r} <span className="num text-muted">×{n}</span>
          </span>
        ))}
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-2 w-3 rounded-sm bg-muted/30" />
          guard <span className="num text-muted">{allocation.guard_low_hz.toFixed(0)}–{allocation.guard_high_hz.toFixed(0)} Hz edges</span>
        </span>
        {hover !== null && (
          <span className="num ml-auto text-ink">
            carrier {allocation.carriers[hover]} · {allocation.frequencies_hz[hover].toFixed(1)} Hz · {allocation.roles[hover]}
          </span>
        )}
      </div>
    </div>
  );
}
