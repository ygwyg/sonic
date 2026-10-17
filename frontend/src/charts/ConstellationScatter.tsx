import { useEffect, useRef } from "react";
import type { Constellation } from "../services/api";
import { SERIES } from "./theme";

interface Props {
  points: Constellation;
  title?: string;
  color?: string;
  size?: number;
  /** Max points drawn (randomly thinned beyond this). */
  maxPoints?: number;
}

/** I/Q constellation scatter on a canvas (fast for thousands of points). */
export default function ConstellationScatter({ points, title, color = SERIES[0], size = 240, maxPoints = 6000 }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const n = Math.min(points.re.length, points.im.length);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#0b0e12";
    ctx.fillRect(0, 0, size, size);

    // Determine scale from the data (robust to outliers: 99th percentile).
    const mags: number[] = [];
    for (let i = 0; i < n; i++) mags.push(Math.max(Math.abs(points.re[i]), Math.abs(points.im[i])));
    mags.sort((a, b) => a - b);
    const p99 = mags.length ? mags[Math.floor(mags.length * 0.99)] : 1;
    const lim = Math.max(1.2, p99 * 1.15) || 1.5;
    const pad = 22;
    const span = size - pad * 2;
    const sx = (v: number) => pad + ((v + lim) / (2 * lim)) * span;
    const sy = (v: number) => pad + ((lim - v) / (2 * lim)) * span;

    // grid + axes
    ctx.strokeStyle = "#262d38";
    ctx.lineWidth = 1;
    for (const g of [-1, 0, 1]) {
      ctx.beginPath();
      ctx.moveTo(sx(g), pad);
      ctx.lineTo(sx(g), size - pad);
      ctx.moveTo(pad, sy(g));
      ctx.lineTo(size - pad, sy(g));
      ctx.stroke();
    }
    ctx.strokeStyle = "#3a4350";
    ctx.strokeRect(pad, pad, span, span);
    ctx.fillStyle = "#7a8595";
    ctx.font = "10px ui-monospace, monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillText("I (in-phase)", size / 2, size - pad + 6);
    ctx.fillText(`${lim.toFixed(1)}`, size - pad, size - pad + 6);
    ctx.fillText(`-${lim.toFixed(1)}`, pad, size - pad + 6);
    ctx.save();
    ctx.translate(8, size / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("Q (quadrature)", 0, 0);
    ctx.restore();

    // points
    const step = n > maxPoints ? n / maxPoints : 1;
    ctx.fillStyle = color;
    ctx.globalAlpha = n > 1500 ? 0.45 : 0.85;
    const r = n > 1500 ? 1.3 : 2.2;
    for (let k = 0; k < Math.min(n, maxPoints); k++) {
      const i = Math.floor(k * step);
      const x = sx(points.re[i]);
      const y = sy(points.im[i]);
      if (x < pad || x > size - pad || y < pad || y > size - pad) continue;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }, [points, n, color, size, maxPoints]);

  return (
    <div className="inline-flex flex-col items-center">
      {title && <div className="mb-1 text-xs text-ink2">{title}</div>}
      <canvas ref={ref} style={{ width: size, height: size, maxWidth: "100%" }} className="rounded border border-line" />
      <div className="num mt-1 text-[11px] text-muted">{n.toLocaleString()} symbols</div>
    </div>
  );
}
