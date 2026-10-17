import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import EnvelopeChart from "../charts/EnvelopeChart";
import AudioPlayer from "../components/AudioPlayer";
import Card from "../components/Card";
import ChannelForm from "../components/ChannelForm";
import ConfigForm from "../components/ConfigForm";
import DataTable from "../components/DataTable";
import DecodeReport from "../components/DecodeReport";
import ErrorBanner from "../components/ErrorBanner";
import FileDrop from "../components/FileDrop";
import NumberStat, { StatGrid } from "../components/NumberStat";
import PageHeader from "../components/PageHeader";
import api, { type ChannelModel, type ConfigModel, type EncodeResponse, type EstimateResponse } from "../services/api";
import { formatBytes } from "../services/audio";
import { DASH, fmt, fmtBps, fmtDb, fmtInt, fmtS, shortHash } from "../services/format";
import { useAppState } from "../state/AppState";

const SAMPLE_TEXT = "Hello from Sonic. This text is being sent through the air as an OFDM audio signal.";

export default function TransmitterPage() {
  const { presets, setLastEncode } = useAppState();
  const navigate = useNavigate();

  const [mode, setMode] = useState<"text" | "file">("text");
  const [text, setText] = useState(SAMPLE_TEXT);
  const [file, setFile] = useState<File | null>(null);
  const [config, setConfig] = useState<ConfigModel>({ preset: "default" });
  const [compression, setCompression] = useState("auto");
  const [payloadType, setPayloadType] = useState("text");
  const [amplitude, setAmplitude] = useState(0.8);
  const [channel, setChannel] = useState<ChannelModel | null>(null);

  const [estimate, setEstimate] = useState<EstimateResponse | null>(null);
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EncodeResponse | null>(null);
  const [sentToExplorer, setSentToExplorer] = useState(false);

  const nBytes = useMemo(() => (mode === "file" ? file?.size ?? 0 : new TextEncoder().encode(text).length), [mode, file, text]);
  const maxPayload = presets?.limits.max_payload_bytes ?? 4 * 1024 * 1024;

  // Debounced live estimate.
  const estimateAbort = useRef<AbortController | null>(null);
  useEffect(() => {
    const t = setTimeout(() => {
      estimateAbort.current?.abort();
      const ac = new AbortController();
      estimateAbort.current = ac;
      api
        .estimate(config, Math.min(nBytes, maxPayload), ac.signal)
        .then((r) => {
          setEstimate(r);
          setEstimateError(null);
        })
        .catch((e: Error) => {
          if (e.name !== "AbortError") setEstimateError(e.message);
        });
    }, 300);
    return () => clearTimeout(t);
  }, [config, nBytes, maxPayload]);

  useEffect(() => {
    if (mode === "file" && payloadType === "text") setPayloadType("binary");
    if (mode === "text" && payloadType === "binary") setPayloadType("text");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  const generate = async () => {
    setBusy(true);
    setError(null);
    setSentToExplorer(false);
    try {
      const r =
        mode === "file"
          ? await api.encodeFile({ file: file!, config, compression, payload_type: payloadType, amplitude, channel })
          : await api.encode({ text, config, compression, payload_type: payloadType, amplitude, channel });
      setResult(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const sendToExplorer = () => {
    if (!result) return;
    setLastEncode(result, mode === "file" ? file?.name ?? "file" : `text (${nBytes} B)`);
    setSentToExplorer(true);
  };

  const canGenerate = !busy && (mode === "text" ? text.length > 0 : !!file) && nBytes <= maxPayload;
  const est = estimate?.estimate;
  const cfg = estimate?.config;
  const compTable = result ? Object.entries(result.info.compression.candidates).sort((a, b) => a[1] - b[1]) : [];

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Transmitter" subtitle="Encode text or a file into an OFDM audio waveform." />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex flex-col gap-4">
          <Card
            title="Payload"
            actions={
              <div className="flex rounded-md border border-line p-0.5">
                <button className={`tab ${mode === "text" ? "tab-active" : ""}`} onClick={() => setMode("text")}>
                  Text
                </button>
                <button className={`tab ${mode === "file" ? "tab-active" : ""}`} onClick={() => setMode("file")}>
                  File
                </button>
              </div>
            }
          >
            {mode === "text" ? (
              <textarea className="input min-h-[120px] font-sans" value={text} onChange={(e) => setText(e.target.value)} placeholder="Type the message to transmit…" />
            ) : (
              <FileDrop file={file} onFile={setFile} hint={`Any file up to ${formatBytes(maxPayload)}`} />
            )}
            <div className="num mt-2 flex flex-wrap gap-4 text-xs text-muted">
              <span>
                size <span className={nBytes > maxPayload ? "text-bad" : "text-ink"}>{formatBytes(nBytes)}</span>
              </span>
              <span>
                limit <span className="text-ink">{formatBytes(maxPayload)}</span>
              </span>
            </div>
          </Card>

          <Card title="OFDM configuration">
            <ConfigForm value={config} onChange={setConfig} presets={presets} />
            <div className="mt-3 grid grid-cols-1 gap-3 border-t border-line pt-3 sm:grid-cols-3">
              <div>
                <label className="label">Compression</label>
                <select className="input" value={compression} onChange={(e) => setCompression(e.target.value)}>
                  <option value="auto">auto (smallest)</option>
                  {(presets?.compression ?? ["none", "zlib", "lzma", "zstd", "codeaware"]).map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label">Payload type</label>
                <select className="input" value={payloadType} onChange={(e) => setPayloadType(e.target.value)}>
                  {(presets?.payload_types ?? ["binary", "text", "json", "url", "contact", "code"]).map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label">
                  Amplitude <span className="num text-ink">{amplitude.toFixed(2)}</span>
                </label>
                <input type="range" className="range mt-2" min={0.05} max={1} step={0.01} value={amplitude} onChange={(e) => setAmplitude(Number(e.target.value))} />
              </div>
            </div>
          </Card>

          <Card title="Simulated channel (optional)" subtitle="Applies a synthetic channel model to the generated audio and decodes it server-side.">
            <ChannelForm value={channel} onChange={setChannel} presets={presets} />
          </Card>

          <div className="flex flex-wrap items-center gap-3">
            <button className="btn btn-primary px-5 py-2" onClick={generate} disabled={!canGenerate}>
              {busy ? "Generating…" : "Generate waveform"}
            </button>
            {error && <ErrorBanner onDismiss={() => setError(null)}>{error}</ErrorBanner>}
          </div>
        </div>

        {/* Live estimate */}
        <Card title="Live estimate" subtitle="Recomputed from the configuration and payload size (before compression)." className="xl:sticky xl:top-4 xl:self-start">
          {estimateError && <ErrorBanner tone="warn">{estimateError}</ErrorBanner>}
          <StatGrid cols={2}>
            <NumberStat label="Payload" value={formatBytes(est?.payload_bytes)} />
            <NumberStat label="Est. duration" value={fmtS(est?.duration_s)} />
            <NumberStat label="Net bitrate" value={fmtBps(est?.net_bitrate_bps)} hint="payload bits / total airtime incl. preamble+header" />
            <NumberStat label="Info bitrate" value={fmtBps(est?.info_bitrate_bps)} hint="PHY rate after FEC" />
            <NumberStat label="Raw bitrate" value={fmtBps(est?.raw_bitrate_bps)} hint="PHY rate before FEC" />
            <NumberStat label="Spectral eff." value={fmt(est?.spectral_efficiency, 3)} unit="bit/s/Hz" />
            <NumberStat label="Header symbols" value={fmtInt(est?.n_header_symbols)} />
            <NumberStat label="Payload symbols" value={fmtInt(est?.n_payload_symbols)} />
          </StatGrid>
          <div className="mt-3 border-t border-line pt-3">
            <div className="card-title mb-2">Resolved configuration</div>
            <StatGrid cols={2}>
              <NumberStat label="Modulation" value={cfg ? `${cfg.modulation} · ${cfg.code_rate}` : DASH} />
              <NumberStat label="Band" value={cfg ? `${(cfg.f_low / 1000).toFixed(1)}–${(cfg.f_high / 1000).toFixed(1)} kHz` : DASH} />
              <NumberStat label="Active carriers" value={fmtInt(cfg?.n_active_carriers)} />
              <NumberStat label="Data / pilot" value={cfg ? `${cfg.n_enabled_data_carriers} / ${cfg.n_pilot_carriers}` : DASH} />
              <NumberStat label="Carrier spacing" value={fmt(cfg?.carrier_spacing_hz, 2)} unit="Hz" />
              <NumberStat label="Symbol" value={fmtS(cfg?.symbol_duration_s, 3)} />
              <NumberStat label="FFT / CP" value={cfg ? `${cfg.n_fft} / ${cfg.cp_len}` : DASH} />
              <NumberStat label="Bits / symbol" value={fmtInt(cfg?.bits_per_ofdm_symbol)} />
            </StatGrid>
          </div>
        </Card>
      </div>

      {result && (
        <>
          <Card
            title="Generated transmission"
            actions={
              <>
                <button className="btn" onClick={sendToExplorer}>
                  {sentToExplorer ? "✓ Sent to Explorer" : "Send to Explorer"}
                </button>
                {sentToExplorer && (
                  <button className="btn btn-primary" onClick={() => navigate("/explorer")}>
                    Open Explorer →
                  </button>
                )}
              </>
            }
          >
            <StatGrid cols={6}>
              <NumberStat label="Duration" value={fmtS(result.info.duration_s)} />
              <NumberStat label="PAPR" value={fmtDb(result.info.papr_db)} hint="Peak-to-average power ratio" />
              <NumberStat label="Peak / RMS" value={`${fmt(result.info.peak, 2)} / ${fmt(result.info.rms, 3)}`} />
              <NumberStat label="Net bitrate" value={fmtBps(result.info.net_bitrate_bps)} />
              <NumberStat label="Info / coded bits" value={`${fmtInt(result.info.info_bits)} / ${fmtInt(result.info.coded_bits)}`} />
              <NumberStat label="Encode time" value={fmtS(result.info.encode_time_s, 3)} />
              <NumberStat label="Compression" value={result.info.compression.algorithm} />
              <NumberStat label="Ratio" value={`${fmt(result.info.compression.ratio, 3)}×`} />
              <NumberStat label="Packets" value={`${result.info.header.n_packets} × ${result.info.header.packet_size} B`} />
              <NumberStat label="Symbols (hdr / pay)" value={`${result.info.n_header_symbols} / ${result.info.n_payload_symbols}`} />
              <NumberStat label="TX id" value={result.info.header.tx_id} />
              <NumberStat label="SHA-256" value={<span title={result.info.header.sha256}>{shortHash(result.info.header.sha256)}</span>} />
            </StatGrid>

            <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
              <div>
                <div className="card-title mb-2">Waveform envelope</div>
                <EnvelopeChart waveform={result.analysis.waveform} sections={result.info.sections} />
              </div>
              <div>
                <div className="card-title mb-2">Compression candidates</div>
                <DataTable
                  dense
                  columns={[
                    { key: "a", header: "algorithm", render: (r: [string, number]) => (r[0] === result.info.compression.algorithm ? <span className="text-good">{r[0]} ✓</span> : r[0]) },
                    { key: "b", header: "bytes", render: (r) => fmtInt(r[1]), align: "right" },
                    { key: "r", header: "ratio", render: (r) => `${(result.info.compression.original_size / Math.max(1, r[1])).toFixed(3)}×`, align: "right" },
                  ]}
                  rows={compTable}
                />
              </div>
            </div>

            <div className="mt-4">
              <AudioPlayer wavBase64={result.wav_base64} filename={`sonic-tx-${result.info.header.tx_id}.wav`} label="Transmit audio" />
            </div>
          </Card>

          {result.decode && (
            <Card title="Simulated channel decode" subtitle={`Channel preset: ${result.channel?.name ?? DASH} · SNR ${result.channel?.snr_db ?? "none"} dB (synthetic model)`}>
              {result.received_wav_base64 && (
                <div className="mb-4">
                  <AudioPlayer wavBase64={result.received_wav_base64} filename={`sonic-rx-${result.info.header.tx_id}.wav`} label="Received audio (after channel)" />
                </div>
              )}
              <DecodeReport decode={result.decode} compact />
            </Card>
          )}
        </>
      )}
    </div>
  );
}
