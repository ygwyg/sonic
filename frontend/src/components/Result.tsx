import { useState } from "react";
import type { Received } from "../lib/api";
import { base64ToBytes, download } from "../lib/audio";
import { bitrate, bytes, modulation, seconds } from "../lib/format";
import { Constellation, SnrByFrequency } from "./Figures";

function quality(db: number | null): string {
  if (db == null) return "";
  return db >= 25 ? "Excellent" : db >= 15 ? "Good" : "Weak";
}

export default function Result({ event }: { event: Received }) {
  const { header: h, summary: s, figures: f } = event;
  const [copied, setCopied] = useState(false);
  const isUrl = h.payload_type === "url" && event.text && /^https?:\/\/\S+$/.test(event.text.trim());
  const name = h.filename || (event.text != null ? "message.txt" : "received.bin");
  const saved = h.original_length > 0 ? 1 - h.payload_length / h.original_length : 0;

  const metrics: ([string, string, string?] | null)[] = [
    ["Signal quality", s.snr_db != null ? `${s.snr_db.toFixed(1)} dB` : "–", quality(s.snr_db)],
    ["Speed", bitrate(s.net_bitrate_bps), "Including compression"],
    ["Sound length", seconds(s.airtime_s)],
    ["Sent over the air", bytes(h.payload_length), saved > 0.01 ? `${Math.round(saved * 100)}% smaller than the original` : "Not compressed"],
    s.sro_ppm != null ? ["Clock difference", `${Math.abs(s.sro_ppm).toFixed(0)} ppm`, "Between the two devices"] : null,
    ["Encoding", modulation(s.config.modulation, s.config.code_rate), s.config.n_active_carriers ? `${s.config.n_active_carriers} tones at once` : undefined],
    ["Packets", s.packets ? `${s.packets.n_ok} of ${s.packets.n_packets}` : "–", "Each checked separately"],
    ["Decoded in", `${Math.round(s.decode_time_s * 1000)} ms`],
  ];

  return (
    <section className="result" aria-label="Received content">
      <div className="result-head">
        <h3>{h.filename || (isUrl ? "Link" : "Message")}</h3>
        <p className="quiet">{bytes(h.original_length)}, matches the sender’s SHA-256 fingerprint</p>
      </div>

      {isUrl ? (
        <a className="result-link" href={event.text!.trim()} target="_blank" rel="noreferrer noopener">
          {event.text!.trim()}
        </a>
      ) : event.text != null ? (
        <pre className="result-text">{event.text}</pre>
      ) : (
        <p className="result-binary">This is a binary file. Save it to open it.</p>
      )}

      <div className="actions">
        {event.text != null && (
          <button
            className="secondary"
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
          <button className="secondary" onClick={() => download(base64ToBytes(event.data_base64!), name)}>
            Save file
          </button>
        )}
      </div>

      <dl className="metrics">
        {metrics.filter((m) => m !== null).map(([k, v, note]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
            {note && <dd className="quiet">{note}</dd>}
          </div>
        ))}
      </dl>

      <div className="figures">
        {f.constellation && (
          <figure>
            <Constellation re={f.constellation.re} im={f.constellation.im} />
            <figcaption>
              <strong>Received symbols.</strong> Each dot is one tone at one instant. Tight clusters mean a clean signal.
            </figcaption>
          </figure>
        )}
        {f.snr_db && (
          <figure>
            <SnrByFrequency hz={f.snr_frequencies_hz} db={f.snr_db} />
            <figcaption>
              <strong>Signal quality by frequency.</strong> Dips are tones the speaker, microphone or room swallowed.
            </figcaption>
          </figure>
        )}
      </div>
    </section>
  );
}
