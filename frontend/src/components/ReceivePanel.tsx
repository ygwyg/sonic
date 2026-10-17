import { useEffect, useRef, useState } from "react";
import { openListenSocket, type Header, type ListenEvent, type Received } from "../lib/api";
import { audioContext, startMic, type Mic } from "../lib/audio";
import { seconds } from "../lib/format";
import Result from "./Result";

type State =
  | { kind: "idle" }
  | { kind: "starting" }
  | { kind: "listening"; note?: string }
  | { kind: "receiving"; progress: number | null; remaining?: number; header?: Header }
  | { kind: "received"; event: Received }
  | { kind: "error"; message: string };

export default function ReceivePanel({ onSound }: { onSound: (on: boolean) => void }) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const session = useRef<{ ws: WebSocket; mic: Mic | null } | null>(null);

  const stop = () => {
    const s = session.current;
    session.current = null;
    s?.mic?.stop();
    if (s && s.ws.readyState <= WebSocket.OPEN) s.ws.close();
    onSound(false);
  };

  useEffect(() => stop, []); // eslint-disable-line react-hooks/exhaustive-deps

  const listen = async () => {
    audioContext(); // unlock audio inside the click
    setState({ kind: "starting" });
    const ws = openListenSocket();
    const s: { ws: WebSocket; mic: Mic | null } = { ws, mic: null };
    session.current = s;

    ws.onmessage = (m) => {
      const e = JSON.parse(m.data as string) as ListenEvent;
      if (session.current !== s) return;
      if (e.type === "listening") setState((p) => (p.kind === "listening" ? p : { kind: "listening" }));
      else if (e.type === "receiving") setState({ kind: "receiving", progress: e.progress, remaining: e.remaining_s, header: e.header });
      else if (e.type === "failed") setState({ kind: "listening", note: "Heard something but couldn’t read it. Move closer or try Reliable." });
      else if (e.type === "received") {
        stop();
        setState({ kind: "received", event: e });
      } else if (e.type === "error") {
        stop();
        setState({ kind: "error", message: e.error });
      }
    };
    ws.onclose = () => {
      if (session.current === s) {
        stop();
        setState({ kind: "error", message: "Lost the connection to the decoder. Check that the server is running." });
      }
    };

    try {
      const mic = await startMic((pcm) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(pcm.buffer);
      });
      s.mic = mic;
      if (session.current !== s) return mic.stop();
      const hello = () => ws.send(JSON.stringify({ sample_rate: mic.sampleRate }));
      if (ws.readyState === WebSocket.OPEN) hello();
      else ws.addEventListener("open", hello, { once: true });
      onSound(true);
    } catch (e) {
      stop();
      const err = e as Error;
      setState({ kind: "error", message: err.name === "NotAllowedError" ? "Microphone access was blocked. Allow it in your browser settings and try again." : err.message });
    }
  };

  const active = state.kind === "listening" || state.kind === "receiving" || state.kind === "starting";

  return (
    <div className="panel">
      <div className="row">
        <button
          className="button primary"
          onClick={() => {
            if (active) {
              stop();
              setState({ kind: "idle" });
            } else void listen();
          }}
          aria-pressed={active}
        >
          {active ? "Stop" : "Listen"}
        </button>
        <span className="status" aria-live="polite">
          {state.kind === "idle" && "Hold this device near the one playing."}
          {state.kind === "starting" && "Starting the microphone…"}
          {state.kind === "listening" && (state.note ?? "Listening…")}
          {state.kind === "receiving" &&
            `Receiving${state.remaining != null && state.remaining > 0.5 ? `, ${seconds(state.remaining)} left` : "…"}`}
          {state.kind === "received" && "Received."}
        </span>
      </div>
      {state.kind === "receiving" && (
        <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((state.progress ?? 0) * 100)}>
          <span style={{ width: `${(state.progress ?? 0.02) * 100}%` }} />
        </div>
      )}
      {state.kind === "error" && <p className="error">{state.message}</p>}
      {state.kind === "received" && <Result event={state.event} />}
    </div>
  );
}
