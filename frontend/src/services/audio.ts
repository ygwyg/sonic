/* Browser audio helpers: base64 WAV handling, gain-controlled playback,
 * microphone capture to 16-bit mono PCM WAV, and a level meter. */

// --------------------------------------------------------- base64 / blobs

export function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64);
  const out = new Uint8Array(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function base64ToBlob(b64: string, mime = "audio/wav"): Blob {
  return new Blob([base64ToBytes(b64)], { type: mime });
}

export function base64ToObjectUrl(b64: string, mime = "audio/wav"): string {
  return URL.createObjectURL(base64ToBlob(b64, mime));
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function downloadBase64(b64: string, filename: string, mime = "application/octet-stream"): void {
  downloadBlob(base64ToBlob(b64, mime), filename);
}

// ----------------------------------------------------------- WAV encoder

/** Encode Float32 PCM (-1..1) as a 16-bit mono RIFF/WAVE blob. */
export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const n = samples.length;
  const buffer = new ArrayBuffer(44 + n * 2);
  const view = new DataView(buffer);
  const writeStr = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + n * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeStr(36, "data");
  view.setUint32(40, n * 2, true);
  let off = 44;
  for (let i = 0; i < n; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export function concatFloat32(chunks: Float32Array[]): Float32Array {
  let total = 0;
  for (const c of chunks) total += c.length;
  const out = new Float32Array(total);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.length;
  }
  return out;
}

// --------------------------------------------------------------- playback

export interface Player {
  readonly element: HTMLAudioElement;
  setVolume(v: number): void;
  play(): Promise<void>;
  pause(): void;
  destroy(): void;
}

/**
 * Wrap an <audio> element in a Web Audio gain node. Volume is clamped to
 * [0, 1]; nothing here ever autoplays. The AudioContext is created lazily on
 * the first play() so it is always started by a user gesture.
 */
export function createPlayer(element: HTMLAudioElement, initialVolume = 0.5): Player {
  let ctx: AudioContext | null = null;
  let gain: GainNode | null = null;
  let volume = clamp01(initialVolume);
  element.volume = volume;

  const ensureGraph = () => {
    if (ctx) return;
    try {
      ctx = new AudioContext();
      const src = ctx.createMediaElementSource(element);
      gain = ctx.createGain();
      gain.gain.value = volume;
      src.connect(gain).connect(ctx.destination);
      // The gain node now controls loudness; keep the element at full scale.
      element.volume = 1;
    } catch {
      ctx = null;
      gain = null;
    }
  };

  return {
    element,
    setVolume(v: number) {
      volume = clamp01(v);
      if (gain) gain.gain.value = volume;
      else element.volume = volume;
    },
    async play() {
      ensureGraph();
      if (ctx && ctx.state === "suspended") await ctx.resume();
      await element.play();
    },
    pause() {
      element.pause();
    },
    destroy() {
      element.pause();
      if (ctx) void ctx.close();
      ctx = null;
      gain = null;
    },
  };
}

export function clamp01(v: number): number {
  if (!Number.isFinite(v)) return 0;
  return Math.max(0, Math.min(1, v));
}

// --------------------------------------------------------------- recorder

export interface RecorderHandle {
  /** AudioContext sample rate in Hz (the WAV sample rate). */
  sampleRate: number;
  /** Stop capture and return a 16-bit mono WAV blob plus the raw samples. */
  stop(): Promise<{ blob: Blob; samples: Float32Array; sampleRate: number; duration_s: number }>;
  /** Instantaneous RMS level 0..1 of the latest block. */
  level(): number;
  /** Seconds of audio captured so far. */
  elapsed(): number;
}

const WORKLET_SOURCE = `
class SonicCapture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch && ch.length) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("sonic-capture", SonicCapture);
`;

/**
 * Start capturing raw microphone PCM. Must be called from a user gesture;
 * getUserMedia is requested here and nowhere else. Uses an AudioWorklet when
 * available and falls back to ScriptProcessorNode.
 */
export async function startRecording(): Promise<RecorderHandle> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone capture is not supported in this browser.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    video: false,
  });
  const ctx = new AudioContext();
  if (ctx.state === "suspended") await ctx.resume();
  const source = ctx.createMediaStreamSource(stream);
  const chunks: Float32Array[] = [];
  let captured = 0;
  let level = 0;

  const onBlock = (block: Float32Array) => {
    chunks.push(block);
    captured += block.length;
    let acc = 0;
    for (let i = 0; i < block.length; i++) acc += block[i] * block[i];
    const rms = Math.sqrt(acc / Math.max(1, block.length));
    level = level * 0.6 + rms * 0.4;
  };

  let cleanup: () => void;
  let usedWorklet = false;
  if (ctx.audioWorklet) {
    try {
      const url = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: "application/javascript" }));
      await ctx.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);
      const node = new AudioWorkletNode(ctx, "sonic-capture", { numberOfInputs: 1, numberOfOutputs: 0 });
      node.port.onmessage = (ev: MessageEvent<Float32Array>) => onBlock(ev.data);
      source.connect(node);
      cleanup = () => {
        node.port.onmessage = null;
        try {
          source.disconnect(node);
        } catch {
          /* ignore */
        }
      };
      usedWorklet = true;
    } catch {
      usedWorklet = false;
    }
  }
  if (!usedWorklet) {
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    proc.onaudioprocess = (ev) => onBlock(new Float32Array(ev.inputBuffer.getChannelData(0)));
    const sink = ctx.createGain();
    sink.gain.value = 0; // keep the processor alive without feedback
    source.connect(proc);
    proc.connect(sink).connect(ctx.destination);
    cleanup = () => {
      proc.onaudioprocess = null;
      try {
        source.disconnect(proc);
        proc.disconnect();
        sink.disconnect();
      } catch {
        /* ignore */
      }
    };
  }

  const sampleRate = ctx.sampleRate;
  return {
    sampleRate,
    level: () => Math.min(1, level * 4),
    elapsed: () => captured / sampleRate,
    async stop() {
      cleanup();
      stream.getTracks().forEach((t) => t.stop());
      await ctx.close();
      const samples = concatFloat32(chunks);
      return { blob: encodeWav(samples, sampleRate), samples, sampleRate, duration_s: samples.length / sampleRate };
    },
  };
}

// ------------------------------------------------------------- utilities

export function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / 1024 / 1024).toFixed(2)} MiB`;
}
