import { useMemo, useState } from "react";
import ConstellationScatter from "../charts/ConstellationScatter";
import LineSeriesChart from "../charts/LineSeriesChart";
import { SERIES } from "../charts/theme";
import type { DecodeResponse, SectionDiag } from "../services/api";
import { downloadBase64, formatBytes } from "../services/audio";
import { DASH, fmt, fmtDb, fmtInt, fmtPct, fmtS, isNum, shortHash } from "../services/format";
import Card from "./Card";
import DataTable from "./DataTable";
import ErrorBanner from "./ErrorBanner";
import JsonView from "./JsonView";
import NumberStat, { StatGrid } from "./NumberStat";

interface Props {
  decode: DecodeResponse;
  /** Show download / text preview for the recovered payload. */
  showPayload?: boolean;
  /** Collapse diagnostics by default. */
  compact?: boolean;
}

/** Full decode result: outcome banner, header, payload, diagnostics charts. */
export default function DecodeReport({ decode, showPayload = true, compact = false }: Props) {
  const [showDiag, setShowDiag] = useState(!compact);
  const d = decode.diagnostics ?? {};
  const h = decode.header;
  const sha = d.sha256;
  const pk = d.packets;
  const sync = d.sync;
  const ps = d.payload_section;
  const hs = d.header_section;

  return (
    <div className="flex flex-col gap-4">
      {decode.success ? (
        <ErrorBanner tone="good" title="Decoded successfully">
          <span className="num">
            SHA-256 {sha?.match ? "match" : sha ? "MISMATCH" : DASH} · {h?.filename || "(no filename)"} · {formatBytes(h?.original_length)} original /{" "}
            {formatBytes(h?.payload_length)} on air · {h?.compression ?? DASH} · {fmtS(decode.decode_time_s)}
          </span>
        </ErrorBanner>
      ) : (
        <ErrorBanner tone="error" title={`Decode failed${d.stage_failed ? ` at stage "${d.stage_failed}"` : ""}`}>
          {decode.error ?? "The receiver could not recover the payload."}
        </ErrorBanner>
      )}

      {showPayload && decode.success && (
        <Card title="Recovered payload">
          <div className="mb-3 flex flex-wrap gap-2">
            {decode.data_base64 && (
              <button className="btn btn-primary" onClick={() => downloadBase64(decode.data_base64!, h?.filename || "sonic-payload.bin")}>
                ⤓ Download reconstructed file
              </button>
            )}
            <span className="num self-center text-xs text-muted">
              type {h?.payload_type ?? DASH} · {fmtInt(h?.n_packets)} packets × {fmtInt(h?.packet_size)} B
            </span>
          </div>
          {typeof decode.text === "string" ? (
            <pre className="plain max-h-72 overflow-auto rounded-md border border-line bg-bg p-3 font-mono text-xs text-ink">{decode.text}</pre>
          ) : (
            <div className="text-xs text-muted">Binary payload (not valid UTF-8); use the download button.</div>
          )}
        </Card>
      )}

      <StatGrid cols={6}>
        <NumberStat label="Sync score" value={fmt(sync?.candidates?.[sync.selected ?? 0]?.score ?? sync?.candidates?.[0]?.score, 3)} hint="Preamble correlation score of the selected candidate" />
        <NumberStat label="Sync threshold" value={fmt(sync?.threshold, 2)} />
        <NumberStat label="Header SNR (EVM)" value={fmtDb(hs?.snr_evm_mean_db)} />
        <NumberStat label="Payload SNR (EVM)" value={fmtDb(ps?.snr_evm_mean_db)} />
        <NumberStat label="Raw BER" value={isNum(d.raw_ber) ? d.raw_ber.toExponential(2) : DASH} />
        <NumberStat
          label="Packets OK"
          value={pk ? `${pk.n_ok} / ${pk.n_packets}` : DASH}
          tone={pk ? (pk.n_ok === pk.n_packets ? "good" : "bad") : "default"}
        />
      </StatGrid>

      {h && (
        <Card title="Header">
          <StatGrid cols={6}>
            <NumberStat label="Version" value={h.version} />
            <NumberStat label="TX id" value={h.tx_id} />
            <NumberStat label="Payload type" value={h.payload_type} />
            <NumberStat label="Compression" value={h.compression} />
            <NumberStat label="Original" value={formatBytes(h.original_length)} />
            <NumberStat label="Payload" value={formatBytes(h.payload_length)} />
            <NumberStat label="Packets" value={`${h.n_packets} × ${h.packet_size} B`} />
            <NumberStat label="Modulation" value={`${h.config?.modulation ?? DASH} ${h.config?.code_rate ?? ""}`} />
            <NumberStat label="FFT / CP" value={`${h.config?.n_fft ?? DASH} / ${h.config?.cp_len ?? DASH}`} />
            <NumberStat label="Band" value={h.config ? `${(h.config.f_low / 1000).toFixed(1)}–${(h.config.f_high / 1000).toFixed(1)} kHz` : DASH} />
            <NumberStat label="SHA-256" value={<span title={h.sha256}>{shortHash(h.sha256)}</span>} tone={sha ? (sha.match ? "good" : "bad") : "default"} />
            <NumberStat label="Filename" value={h.filename || "—"} />
          </StatGrid>
        </Card>
      )}

      <button className="self-start text-xs text-accent hover:underline" onClick={() => setShowDiag((s) => !s)}>
        {showDiag ? "▾ Hide diagnostics" : "▸ Show detailed diagnostics"}
      </button>

      {showDiag && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Card title="Sync candidates" caption="Correlation peaks found while searching for the preamble; the selected one marks where the frame starts.">
            <DataTable
              dense
              maxHeight={180}
              columns={[
                { key: "i", header: "#", render: (_r: { position: number; score: number }, i: number) => i },
                { key: "pos", header: "position (samples)", render: (r) => r.position, align: "right" },
                { key: "score", header: "score", render: (r) => fmt(r.score, 4), align: "right" },
                { key: "sel", header: "selected", render: (_r, i) => (sync?.selected === i ? "✓" : "") },
              ]}
              rows={sync?.candidates ?? []}
              empty="No preamble candidates above threshold."
            />
          </Card>

          <Card title="Packet report" caption="CRC-checked packets after FEC decoding. Failed indices are listed; a single failed packet fails the file.">
            {pk ? (
              <div className="flex flex-col gap-2 text-xs">
                <StatGrid cols={4}>
                  <NumberStat label="Total" value={pk.n_packets} />
                  <NumberStat label="OK" value={pk.n_ok} tone="good" />
                  <NumberStat label="PER" value={fmtPct(pk.packet_error_rate)} tone={pk.packet_error_rate > 0 ? "bad" : "default"} />
                  <NumberStat label="Missing" value={pk.missing} tone={pk.missing > 0 ? "warn" : "default"} />
                </StatGrid>
                <div className="num">
                  CRC failed: <span className="text-bad">{pk.crc_failed.length ? pk.crc_failed.join(", ") : "none"}</span>
                </div>
                <div className="num">
                  Index mismatch: <span className="text-warn">{pk.index_mismatch.length ? pk.index_mismatch.join(", ") : "none"}</span>
                </div>
                {sha && (
                  <div className="num break-all">
                    SHA-256 expected <span className="text-muted">{sha.expected}</span>
                    <br />
                    actual <span className={sha.match ? "text-good" : "text-bad"}>{sha.actual}</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-muted">No packet stage reached.</div>
            )}
          </Card>

          {ps && <SectionCharts diag={ps} name="Payload" pilotSpacing={h?.config?.pilot_spacing} />}
          {hs && !ps && <SectionCharts diag={hs} name="Header" pilotSpacing={d.header?.config?.pilot_spacing ?? 8} />}

          <Card title="Raw diagnostics" className="xl:col-span-2">
            <div className="max-h-80 overflow-auto">
              <JsonView data={d} collapseDepth={1} />
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

/** Charts for one SectionDiag (header or payload). */
function SectionCharts({ diag, name, pilotSpacing }: { diag: SectionDiag; name: string; pilotSpacing?: number }) {
  const snrRows = useMemo(() => {
    const snr = diag.snr_evm_db;
    if (!snr) return { rows: [] as Record<string, number>[], xKey: "f", xLabel: "frequency (Hz)" };
    const freqs = diag.carrier_frequencies_hz;
    if (snr.length === freqs.length) return { rows: snr.map((v, i) => ({ f: freqs[i], snr: v })), xKey: "f", xLabel: "frequency (Hz)" };
    if (pilotSpacing && pilotSpacing > 0) {
      const dataF = freqs.filter((_, i) => i % pilotSpacing !== 0);
      if (dataF.length === snr.length) return { rows: snr.map((v, i) => ({ f: dataF[i], snr: v })), xKey: "f", xLabel: "frequency (Hz), data carriers" };
    }
    return { rows: snr.map((v, i) => ({ f: i, snr: v })), xKey: "f", xLabel: "data carrier index" };
  }, [diag, pilotSpacing]);

  const magRows = useMemo(
    () => diag.channel_magnitude_db.map((v, i) => ({ f: diag.carrier_frequencies_hz[i], mag: v, snrT: diag.snr_training_db?.[i] ?? null })),
    [diag]
  );
  const driftRows = useMemo(
    () => diag.timing_drift_samples.map((v, i) => ({ sym: i, drift: v, phase: diag.common_phase_rad[i] ?? null, gain: diag.gain_track[i] ?? null })),
    [diag]
  );

  return (
    <>
      <Card
        title={`${name}: per-carrier SNR (from EVM)`}
        subtitle={`mean ${fmtDb(diag.snr_evm_mean_db)} · training-based mean ${fmtDb(diag.snr_training_mean_db)}`}
        caption="SNR estimated from the error-vector magnitude of each data carrier's symbols. Dips reveal notches or multipath fades in the room."
      >
        {snrRows.rows.length ? (
          <LineSeriesChart data={snrRows.rows} xKey="f" series={[{ key: "snr", name: "SNR (EVM)", dot: false, color: SERIES[0] }]} xLabel={snrRows.xLabel} yLabel="SNR (dB)" xFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v))} yDomain={["auto", "auto"]} height={220} />
        ) : (
          <div className="text-xs text-muted">No EVM data for this section.</div>
        )}
      </Card>

      <Card title={`${name}: channel magnitude`} caption="Estimated channel gain per carrier from the training symbols (dB relative to the transmit level). Tilt and ripples are speaker/mic/room response.">
        <LineSeriesChart data={magRows} xKey="f" series={[{ key: "mag", name: "|H| (dB)", dot: false, color: SERIES[1] }]} xLabel="frequency (Hz)" yLabel="gain (dB)" xFormatter={(v) => `${(v / 1000).toFixed(1)}k`} yDomain={["auto", "auto"]} height={220} />
      </Card>

      <Card title={`${name}: received constellation`} caption="Equalised data symbols. Tight clusters mean a clean channel; smeared clusters mean noise or residual timing/phase error.">
        <ConstellationScatter points={diag.constellation} color={SERIES[2]} size={260} />
      </Card>

      <Card
        title={`${name}: timing drift & tracking`}
        subtitle={`window start ${diag.window_start} · refine ${diag.timing_refine_samples} samples · ${diag.n_symbols_available}/${diag.n_symbols_requested} symbols${diag.truncated ? " (truncated)" : ""}`}
        caption="Per-symbol timing drift measured from the pilots. A slope indicates a sample-rate mismatch between speaker and microphone."
      >
        <LineSeriesChart data={driftRows} xKey="sym" series={[{ key: "drift", name: "timing drift", color: SERIES[3] }]} xLabel="OFDM symbol index" yLabel="drift (samples)" yDomain={["auto", "auto"]} height={200} />
      </Card>
    </>
  );
}
