import { useCallback, useState } from "react";
import AudioPlayer from "../components/AudioPlayer";
import Card from "../components/Card";
import ChannelForm from "../components/ChannelForm";
import DecodeReport from "../components/DecodeReport";
import ErrorBanner from "../components/ErrorBanner";
import FileDrop from "../components/FileDrop";
import PageHeader from "../components/PageHeader";
import Recorder, { type Recording } from "../components/Recorder";
import api, { type ChannelModel, type DecodeResponse } from "../services/api";
import { formatBytes } from "../services/audio";
import { useAppState } from "../state/AppState";

interface Source {
  blob: Blob;
  name: string;
  origin: "upload" | "microphone";
  sampleRate?: number;
  duration_s?: number;
}

export default function ReceiverPage() {
  const { presets } = useAppState();
  const [source, setSource] = useState<Source | null>(null);
  const [channel, setChannel] = useState<ChannelModel | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DecodeResponse | null>(null);
  const [mode, setMode] = useState<"upload" | "record">("upload");

  const onFile = useCallback((f: File) => {
    setSource({ blob: f, name: f.name, origin: "upload" });
    setResult(null);
    setError(null);
  }, []);

  const onRecording = useCallback((rec: Recording) => {
    setSource({ blob: rec.blob, name: `recording-${Date.now()}.wav`, origin: "microphone", sampleRate: rec.sampleRate, duration_s: rec.duration_s });
    setResult(null);
    setError(null);
  }, []);

  const decode = async () => {
    if (!source) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.decode(source.blob, channel, source.name);
      setResult(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Receiver" subtitle="Decode a Sonic transmission from a WAV file or a live microphone recording." />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card
          title="Input audio"
          actions={
            <div className="flex rounded-md border border-line p-0.5">
              <button className={`tab ${mode === "upload" ? "tab-active" : ""}`} onClick={() => setMode("upload")}>
                Upload WAV
              </button>
              <button className={`tab ${mode === "record" ? "tab-active" : ""}`} onClick={() => setMode("record")}>
                Microphone
              </button>
            </div>
          }
        >
          {mode === "upload" ? (
            <FileDrop accept=".wav,audio/wav,audio/x-wav,audio/wave" onFile={onFile} file={source?.origin === "upload" ? (source.blob as File) : null} label="Drop a WAV file here or click to browse" hint={`PCM WAV, up to ${formatBytes(presets?.limits.max_upload_bytes)}`} />
          ) : (
            <Recorder onRecording={onRecording} />
          )}
          {source && (
            <div className="mt-3">
              <AudioPlayer blob={source.blob} filename={source.name} label={source.origin === "microphone" ? `Recording · ${source.sampleRate ?? "?"} Hz · ${source.duration_s?.toFixed(1) ?? "?"} s` : `File · ${source.name}`} />
            </div>
          )}
        </Card>

        <Card title="Simulated channel (optional)" subtitle="Synthetic impairments applied to the input before decoding — useful for stress-testing a clean file.">
          <ChannelForm value={channel} onChange={setChannel} presets={presets} />
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button className="btn btn-primary px-5 py-2" onClick={decode} disabled={!source || busy}>
              {busy ? "Decoding…" : "Decode"}
            </button>
            {!source && <span className="text-xs text-muted">Provide a recording first.</span>}
          </div>
        </Card>
      </div>

      {error && <ErrorBanner onDismiss={() => setError(null)}>{error}</ErrorBanner>}

      {result && (
        <>
          {result.input && (
            <div className="num text-xs text-muted">
              input: {result.input.sample_rate} Hz · {result.input.channels} ch · {result.input.duration_s.toFixed(2)} s
              {result.diagnostics?.input && ` · peak ${result.diagnostics.input.peak.toFixed(3)} · clipped ${(result.diagnostics.input.clipped_fraction * 100).toFixed(2)} %`}
            </div>
          )}
          <DecodeReport decode={result} />
        </>
      )}
    </div>
  );
}
