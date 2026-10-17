import { useEffect, useRef, useState } from "react";
import type { SpectrogramAnalysis } from "../services/api";
import { viridis } from "./theme";

interface Props {
  spectrogram: SpectrogramAnalysis;
  height?: number;
}

const ML = 56; // left margin (frequency axis)
const MB = 34; // bottom margin (time axis)
const MR = 54; // right margin (colorbar)
const MT = 8;

/** Spectrogram heatmap drawn on a canvas (rows = frequency, cols = time). */
export default function SpectrogramCanvas({ spectrogram, height = 260 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<{ x: number; y: number; t: number; f: number; db: number } | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = Math.floor(entries[0].contentRect.width);
      if (w > 0) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#0b0e12";
    ctx.fillRect(0, 0, width, height);

    const { db, time_s, frequency_hz, db_min, db_max } = spectrogram;
    const nf = db.length;
    const nt = nf ? db[0].length : 0;
    const pw = Math.max(1, width - ML - MR);
    const ph = Math.max(1, height - MT - MB);
    if (!nf || !nt) return;

    // Render at data resolution then scale up (nearest neighbour).
    const img = new OffscreenOrFallbackCanvas(nt, nf);
    const ictx = img.getContext();
    const data = ictx.createImageData(nt, nf);
    const range = Math.max(1e-9, db_max - db_min);
    for (let fi = 0; fi < nf; fi++) {
      const row = db[fi];
      const y = nf - 1 - fi; // low frequency at the bottom
      for (let ti = 0; ti < nt; ti++) {
        const t = (row[ti] - db_min) / range;
        const [r, g, b] = viridis(t);
        const o = (y * nt + ti) * 4;
        data.data[o] = r;
        data.data[o + 1] = g;
        data.data[o + 2] = b;
        data.data[o + 3] = 255;
      }
    }
    ictx.putImageData(data, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img.element, ML, MT, pw, ph);

    // Axes
    ctx.strokeStyle = "#262d38";
    ctx.fillStyle = "#7a8595";
    ctx.font = "11px ui-monospace, monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const tMax = time_s[nt - 1] ?? 0;
    const nTicks = Math.max(2, Math.min(8, Math.floor(pw / 90)));
    for (let i = 0; i <= nTicks; i++) {
      const x = ML + (pw * i) / nTicks;
      const t = (tMax * i) / nTicks;
      ctx.beginPath();
      ctx.moveTo(x, MT + ph);
      ctx.lineTo(x, MT + ph + 4);
      ctx.stroke();
      ctx.fillText(t.toFixed(2), x, MT + ph + 6);
    }
    ctx.fillText("time (s)", ML + pw / 2, MT + ph + 20);

    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    const fMin = frequency_hz[0] ?? 0;
    const fMax = frequency_hz[nf - 1] ?? 1;
    const nF = Math.max(2, Math.min(8, Math.floor(ph / 36)));
    for (let i = 0; i <= nF; i++) {
      const y = MT + ph - (ph * i) / nF;
      const f = fMin + ((fMax - fMin) * i) / nF;
      ctx.beginPath();
      ctx.moveTo(ML - 4, y);
      ctx.lineTo(ML, y);
      ctx.stroke();
      ctx.fillText(f >= 1000 ? `${(f / 1000).toFixed(1)}k` : f.toFixed(0), ML - 6, y);
    }
    ctx.save();
    ctx.translate(12, MT + ph / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "center";
    ctx.fillText("frequency (Hz)", 0, 0);
    ctx.restore();

    // Colorbar
    const cbx = ML + pw + 10;
    const cbw = 10;
    for (let i = 0; i < ph; i++) {
      const [r, g, b] = viridis(1 - i / ph);
      ctx.fillStyle = `rgb(${r | 0},${g | 0},${b | 0})`;
      ctx.fillRect(cbx, MT + i, cbw, 1);
    }
    ctx.fillStyle = "#7a8595";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText(`${db_max.toFixed(0)}`, cbx + cbw + 3, MT);
    ctx.textBaseline = "bottom";
    ctx.fillText(`${db_min.toFixed(0)}`, cbx + cbw + 3, MT + ph);
    ctx.textBaseline = "middle";
    ctx.fillText("dB", cbx + cbw + 3, MT + ph / 2);
  }, [spectrogram, width, height]);

  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const pw = width - ML - MR;
    const ph = height - MT - MB;
    const { db, time_s, frequency_hz } = spectrogram;
    const nf = db.length;
    const nt = nf ? db[0].length : 0;
    if (x < ML || x > ML + pw || y < MT || y > MT + ph || !nf || !nt) {
      setHover(null);
      return;
    }
    const ti = Math.min(nt - 1, Math.floor(((x - ML) / pw) * nt));
    const fi = Math.min(nf - 1, Math.floor(((MT + ph - y) / ph) * nf));
    setHover({ x, y, t: time_s[ti], f: frequency_hz[fi], db: db[fi][ti] });
  };

  return (
    <div ref={wrapRef} className="relative w-full">
      <canvas ref={canvasRef} style={{ width, height, display: "block" }} onMouseMove={onMove} onMouseLeave={() => setHover(null)} />
      {hover && (
        <div
          className="num pointer-events-none absolute rounded border border-line bg-panel2 px-2 py-1 text-[11px] text-ink"
          style={{ left: Math.min(width - 150, hover.x + 12), top: Math.max(0, hover.y - 36) }}
        >
          t {hover.t.toFixed(3)} s · f {hover.f.toFixed(0)} Hz · {hover.db.toFixed(1)} dB
        </div>
      )}
    </div>
  );
}

/** Small wrapper so rendering works whether or not OffscreenCanvas exists. */
class OffscreenOrFallbackCanvas {
  element: HTMLCanvasElement | OffscreenCanvas;
  constructor(w: number, h: number) {
    if (typeof OffscreenCanvas !== "undefined") {
      this.element = new OffscreenCanvas(w, h);
    } else {
      const c = document.createElement("canvas");
      c.width = w;
      c.height = h;
      this.element = c;
    }
  }
  getContext(): CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D {
    const ctx = (this.element as HTMLCanvasElement).getContext("2d");
    if (!ctx) throw new Error("2d context unavailable");
    return ctx as CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
  }
}
