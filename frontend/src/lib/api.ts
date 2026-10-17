/* Client for the Sonic backend. Paths are relative to /api, which the Vite
 * dev server proxies (HTTP and WebSocket) to the FastAPI app. */

export type Mode = "fast" | "balanced" | "reliable";

export const MODES: { id: Mode; label: string; hint: string; config: Record<string, string> }[] = [
  { id: "fast", label: "Fast", hint: "Devices within a hand’s width of each other.", config: { preset: "default", modulation: "16qam", code_rate: "1/2" } },
  { id: "balanced", label: "Balanced", hint: "About half a metre apart. Tested laptop to phone.", config: { preset: "default" } },
  { id: "reliable", label: "Reliable", hint: "Slowest. Holds up better in echoey rooms.", config: { preset: "robust" } },
];

export interface Config {
  modulation: string;
  code_rate: string;
  n_fft: number;
  cp_len: number;
  f_low: number;
  f_high: number;
  n_active_carriers?: number;
}

export interface Header {
  payload_type: string;
  compression: string;
  original_length: number;
  payload_length: number;
  n_packets: number;
  sha256: string;
  filename: string;
  config: Config;
}

export interface EncodeResult {
  wav_base64: string;
  info: {
    duration_s: number;
    net_bitrate_bps: number;
    compression: { algorithm: string; original_size: number; compressed_size: number };
    header: Header;
  };
}

export interface Received {
  type: "received";
  header: Header;
  text?: string | null;
  data_base64?: string;
  summary: {
    snr_db: number | null;
    airtime_s: number;
    net_bitrate_bps: number | null;
    sro_ppm: number | null;
    decode_time_s: number;
    config: Config;
    packets: { n_packets: number; n_ok: number } | null;
  };
  figures: {
    constellation: { re: number[]; im: number[] } | null;
    snr_frequencies_hz: number[];
    snr_db: number[] | null;
  };
}

export type ListenEvent =
  | { type: "listening" }
  | { type: "receiving"; progress: number | null; remaining_s?: number; header?: Header }
  | Received
  | { type: "failed"; error: string }
  | { type: "error"; error: string };

async function asJson<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const body = await r.json();
      if (body?.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep status text */
    }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export function encodeText(text: string, mode: Mode): Promise<EncodeResult> {
  const config = MODES.find((m) => m.id === mode)!.config;
  return fetch("/api/encode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, config, compression: "auto", payload_type: /^https?:\/\/\S+$/.test(text.trim()) ? "url" : "text", amplitude: 0.8 }),
  }).then((r) => asJson<EncodeResult>(r));
}

export function encodeFile(file: File, mode: Mode): Promise<EncodeResult> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  fd.append("config", JSON.stringify(MODES.find((m) => m.id === mode)!.config));
  fd.append("compression", "auto");
  fd.append("payload_type", "binary");
  fd.append("amplitude", "0.8");
  return fetch("/api/encode/file", { method: "POST", body: fd }).then((r) => asJson<EncodeResult>(r));
}

export function openListenSocket(): WebSocket {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/api/listen`);
  ws.binaryType = "arraybuffer";
  return ws;
}
