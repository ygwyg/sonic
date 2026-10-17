import { useEffect, useRef, useState } from "react";
import { encodeText, type Analysis, type EncodeResult } from "../lib/api";
import { seconds } from "../lib/format";
import { Dots, LineChart, Lines } from "./Figures";

const EXAMPLE = "Sonic sends data as hundreds of tones at once. They overlap in frequency but stay separable.";
const kHz = (v: number) => (v === 0 ? "0" : `${+(v / 1000).toFixed(1)}k`);
const ZOOM = 120; // samples of one symbol shown (2.5 ms at 48 kHz)

/** Charts of one transmission: the last one sent, or an example. */
export default function Explore({ sent }: { sent: EncodeResult | null }) {
  const [example, setExample] = useState<EncodeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const res = sent ?? example;

  useEffect(() => {
    if (sent || example) return;
    encodeText(EXAMPLE, "balanced").then(setExample, (e: Error) => setError(e.message));
  }, [sent, example]);

  if (error) return <p className="error">{error}</p>;
  if (!res) return <p className="muted">Preparing an example…</p>;

  const a = res.analysis;
  const fs = a.waveform.sample_rate;
  const demo = a.carriers_demo;
  const ms = demo ? demo.composite.slice(0, ZOOM).map((_, i) => (i / fs) * 1000) : [];
  const symbolMs = demo ? (demo.composite.length / fs) * 1000 : 0;
  // three tones at clearly different pitches read better than all of them
  const few = demo ? [demo.components[0], demo.components[Math.floor(demo.components.length / 2)], demo.components[demo.components.length - 1]] : [];

  return (
    <div className="explore">
      <p className="muted">
        {sent ? "The last message you sent" : "An example message"}: {res.info.header.original_length} bytes as {seconds(a.waveform.duration_s)} of sound,{" "}
        {a.allocation?.n_data ?? "–"} data tones and {a.allocation?.n_pilot ?? "–"} reference tones between {kHz(res.info.header.config.f_low)}Hz and{" "}
        {kHz(res.info.header.config.f_high)}Hz.
      </p>

      <figure>
        <figcaption>The whole sound. A chirp marks the start, then a robust header, then the data.</figcaption>
        <Waveform a={a} />
      </figure>

      <figure>
        <figcaption>Spectrum. All the energy sits inside the band the tones use.</figcaption>
        <LineChart x={a.spectrum.frequency_hz} y={a.spectrum.power_db} xFormat={kHz} />
      </figure>

      <figure>
        <figcaption>Spectrogram, 0–{kHz(fs / 2)}Hz bottom to top. The chirp sweeps up, the header fills a low band, the data a wider one.</figcaption>
        <Spectrogram s={a.spectrogram} />
      </figure>

      {a.allocation && a.header_allocation && (
        <figure>
          <figcaption>Where the tones sit. The shaded span carries data; each line is a reference tone the receiver already knows.</figcaption>
          <CarrierMap rows={[["Data", a.allocation], ["Header", a.header_allocation]]} nyquist={fs / 2} />
        </figure>
      )}

      {demo && (
        <>
          <figure>
            <figcaption>
              Three of the {demo.n_total_carriers} tones ({few.map((c) => kHz(c.frequency_hz) + "Hz").join(", ")}), first {ms[ms.length - 1].toFixed(1)} ms of a{" "}
              {symbolMs.toFixed(1)} ms symbol. Each is a plain sine wave.
            </figcaption>
            <Lines x={ms} series={few.map((c) => ({ y: c.samples.slice(0, ZOOM) }))} xFormat={(v) => `${v} ms`} height={220} />
          </figure>
          <figure>
            <figcaption>All {demo.n_total_carriers} added together. This is what the speaker actually plays.</figcaption>
            <Lines x={ms} series={[{ y: demo.composite.slice(0, ZOOM), strong: true }]} xFormat={(v) => `${v} ms`} height={220} />
          </figure>
          <figure>
            <figcaption>One FFT pulls them apart again. Each data tone’s phase lands on one of four values (two bits); reference tones sit at 0 or π.</figcaption>
            <Dots
              x={demo.carrier_frequencies_hz}
              y={demo.carrier_phases}
              xFormat={kHz}
              yTicks={[
                { v: -Math.PI, label: "−π" },
                { v: -Math.PI / 2, label: "−π/2" },
                { v: 0, label: "0" },
                { v: Math.PI / 2, label: "π/2" },
                { v: Math.PI, label: "π" },
              ]}
            />
          </figure>
        </>
      )}
    </div>
  );
}

const W = 600;

function Waveform({ a }: { a: Analysis }) {
  const H = 200;
  const env = a.waveform.envelope;
  const n = a.waveform.n_samples;
  const x = (i: number) => (i / n) * W;
  const y = (v: number) => H / 2 - v * (H / 2 - 24);
  const pts = [...env.index.map((i, k) => `${x(i).toFixed(1)},${y(env.max[k]).toFixed(1)}`), ...env.index.map((i, k) => `${x(i).toFixed(1)},${y(env.min[k]).toFixed(1)}`).reverse()];
  const sec = Object.fromEntries((a.sections ?? []).map((s) => [s.name, s]));
  const parts = [
    ["Chirp", sec.preamble?.start],
    ["Header", sec.header_training?.start],
    ["Data", sec.payload_training?.start],
  ].filter((p): p is [string, number] => p[1] != null);
  return (
    <svg className="fig" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Waveform">
      <polygon points={pts.join(" ")} className="fig-area" />
      {parts.map(([label, at]) => (
        <g key={label}>
          <line x1={x(at)} x2={x(at)} y1={0} y2={H} className="fig-mark" />
          <text x={x(at) + 6} y={16} className="fig-label">
            {label}
          </text>
        </g>
      ))}
    </svg>
  );
}

function Spectrogram({ s }: { s: Analysis["spectrogram"] }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = canvas.current!;
    const nf = s.db.length;
    const nt = s.db[0]?.length ?? 0;
    el.width = nt;
    el.height = nf;
    const g = el.getContext("2d")!;
    const css = getComputedStyle(document.documentElement);
    const rgb = (v: string) => {
      const h = v.trim().replace("#", "");
      return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
    };
    const bg = rgb(css.getPropertyValue("--bg"));
    const fg = rgb(css.getPropertyValue("--fg"));
    const img = g.createImageData(nt, nf);
    const span = s.db_max - s.db_min || 1;
    for (let f = 0; f < nf; f++) {
      for (let t = 0; t < nt; t++) {
        const k = Math.max(0, Math.min(1, (s.db[f][t] - s.db_min) / span)) ** 1.6;
        const o = ((nf - 1 - f) * nt + t) * 4;
        for (let c = 0; c < 3; c++) img.data[o + c] = bg[c] + (fg[c] - bg[c]) * k;
        img.data[o + 3] = 255;
      }
    }
    g.putImageData(img, 0, 0);
  }, [s]);
  return <canvas ref={canvas} className="fig spectrogram" aria-label="Spectrogram" />;
}

function CarrierMap({ rows, nyquist }: { rows: [string, NonNullable<Analysis["allocation"]>][]; nyquist: number }) {
  const L = 80;
  const rowH = 40;
  const H = rows.length * (rowH + 14) + 24;
  const x = (f: number) => L + (f / nyquist) * (W - L - 24);
  return (
    <svg className="fig" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Carrier map">
      {rows.map(([label, al], r) => {
        const top = r * (rowH + 14) + 4;
        return (
          <g key={label}>
            <text x={0} y={top + rowH / 2 + 7} className="fig-label">
              {label}
            </text>
            <line x1={L} x2={x(nyquist)} y1={top + rowH} y2={top + rowH} className="fig-grid" />
            <rect
              x={x(Math.min(...al.frequencies_hz))}
              width={x(Math.max(...al.frequencies_hz)) - x(Math.min(...al.frequencies_hz))}
              y={top}
              height={rowH}
              className="fig-span"
            />
            {al.frequencies_hz.map((f, i) =>
              al.roles[i] === "pilot" ? <line key={i} x1={x(f)} x2={x(f)} y1={top} y2={top + rowH} className="fig-tick" /> : null
            )}
          </g>
        );
      })}
      {[0, 0.25, 0.5, 0.75, 1].map((p) => (
        <text key={p} x={x(p * nyquist)} y={H - 4} textAnchor="middle" className="fig-label">
          {kHz(p * nyquist)}
        </text>
      ))}
    </svg>
  );
}
