import { useRef, useState } from "react";
import { encodeFile, encodeText, type EncodeResult, type Mode } from "../lib/api";
import { audioContext, base64ToBytes, download, playWav, type Playback } from "../lib/audio";
import { bytes, seconds } from "../lib/format";
import ModePicker from "./ModePicker";

type State = { kind: "idle" } | { kind: "encoding" } | { kind: "playing"; pb: Playback } | { kind: "error"; message: string };

export default function SendPanel({ onSound }: { onSound: (on: boolean) => void }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<Mode>("balanced");
  const [state, setState] = useState<State>({ kind: "idle" });
  const [last, setLast] = useState<EncodeResult | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  const playing = state.kind === "playing";

  const pick = (f: File | null) => {
    setFile(f);
    setLast(null);
  };

  const play = async () => {
    if (playing) {
      state.pb.stop();
      return;
    }
    audioContext(); // unlock audio inside the click
    setState({ kind: "encoding" });
    try {
      const res = file ? await encodeFile(file, mode) : await encodeText(text, mode);
      setLast(res);
      const pb = await playWav(base64ToBytes(res.wav_base64));
      setState({ kind: "playing", pb });
      onSound(true);
      await pb.done;
      setState({ kind: "idle" });
    } catch (e) {
      setState({ kind: "error", message: (e as Error).message });
    } finally {
      onSound(false);
    }
  };

  return (
    <div
      className="panel"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const f = e.dataTransfer.files?.[0];
        if (f) pick(f);
      }}
    >
      {file ? (
        <div className="file">
          <span>{file.name}</span>
          <span className="muted">{bytes(file.size)}</span>
          <button className="link" onClick={() => pick(null)}>
            Remove
          </button>
        </div>
      ) : (
        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setLast(null);
          }}
          placeholder="Type a message, paste a link, or drop a file"
          rows={4}
          aria-label="Message"
        />
      )}
      <input
        ref={picker}
        type="file"
        hidden
        onChange={(e) => {
          pick(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />

      <div className="row">
        <button className="button primary" onClick={play} disabled={(!file && !text.trim()) || state.kind === "encoding"}>
          {playing ? "Stop" : state.kind === "encoding" ? "Preparing…" : "Play"}
        </button>
        <ModePicker value={mode} onChange={setMode} />
        <button className="link" onClick={() => picker.current?.click()}>
          Choose file
        </button>
      </div>

      {last && (
        <p className="muted">
          {seconds(last.info.duration_s)} of sound.{" "}
          <button className="link" onClick={() => download(base64ToBytes(last.wav_base64), "sonic.wav", "audio/wav")}>
            Save WAV
          </button>
        </p>
      )}
      {state.kind === "error" && <p className="error">{state.message}</p>}
    </div>
  );
}
