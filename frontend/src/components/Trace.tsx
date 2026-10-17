import { useEffect, useRef } from "react";
import { sharedAnalyser } from "../lib/audio";

const STEP = 3; // px per column

/**
 * A single line across the page. While `active`, it scrolls a trace of the
 * sound passing through the shared analyser (playback or microphone) and
 * settles back to a flat line once the sound stops.
 */
export default function Trace({ active }: { active: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const activeRef = useRef(active);
  activeRef.current = active;
  const kick = useRef<() => void>(() => {});

  useEffect(() => {
    const el = canvas.current!;
    const g = el.getContext("2d")!;
    let cols: number[] = [];
    let raf = 0;
    let scale = 0.05;
    const td = new Float32Array(2048);

    const size = () => {
      const dpr = window.devicePixelRatio || 1;
      el.width = el.clientWidth * dpr;
      el.height = el.clientHeight * dpr;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      cols = cols.slice(-Math.ceil(el.clientWidth / STEP));
      draw();
    };

    const draw = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      const mid = h / 2;
      const ink = getComputedStyle(el).color;
      g.clearRect(0, 0, w, h);
      g.fillStyle = ink;
      g.fillRect(0, Math.round(mid), w, 1);
      const n = cols.length;
      for (let i = 0; i < n; i++) {
        const a = cols[i];
        if (a < 0.004) continue;
        const x = w - (n - i) * STEP;
        const half = Math.max(0.5, a * (mid - 2));
        g.fillRect(x, mid - half, STEP - 1, half * 2);
      }
    };

    const frame = () => {
      const an = sharedAnalyser();
      let peak = 0;
      if (an && activeRef.current) {
        an.getFloatTimeDomainData(td);
        for (let i = 0; i < td.length; i++) peak = Math.max(peak, Math.abs(td[i]));
      }
      scale = Math.max(peak, scale * 0.995, 0.02);
      cols.push(Math.min(1, peak / scale));
      const max = Math.ceil(el.clientWidth / STEP);
      if (cols.length > max) cols = cols.slice(-max);
      draw();
      if (activeRef.current || cols.some((c) => c >= 0.004)) raf = requestAnimationFrame(frame);
      else raf = 0;
    };

    kick.current = () => {
      if (!raf) raf = requestAnimationFrame(frame);
    };
    const ro = new ResizeObserver(size);
    ro.observe(el);
    size();
    return () => {
      ro.disconnect();
      cancelAnimationFrame(raf);
    };
  }, []);

  useEffect(() => {
    if (active) kick.current();
  }, [active]);

  return <canvas ref={canvas} className="trace" aria-hidden="true" />;
}
