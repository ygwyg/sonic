/* Browser audio: one shared AudioContext with an analyser that the trace
 * reads, playback of encoded WAVs, and microphone streaming. */

let ctx: AudioContext | null = null;
let analyser: AnalyserNode | null = null;

/** Create (or resume) the shared context. Call synchronously inside a user gesture. */
export function audioContext(): AudioContext {
  if (!ctx) {
    ctx = new AudioContext();
    analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
  }
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

export function sharedAnalyser(): AnalyserNode | null {
  return analyser;
}

export function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function download(bytes: Uint8Array<ArrayBuffer> | Blob, filename: string, mime = "application/octet-stream") {
  const blob = bytes instanceof Blob ? bytes : new Blob([bytes], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export interface Playback {
  duration: number;
  /** Seconds played so far. */
  position(): number;
  stop(): void;
  done: Promise<void>;
}

export async function playWav(bytes: Uint8Array<ArrayBuffer>): Promise<Playback> {
  const c = audioContext();
  const buf = await c.decodeAudioData(bytes.slice().buffer);
  const src = c.createBufferSource();
  src.buffer = buf;
  src.connect(analyser!);
  analyser!.connect(c.destination);
  const t0 = c.currentTime;
  let resolve!: () => void;
  const done = new Promise<void>((r) => (resolve = r));
  src.onended = () => {
    src.disconnect();
    analyser!.disconnect();
    resolve();
  };
  src.start();
  return {
    duration: buf.duration,
    position: () => Math.min(buf.duration, c.currentTime - t0),
    stop: () => {
      try {
        src.stop();
      } catch {
        /* already stopped */
      }
    },
    done,
  };
}

const WORKLET = `
class SonicTap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch && ch.length) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("sonic-tap", SonicTap);
`;

export interface Mic {
  sampleRate: number;
  stop(): void;
}

/**
 * Stream the microphone as int16 PCM frames (~85 ms each). Voice processing
 * (echo cancellation, noise suppression, auto gain) is turned off because it
 * distorts the tones. Call inside a user gesture.
 */
export async function startMic(onFrame: (pcm: Int16Array) => void): Promise<Mic> {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("This browser can’t use the microphone. On a phone, open the page over HTTPS.");
  const c = audioContext();
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
  });
  const source = c.createMediaStreamSource(stream);
  source.connect(analyser!);

  const FRAME = 4096;
  let acc = new Int16Array(FRAME);
  let n = 0;
  const push = (block: Float32Array) => {
    for (let i = 0; i < block.length; i++) {
      const v = Math.max(-1, Math.min(1, block[i]));
      acc[n++] = v < 0 ? v * 32768 : v * 32767;
      if (n === FRAME) {
        onFrame(acc);
        acc = new Int16Array(FRAME);
        n = 0;
      }
    }
  };

  const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
  await c.audioWorklet.addModule(url);
  URL.revokeObjectURL(url);
  const tap = new AudioWorkletNode(c, "sonic-tap", { numberOfInputs: 1, numberOfOutputs: 0 });
  tap.port.onmessage = (e: MessageEvent<Float32Array>) => push(e.data);
  source.connect(tap);

  return {
    sampleRate: c.sampleRate,
    stop: () => {
      tap.port.onmessage = null;
      source.disconnect();
      stream.getTracks().forEach((t) => t.stop());
    },
  };
}
