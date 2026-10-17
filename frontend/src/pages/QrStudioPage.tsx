import { useCallback, useState } from "react";
import AudioPlayer from "../components/AudioPlayer";
import Card from "../components/Card";
import ErrorBanner from "../components/ErrorBanner";
import FileDrop from "../components/FileDrop";
import PageHeader from "../components/PageHeader";
import Recorder, { type Recording } from "../components/Recorder";
import api, { type EncodeResponse, type QrDecodeResponse } from "../services/api";
import { fmt, fmtS } from "../services/format";

const TEMPLATES: { id: string; label: string; payload_type: string; text: string }[] = [
  { id: "text", label: "Plain text", payload_type: "text", text: "Meet me at the north entrance at 7pm. Bring the blue folder." },
  { id: "url", label: "Web link", payload_type: "url", text: "https://example.com/menu" },
  { id: "json", label: "JSON", payload_type: "json", text: '{"wifi":"CafeGuest","pass":"latte2026","note":"2nd floor"}' },
  { id: "contact", label: "Contact card", payload_type: "contact", text: "BEGIN:VCARD\nVERSION:3.0\nN:Doe;Jane\nFN:Jane Doe\nTEL:+1 555 0100\nEMAIL:jane@example.com\nEND:VCARD" },
];

const MAX_CHARS = 4000;

export default function QrStudioPage() {
  const [text, setText] = useState(TEMPLATES[0].text);
  const [payloadType, setPayloadType] = useState("text");
  const [busy, setBusy] = useState(false);
  const [sound, setSound] = useState<EncodeResponse | null>(null);
  const [encodeError, setEncodeError] = useState<string | null>(null);

  const [listenSeconds, setListenSeconds] = useState(10);
  const [decoding, setDecoding] = useState(false);
  const [decoded, setDecoded] = useState<QrDecodeResponse | null>(null);
  const [decodeError, setDecodeError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const makeSound = async () => {
    setBusy(true);
    setEncodeError(null);
    try {
      const r = await api.qrEncode(text, 0.6, payloadType);
      setSound(r);
    } catch (e) {
      setEncodeError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const decodeBlob = useCallback(async (blob: Blob, name: string) => {
    setDecoding(true);
    setDecodeError(null);
    setDecoded(null);
    setCopied(false);
    try {
      const r = await api.qrDecode(blob, name);
      setDecoded(r);
    } catch (e) {
      setDecodeError((e as Error).message);
    } finally {
      setDecoding(false);
    }
  }, []);

  const onRecording = useCallback((rec: Recording) => void decodeBlob(rec.blob, "recording.wav"), [decodeBlob]);

  const copy = async () => {
    if (!decoded?.text) return;
    try {
      await navigator.clipboard.writeText(decoded.text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <PageHeader title="Audio QR Studio" subtitle="Share a short message between devices using nothing but a speaker and a microphone." />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* ---------------------------------------------------------- send */}
        <Card title="1 · Make a sound" subtitle="Type something, press Make sound, then play it near the listening device.">
          <div className="mb-2 flex flex-wrap gap-2">
            {TEMPLATES.map((t) => (
              <button
                key={t.id}
                className={`rounded-full border px-3 py-1 text-xs ${payloadType === t.payload_type ? "border-accent text-ink" : "border-line text-ink2 hover:border-ink2"}`}
                onClick={() => {
                  setText(t.text);
                  setPayloadType(t.payload_type);
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
          <textarea className="input min-h-[140px] font-sans text-base" value={text} maxLength={MAX_CHARS} onChange={(e) => setText(e.target.value)} placeholder="Your message…" />
          <div className="num mt-1 text-right text-xs text-muted">
            {text.length} / {MAX_CHARS}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button className="btn btn-primary px-6 py-2.5 text-base" onClick={makeSound} disabled={busy || text.trim().length === 0}>
              {busy ? "Encoding…" : "♪ Make sound"}
            </button>
            {sound && (
              <span className="num text-xs text-muted">
                {fmtS(sound.info.duration_s)} · {sound.info.header.payload_length} bytes on air · {sound.info.compression.algorithm}
              </span>
            )}
          </div>
          {encodeError && (
            <div className="mt-3">
              <ErrorBanner onDismiss={() => setEncodeError(null)}>{encodeError}</ErrorBanner>
            </div>
          )}
          {sound && (
            <div className="mt-4">
              <AudioPlayer wavBase64={sound.wav_base64} filename="audio-qr.wav" initialVolume={0.5} big label="Your sound" />
              <p className="mt-2 text-xs text-muted">Tip: play at a comfortable volume, 30–100 cm from the listening microphone. Avoid talking over it.</p>
            </div>
          )}
        </Card>

        {/* -------------------------------------------------------- receive */}
        <Card title="2 · Listen" subtitle="Press Listen on the receiving device, then play the sound from the other one.">
          <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
            <label className="text-ink2">Listen for</label>
            <input type="range" className="range max-w-[200px]" min={5} max={30} step={1} value={listenSeconds} onChange={(e) => setListenSeconds(Number(e.target.value))} />
            <span className="num text-ink">{listenSeconds} s</span>
          </div>
          <Recorder onRecording={onRecording} maxSeconds={listenSeconds} startLabel="🎤 Listen" big disabled={decoding} />
          <div className="my-3 text-center text-xs text-muted">— or —</div>
          <FileDrop compact accept=".wav,audio/wav,audio/x-wav" onFile={(f) => void decodeBlob(f, f.name)} disabled={decoding} label="Upload a recording (WAV)" />

          {decoding && <div className="mt-4 text-sm text-ink2">Decoding…</div>}
          {decodeError && (
            <div className="mt-4">
              <ErrorBanner onDismiss={() => setDecodeError(null)}>{decodeError}</ErrorBanner>
            </div>
          )}
          {decoded && (
            <div className="mt-4">
              {decoded.success ? (
                <div className="rounded-lg border border-good/50 bg-good/10 p-4">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-sm font-medium text-good">✓ Message received</span>
                    <button className="btn" onClick={copy} disabled={!decoded.text}>
                      {copied ? "Copied" : "Copy"}
                    </button>
                  </div>
                  {typeof decoded.text === "string" ? (
                    <pre className="plain max-h-72 overflow-auto rounded-md bg-bg p-3 font-sans text-lg text-ink">{decoded.text}</pre>
                  ) : (
                    <div className="text-sm text-ink2">Received binary data ({decoded.header?.original_length ?? "?"} bytes).</div>
                  )}
                  <div className="num mt-2 text-xs text-muted">
                    {decoded.header?.payload_type ?? ""} · SNR {fmt(decoded.summary?.snr_db, 1)} dB · sync {fmt(decoded.summary?.sync_score, 2)} · {decoded.summary?.packets ? `${decoded.summary.packets.n_ok}/${decoded.summary.packets.n_packets} packets` : ""} ·{" "}
                    {decoded.summary?.sha256?.match ? "integrity ok" : "integrity —"} · {fmtS(decoded.decode_time_s)}
                  </div>
                </div>
              ) : (
                <FriendlyFailure r={decoded} />
              )}
            </div>
          )}
        </Card>
      </div>

      <Card title="Tips for a clean transfer">
        <ul className="grid list-disc grid-cols-1 gap-1 pl-5 text-sm text-ink2 md:grid-cols-2">
          <li>Hold the phone or laptop 30–100 cm from the speaker.</li>
          <li>Reduce background noise — pause music, close windows.</li>
          <li>Start listening first, then play the sound; keep listening until playback ends.</li>
          <li>Keep the volume moderate; distortion from a maxed-out speaker hurts more than quiet playback.</li>
          <li>Short messages are more robust; links and contact cards usually transfer in a few seconds.</li>
          <li>If it fails, try again a bit closer and with a longer listening window.</li>
        </ul>
      </Card>
    </div>
  );
}

function FriendlyFailure({ r }: { r: QrDecodeResponse }) {
  const err = (r.error ?? "").toLowerCase();
  let title = "Could not read a message";
  let advice = "Try again closer to the speaker with a longer listening window.";
  if (err.includes("preamble") || err.includes("sync") || err.includes("no transmission") || err.includes("not found")) {
    title = "No transmission detected";
    advice = "The listener did not hear a Sonic signal. Make sure the sound actually played, start listening before playback, and move closer.";
  } else if (err.includes("sha") || err.includes("integrity") || err.includes("crc") || err.includes("packet")) {
    title = "Received, but failed the integrity check";
    advice = "Part of the message was corrupted by noise or echo. Reduce background noise, lower the playback volume a little, and try again.";
  } else if (err.includes("header")) {
    title = "Could not read the message header";
    advice = "The start of the transmission was not clear. Keep the devices still and try again a bit closer.";
  }
  return (
    <div className="rounded-lg border border-bad/50 bg-bad/10 p-4">
      <div className="text-sm font-medium text-bad">✕ {title}</div>
      <p className="mt-1 text-sm text-ink2">{advice}</p>
      {r.error && <div className="num mt-2 text-xs text-muted">detail: {r.error}</div>}
      <div className="num mt-1 text-xs text-muted">
        sync {fmt(r.summary?.sync_score, 2)} · SNR {fmt(r.summary?.snr_db, 1)} dB
      </div>
    </div>
  );
}
