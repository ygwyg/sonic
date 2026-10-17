import { useEffect, useMemo, useRef, useState } from "react";
import { base64ToBlob, clamp01, createPlayer, downloadBlob, type Player } from "../services/audio";

interface Props {
  /** Base64 WAV payload from the API. */
  wavBase64?: string | null;
  /** Or a ready Blob (e.g. a microphone recording). */
  blob?: Blob | null;
  filename?: string;
  /** Initial volume, 0..1 (default 0.5). Never autoplays. */
  initialVolume?: number;
  label?: string;
  big?: boolean;
}

/** Audio player with an explicit volume slider wired to a Web Audio gain node. */
export default function AudioPlayer({ wavBase64, blob, filename = "sonic.wav", initialVolume = 0.5, label, big }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const playerRef = useRef<Player | null>(null);
  const [volume, setVolume] = useState(clamp01(initialVolume));
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [dur, setDur] = useState(0);

  const theBlob = useMemo(() => (blob ? blob : wavBase64 ? base64ToBlob(wavBase64) : null), [blob, wavBase64]);
  const [url, setUrl] = useState<string | null>(null);
  // Create/revoke the object URL inside an effect so StrictMode's double
  // invocation cannot revoke a URL that is still in use.
  useEffect(() => {
    if (!theBlob) {
      setUrl(null);
      return;
    }
    const u = URL.createObjectURL(theBlob);
    setUrl(u);
    setTime(0);
    setDur(0);
    return () => URL.revokeObjectURL(u);
  }, [theBlob]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    if (!playerRef.current) playerRef.current = createPlayer(el, volume);
    const p = playerRef.current;
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onTime = () => setTime(el.currentTime);
    const onMeta = () => setDur(el.duration);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onPause);
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("loadedmetadata", onMeta);
    return () => {
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onPause);
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("loadedmetadata", onMeta);
      p.pause();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => playerRef.current?.destroy(), []);
  useEffect(() => {
    playerRef.current?.setVolume(volume);
  }, [volume]);

  const toggle = async () => {
    const p = playerRef.current;
    if (!p || !url) return;
    if (playing) p.pause();
    else {
      try {
        await p.play();
      } catch {
        /* play() can reject if the browser blocks it; leave paused */
      }
    }
  };

  const pct = dur > 0 ? (time / dur) * 100 : 0;

  return (
    <div className={`flex flex-col gap-2 rounded-md border border-line bg-bg/60 ${big ? "p-4" : "p-3"}`}>
      {label && <div className="text-xs uppercase tracking-wider text-muted">{label}</div>}
      <audio ref={audioRef} src={url ?? undefined} preload="metadata" />
      <div className="flex flex-wrap items-center gap-3">
        <button className={`btn ${big ? "btn-primary px-5 py-2 text-base" : ""}`} onClick={toggle} disabled={!url}>
          {playing ? "❚❚ Pause" : "▶ Play"}
        </button>
        <div className="num min-w-[90px] text-xs text-ink2">
          {time.toFixed(1)} / {Number.isFinite(dur) ? dur.toFixed(1) : "—"} s
        </div>
        <div className="h-1.5 min-w-[80px] flex-1 overflow-hidden rounded bg-line">
          <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
        </div>
        {theBlob && (
          <button className="btn" onClick={() => downloadBlob(theBlob, filename)}>
            ⤓ Download WAV
          </button>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs text-muted">Volume</span>
        <input
          type="range"
          className="range max-w-xs"
          min={0}
          max={1}
          step={0.01}
          value={volume}
          onChange={(e) => setVolume(clamp01(parseFloat(e.target.value)))}
          aria-label="Volume"
        />
        <span className="num w-10 text-xs text-ink2">{Math.round(volume * 100)}%</span>
      </div>
    </div>
  );
}
