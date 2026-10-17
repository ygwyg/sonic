import { useState } from "react";
import type { Received } from "../lib/api";
import { base64ToBytes, download } from "../lib/audio";
import { bitrate, bytes, modulation, seconds } from "../lib/format";
import { Constellation, LineChart } from "./Figures";

const kHz = (v: number) => `${+(v / 1000).toFixed(1)}k`;

export default function Result({ event }: { event: Received }) {
  const { header: h, summary: s, figures: f } = event;
  const [copied, setCopied] = useState(false);
  const text = event.text?.trim();
  const isUrl = !!text && /^https?:\/\/\S+$/.test(text);
  const name = h.filename || (event.text != null ? "message.txt" : "received.bin");

  const metrics: [string, string][] = [
    ["Signal", s.snr_db != null ? `${s.snr_db.toFixed(1)} dB` : "–"],
    ["Speed", bitrate(s.net_bitrate_bps)],
    ["Length", seconds(s.airtime_s)],
    ["Size", h.payload_length < h.original_length ? `${h.original_length} → ${bytes(h.payload_length)}` : bytes(h.original_length)],
    ["Encoding", modulation(s.config.modulation, s.config.code_rate)],
    ["Packets", s.packets ? `${s.packets.n_ok} / ${s.packets.n_packets}` : "–"],
  ];
  if (s.sro_ppm != null) metrics.push(["Clock offset", `${Math.abs(s.sro_ppm).toFixed(0)} ppm`]);

  return (
    <section className="result" aria-label="Received">
      {isUrl ? (
        <a className="result-link" href={text} target="_blank" rel="noreferrer noopener">
          {text}
        </a>
      ) : event.text != null ? (
        <pre className="result-text">{event.text}</pre>
      ) : (
        <p>Received {name}. It isn’t text, so save it to open it.</p>
      )}

      <div className="row">
        {event.text != null && (
          <button
            className="button"
            onClick={async () => {
              await navigator.clipboard.writeText(event.text!);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
          >
            {copied ? "Copied" : "Copy"}
          </button>
        )}
        {event.data_base64 && (
          <button className="button" onClick={() => download(base64ToBytes(event.data_base64!), name)}>
            Save
          </button>
        )}
        <span className="muted">Verified with SHA-256</span>
      </div>

      <dl className="metrics">
        {metrics.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>

      <div className="charts">
        {f.constellation && (
          <figure>
            <figcaption>Constellation</figcaption>
            <Constellation re={f.constellation.re} im={f.constellation.im} />
          </figure>
        )}
        {f.snr_db && (
          <figure>
            <figcaption>Signal quality by frequency (dB)</figcaption>
            <LineChart x={f.snr_frequencies_hz} y={f.snr_db} xFormat={kHz} />
          </figure>
        )}
        {f.channel_db && f.channel_hz && (
          <figure>
            <figcaption>Channel response (dB)</figcaption>
            <LineChart x={f.channel_hz} y={f.channel_db} xFormat={kHz} />
          </figure>
        )}
        {f.drift_samples && f.drift_samples.length >= 8 && (
          <figure>
            <figcaption>Timing drift by symbol (samples)</figcaption>
            <LineChart x={f.drift_samples.map((_, i) => i)} y={f.drift_samples} />
          </figure>
        )}
      </div>
    </section>
  );
}
