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
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  const empty = !file && !text.trim();
  const playing = state.kind === "playing";

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

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  };

  return (
    <div className="panel">
      <div
        className={`field${dragging ? " is-dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        {file ? (
          <div className="file">
            <span className="file-name">{file.name}</span>
            <span className="quiet">{bytes(file.size)}</span>
            <button className="link" onClick={() => setFile(null)}>
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
            placeholder="Type a message or paste a link"
            rows={4}
            aria-label="Message to send"
          />
        )}
        <div className="field-foot">
          <button className="link" onClick={() => picker.current?.click()}>
            {file ? "Choose another file" : "Or choose a file"}
          </button>
          <input
            ref={picker}
            type="file"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) setFile(f);
              setLast(null);
              e.target.value = "";
            }}
          />
        </div>
      </div>

      <ModePicker value={mode} onChange={setMode} />

      <div className="actions">
        <button className="primary" onClick={play} disabled={empty || state.kind === "encoding"}>
          {playing ? "Stop" : state.kind === "encoding" ? "Preparing…" : "Play sound"}
        </button>
        {last && (
          <p className="quiet">
            {seconds(last.info.duration_s)} of sound for {bytes(last.info.header.original_length)}
            {last.info.compression.algorithm !== "none" && <>, compressed to {bytes(last.info.header.payload_length)}</>}.{" "}
            <button className="link" onClick={() => download(base64ToBytes(last.wav_base64), "sonic.wav", "audio/wav")}>
              Save as WAV
            </button>
          </p>
        )}
      </div>
      {state.kind === "error" && <p className="error">Couldn’t prepare the sound: {state.message}</p>}
    </div>
  );
}

