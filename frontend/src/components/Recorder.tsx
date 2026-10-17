import { useCallback, useEffect, useRef, useState } from "react";
import { startRecording, type RecorderHandle } from "../services/audio";

export interface Recording {
  blob: Blob;
  samples: Float32Array;
  sampleRate: number;
  duration_s: number;
}

interface Props {
  onRecording: (rec: Recording) => void;
  /** Auto-stop after this many seconds (undefined = manual stop). */
  maxSeconds?: number;
  disabled?: boolean;
  startLabel?: string;
  big?: boolean;
}

/**
 * Microphone recorder. getUserMedia is requested only when the user presses
 * the start button. Shows a level meter and elapsed time while recording.
 */
export default function Recorder({ onRecording, maxSeconds, disabled, startLabel = "● Start recording", big }: Props) {
  const handleRef = useRef<RecorderHandle | null>(null);
  const [recording, setRecording] = useState(false);
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [sampleRate, setSampleRate] = useState<number | null>(null);
  const rafRef = useRef<number>(0);

  const stop = useCallback(async () => {
    const h = handleRef.current;
    if (!h) return;
    handleRef.current = null;
    cancelAnimationFrame(rafRef.current);
    setRecording(false);
    try {
      const rec = await h.stop();
      onRecording(rec);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [onRecording]);

  const start = useCallback(async () => {
    setError(null);
    try {
      const h = await startRecording();
      handleRef.current = h;
      setSampleRate(h.sampleRate);
      setRecording(true);
      setElapsed(0);
      const tick = () => {
        const cur = handleRef.current;
        if (!cur) return;
        setLevel(cur.level());
        const t = cur.elapsed();
        setElapsed(t);
        if (maxSeconds !== undefined && t >= maxSeconds) {
          void stop();
          return;
        }
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    } catch (e) {
      const err = e as Error;
      setError(
        err.name === "NotAllowedError"
          ? "Microphone permission was denied. Allow microphone access and try again."
          : err.message || "Could not start the microphone."
      );
    }
  }, [maxSeconds, stop]);

  useEffect(
    () => () => {
      cancelAnimationFrame(rafRef.current);
      const h = handleRef.current;
      handleRef.current = null;
      if (h) void h.stop();
    },
    []
  );

  const remaining = maxSeconds !== undefined ? Math.max(0, maxSeconds - elapsed) : null;

  return (
    <div className={`flex flex-col gap-3 rounded-md border border-line bg-bg/60 ${big ? "p-4" : "p-3"}`}>
      <div className="flex flex-wrap items-center gap-3">
        {!recording ? (
          <button className={`btn ${big ? "btn-primary px-5 py-2 text-base" : ""}`} onClick={start} disabled={disabled}>
            {startLabel}
          </button>
        ) : (
          <button className="btn btn-danger" onClick={stop}>
            ■ Stop
          </button>
        )}
        <div className="num text-sm text-ink2">
          {recording ? (
            <>
              <span className="mr-1 inline-block h-2 w-2 animate-pulse rounded-full bg-bad" />
              {elapsed.toFixed(1)} s
              {remaining !== null && <span className="text-muted"> · stops in {remaining.toFixed(0)} s</span>}
            </>
          ) : (
            <span className="text-muted">{sampleRate ? `last session @ ${sampleRate} Hz` : "microphone idle"}</span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted">Level</span>
        <div className="h-2 flex-1 overflow-hidden rounded bg-line" role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={level}>
          <div
            className="h-full transition-[width] duration-75"
            style={{
              width: `${Math.round(level * 100)}%`,
              background: level > 0.9 ? "var(--bad)" : level > 0.6 ? "var(--warn)" : "var(--good)",
            }}
          />
        </div>
      </div>
      {error && <div className="text-xs text-bad">{error}</div>}
    </div>
  );
}
