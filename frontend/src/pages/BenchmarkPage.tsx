import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import GroupedBarChart from "../charts/GroupedBarChart";
import LineSeriesChart, { type LineSeries } from "../charts/LineSeriesChart";
import { modulationColor, MODULATION_ORDER, SERIES } from "../charts/theme";
import Card from "../components/Card";
import ChannelForm from "../components/ChannelForm";
import DataTable, { type Column } from "../components/DataTable";
import ErrorBanner from "../components/ErrorBanner";
import NumberStat, { StatGrid } from "../components/NumberStat";
import PageHeader from "../components/PageHeader";
import api, {
  type BenchmarkJob,
  type BenchmarkJobSummary,
  type BenchmarkProgress,
  type BenchmarkWsMessage,
  type ChannelModel,
  type ExperimentName,
  type StoredResults,
  type SummaryRow,
  type ThresholdEntry,
  type TrialRecord,
} from "../services/api";
import { DASH, fmt, fmtPct, fmtS, isNum } from "../services/format";
import { useAppState } from "../state/AppState";

const EXPERIMENTS: { id: ExperimentName; label: string; desc: string }[] = [
  { id: "snr_sweep", label: "SNR sweep", desc: "Throughput, BER and success vs channel SNR for each modulation (AWGN)." },
  { id: "carrier_density", label: "Carrier density", desc: "Same bandwidth split into 16…1024 carriers; what changes and what does not." },
  { id: "file_sizes", label: "File sizes", desc: "Transmission time and net throughput as payload size grows." },
  { id: "channels", label: "Channel presets", desc: "Each OFDM preset across the synthetic room models." },
  { id: "compression", label: "Compression", desc: "Bits per byte achieved by each algorithm on sample files by language." },
  { id: "adaptive", label: "Adaptive bit-loading", desc: "Fixed default vs best fixed vs adaptive per-band modulation per channel." },
];

const BER_FLOOR = 1e-6;

export default function BenchmarkPage() {
  const [tab, setTab] = useState<"run" | "stored">("run");
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Benchmark Laboratory"
        subtitle="Run reproducible experiments against synthetic channels and compare with stored results."
        actions={
          <div className="flex rounded-md border border-line p-0.5">
            <button className={`tab ${tab === "run" ? "tab-active" : ""}`} onClick={() => setTab("run")}>
              Run experiment
            </button>
            <button className={`tab ${tab === "stored" ? "tab-active" : ""}`} onClick={() => setTab("stored")}>
              Stored results
            </button>
          </div>
        }
      />
      {tab === "run" ? <RunTab /> : <StoredTab />}
    </div>
  );
}

// ------------------------------------------------------------------ run tab

function RunTab() {
  const { presets } = useAppState();
  const [experiment, setExperiment] = useState<ExperimentName>("snr_sweep");
  const [trials, setTrials] = useState(2);
  const [snrs, setSnrs] = useState("0, 3, 6, 9, 12, 15, 18, 21, 24");
  const [mods, setMods] = useState<string[]>(["bpsk", "qpsk", "16qam", "64qam"]);
  const [carrierCounts, setCarrierCounts] = useState("16, 32, 64, 128, 256, 512, 1024");
  const [channel, setChannel] = useState<ChannelModel | null>({ preset: "awgn", snr_db: 20 });
  const [payloadBytes, setPayloadBytes] = useState(1024);

  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [progress, setProgress] = useState<BenchmarkProgress>({});
  const [records, setRecords] = useState<TrialRecord[]>([]);
  const [job, setJob] = useState<BenchmarkJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<BenchmarkJobSummary[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const refreshJobs = useCallback(() => {
    api
      .benchmarkJobs()
      .then((j) => setJobs([...j].sort((a, b) => b.created - a.created)))
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    refreshJobs();
  }, [refreshJobs]);
  useEffect(() => () => wsRef.current?.close(), []);

  const parseList = (s: string) => s.split(/[,\s]+/).map((x) => Number(x)).filter((x) => Number.isFinite(x));

  const loadFinished = useCallback(
    async (id: string) => {
      try {
        const j = await api.benchmarkJob(id);
        setJob(j);
        setRecords(j.records);
        setStatus(j.status === "running" ? "running" : j.status);
        setProgress(j.progress ?? {});
        if (j.status === "error") setError(j.error ?? "Benchmark failed.");
      } catch (e) {
        setError((e as Error).message);
      }
      refreshJobs();
    },
    [refreshJobs]
  );

  const attach = useCallback(
    (id: string) => {
      wsRef.current?.close();
      setJobId(id);
      setJob(null);
      setRecords([]);
      setError(null);
      setStatus("running");
      setProgress({});
      const ws = api.benchmarkSocket(id);
      wsRef.current = ws;
      ws.onmessage = (ev) => {
        try {
          const m = JSON.parse(ev.data) as BenchmarkWsMessage & { error?: string | null };
          if (m.error && !m.status) {
            setError(m.error);
            setStatus("error");
            return;
          }
          if (m.records?.length) setRecords((r) => [...r, ...m.records]);
          if (m.progress) setProgress(m.progress);
          if (m.status && m.status !== "running") {
            setStatus(m.status);
            if (m.status === "error") setError(m.error ?? "Benchmark failed.");
            void loadFinished(id);
          }
        } catch {
          /* ignore malformed frame */
        }
      };
      ws.onerror = () => {
        // Fall back to polling the job once.
        void loadFinished(id);
      };
      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
      };
    },
    [loadFinished]
  );

  const start = async () => {
    setError(null);
    try {
      const req = {
        experiment,
        trials,
        payload_bytes: payloadBytes,
        snrs: experiment === "snr_sweep" ? parseList(snrs) : undefined,
        modulations: experiment === "snr_sweep" || experiment === "carrier_density" ? mods : undefined,
        carrier_counts: experiment === "carrier_density" ? parseList(carrierCounts).map((x) => Math.round(x)) : undefined,
        channel: channel ?? undefined,
      };
      const { job_id } = await api.benchmarkStart(req);
      attach(job_id);
      refreshJobs();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const pct = progress.total ? Math.min(100, (100 * (progress.done ?? 0)) / progress.total) : status === "done" ? 100 : 0;
  const expMeta = EXPERIMENTS.find((e) => e.id === experiment)!;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card title="Experiment">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="label">Type</label>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
                {EXPERIMENTS.map((e) => (
                  <button key={e.id} className={`rounded-md border px-3 py-2 text-left text-sm ${experiment === e.id ? "border-accent bg-accent/10 text-ink" : "border-line text-ink2 hover:border-ink2"}`} onClick={() => setExperiment(e.id)}>
                    {e.label}
                  </button>
                ))}
              </div>
              <p className="mt-1 text-xs text-muted">{expMeta.desc}</p>
            </div>
            <div>
              <label className="label">Trials per point (1–10)</label>
              <input className="input" type="number" min={1} max={10} value={trials} onChange={(e) => setTrials(Math.max(1, Math.min(10, Number(e.target.value) || 1)))} />
            </div>
            <div>
              <label className="label">Payload bytes (16–65536)</label>
              <input className="input" type="number" min={16} max={65536} value={payloadBytes} onChange={(e) => setPayloadBytes(Math.max(16, Math.min(65536, Number(e.target.value) || 16)))} />
            </div>
            {experiment === "snr_sweep" && (
              <div className="sm:col-span-2">
                <label className="label">SNR list (dB)</label>
                <input className="input" value={snrs} onChange={(e) => setSnrs(e.target.value)} />
              </div>
            )}
            {(experiment === "snr_sweep" || experiment === "carrier_density") && (
              <div className="sm:col-span-2">
                <label className="label">Modulations</label>
                <div className="flex flex-wrap gap-3">
                  {(presets?.modulations ?? MODULATION_ORDER).map((m) => (
                    <label key={m} className="num flex items-center gap-1 text-sm">
                      <input type="checkbox" checked={mods.includes(m)} onChange={(e) => setMods((cur) => (e.target.checked ? [...cur, m] : cur.filter((x) => x !== m)))} />
                      {m}
                    </label>
                  ))}
                </div>
              </div>
            )}
            {experiment === "carrier_density" && (
              <div className="sm:col-span-2">
                <label className="label">Carrier counts</label>
                <input className="input" value={carrierCounts} onChange={(e) => setCarrierCounts(e.target.value)} />
              </div>
            )}
            {(experiment === "carrier_density" || experiment === "file_sizes") && (
              <div className="sm:col-span-2 rounded-md border border-line bg-bg/40 p-3">
                <div className="card-title mb-2">Channel (synthetic)</div>
                <ChannelForm value={channel ?? { preset: "awgn" }} onChange={(v) => setChannel(v)} presets={presets} alwaysOn compact />
              </div>
            )}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button className="btn btn-primary px-5 py-2" onClick={start} disabled={status === "running" || ((experiment === "snr_sweep" || experiment === "carrier_density") && mods.length === 0)}>
              {status === "running" ? "Running…" : "Start benchmark"}
            </button>
            {jobId && (
              <span className="num text-xs text-muted">
                job <span className="text-ink">{jobId}</span>
              </span>
            )}
          </div>
        </Card>

        <Card title="Jobs on the server" actions={<button className="btn px-2 py-1 text-xs" onClick={refreshJobs}>↻</button>}>
          <DataTable
            dense
            maxHeight={260}
            columns={[
              { key: "id", header: "id", render: (j: BenchmarkJobSummary) => <button className="text-accent hover:underline" onClick={() => (j.status === "running" ? attach(j.id) : (setJobId(j.id), void loadFinished(j.id)))}>{j.id}</button> },
              { key: "exp", header: "experiment", render: (j) => j.request?.experiment ?? DASH },
              { key: "st", header: "status", render: (j) => <span className={j.status === "done" ? "text-good" : j.status === "error" ? "text-bad" : "text-warn"}>{j.status}</span> },
              { key: "pr", header: "progress", render: (j) => (j.progress?.total ? `${j.progress.done}/${j.progress.total}` : DASH), align: "right" },
            ]}
            rows={jobs}
            empty="No jobs yet in this server session."
          />
        </Card>
      </div>

      {error && <ErrorBanner onDismiss={() => setError(null)}>{error}</ErrorBanner>}

      {jobId && (
        <Card
          title="Progress"
          subtitle={progress.experiment ? `${progress.experiment} · ${progress.done ?? 0} / ${progress.total ?? "?"} trials` : status}
          actions={
            status === "done" && (
              <>
                <a className="btn" href={api.benchmarkExportUrl(jobId, "csv")} download>
                  ⤓ CSV
                </a>
                <a className="btn" href={api.benchmarkExportUrl(jobId, "json")} download>
                  ⤓ JSON
                </a>
              </>
            )
          }
        >
          <div className="h-2 w-full overflow-hidden rounded bg-line">
            <div className={`h-full transition-[width] ${status === "error" ? "bg-bad" : status === "done" ? "bg-good" : "bg-accent"}`} style={{ width: `${pct}%` }} />
          </div>
          <div className="mt-3">
            <RecordsTable records={records} experiment={(job?.request?.experiment as ExperimentName) ?? experiment} />
          </div>
        </Card>
      )}

      {job && job.status === "done" && <ExperimentCharts experiment={job.request.experiment} summary={job.summary} records={job.records} />}
    </div>
  );
}

// --------------------------------------------------------------- stored tab

function StoredTab() {
  const [results, setResults] = useState<StoredResults | null>(null);
  const [plots, setPlots] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => {
    api
      .results()
      .then((r) => {
        setResults(r);
        const keys = Object.keys(r);
        setSel((s) => s ?? keys[0] ?? null);
      })
      .catch((e: Error) => setError(e.message));
    api
      .resultPlots()
      .then(setPlots)
      .catch(() => setPlots([]));
  }, []);

  const keys = results ? Object.keys(results) : [];
  const cur = sel && results ? results[sel] : null;

  return (
    <div className="flex flex-col gap-4">
      {error && <ErrorBanner>{error}</ErrorBanner>}
      {results && keys.length === 0 && <Card>
        <div className="py-6 text-center text-sm text-muted">No stored result files found on the server (benchmarks/results). Run <span className="num">sonic benchmark</span> to produce them.</div>
      </Card>}
      {keys.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {keys.map((k) => (
            <button key={k} className={`rounded-md border px-3 py-1.5 text-sm ${sel === k ? "border-accent bg-accent/10 text-ink" : "border-line text-ink2 hover:border-ink2"}`} onClick={() => setSel(k)}>
              {k}
            </button>
          ))}
        </div>
      )}
      {sel && cur && sel === "thresholds" && <ThresholdsView data={cur as Record<string, ThresholdEntry | unknown>} />}
      {sel && cur && sel !== "thresholds" && (
        <>
          {"meta" in cur && cur.meta ? (
            <div className="num text-xs text-muted">
              {Object.entries(cur.meta as Record<string, unknown>)
                .filter(([, v]) => typeof v !== "object")
                .map(([k, v]) => `${k}: ${String(v)}`)
                .join(" · ")}
            </div>
          ) : null}
          <ExperimentCharts experiment={sel} summary={(cur as { summary?: SummaryRow[] | null }).summary ?? null} records={(cur as { records?: TrialRecord[] }).records ?? []} />
          <Card title="Records">
            <RecordsTable records={(cur as { records?: TrialRecord[] }).records ?? []} experiment={sel as ExperimentName} />
          </Card>
        </>
      )}
      {plots.length > 0 && (
        <Card title="Pre-rendered plots" subtitle="PNG files produced by the CLI benchmark runner.">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {plots.map((p) => (
              <a key={p} href={api.resultPlotUrl(p)} target="_blank" rel="noreferrer" className="rounded-md border border-line bg-bg p-2 hover:border-accent">
                <img src={api.resultPlotUrl(p)} alt={p} className="w-full rounded" loading="lazy" />
                <div className="num mt-1 truncate text-xs text-muted">{p}</div>
              </a>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function ThresholdsView({ data }: { data: Record<string, ThresholdEntry | unknown> }) {
  const entries = Object.entries(data).filter(([k, v]) => k !== "_meta" && v && typeof v === "object" && "sweep" in (v as object)) as [string, ThresholdEntry][];
  const rows = useMemo(() => {
    // One line per modulation|rate: estimated SNR vs channel SNR.
    const xs = new Set<number>();
    entries.forEach(([, e]) => e.sweep.forEach((s) => xs.add(s.snr_db)));
    return Array.from(xs)
      .sort((a, b) => a - b)
      .map((x) => {
        const row: Record<string, unknown> = { snr: x };
        entries.forEach(([k, e]) => {
          const p = e.sweep.find((s) => s.snr_db === x);
          row[k] = p?.snr_est_db ?? null;
        });
        return row;
      });
  }, [entries]);
  return (
    <div className="flex flex-col gap-4">
      <Card title="Decoding thresholds" caption="Lowest channel SNR at which each modulation / code-rate pair decoded without error, with the receiver's own SNR estimate at that point.">
        <DataTable
          dense
          columns={[
            { key: "m", header: "modulation", render: (r: [string, ThresholdEntry]) => r[1].modulation },
            { key: "r", header: "code rate", render: (r) => r[1].code_rate },
            { key: "t", header: "threshold channel SNR (dB)", render: (r) => fmt(r[1].threshold_channel_snr_db, 1), align: "right" },
            { key: "e", header: "threshold est. SNR (dB)", render: (r) => fmt(r[1].threshold_est_snr_db, 1), align: "right" },
            { key: "ok", header: "sweep (ok)", render: (r) => r[1].sweep.map((s) => (s.ok ? "●" : "·")).join("") },
          ]}
          rows={entries}
        />
      </Card>
      <Card title="Estimated vs channel SNR" caption="The receiver's EVM-based SNR estimate against the true synthetic channel SNR for every sweep point.">
        <LineSeriesChart data={rows} xKey="snr" series={entries.slice(0, 8).map(([k], i) => ({ key: k, name: k, color: SERIES[i % SERIES.length] }))} xLabel="channel SNR (dB)" yLabel="estimated SNR (dB)" yDomain={["auto", "auto"]} height={280} />
        {entries.length > 8 && <p className="mt-1 text-xs text-muted">Showing the first 8 of {entries.length} series.</p>}
      </Card>
    </div>
  );
}

// --------------------------------------------------------------- records

function RecordsTable({ records, experiment }: { records: TrialRecord[]; experiment: ExperimentName | string }) {
  const cols = useMemo<Column<TrialRecord>[]>(() => {
    if (experiment === "compression") {
      return [
        { key: "sample", header: "sample", render: (r) => r.sample ?? DASH },
        { key: "lang", header: "language", render: (r) => r.language ?? DASH },
        { key: "algo", header: "algorithm", render: (r) => r.algorithm ?? DASH },
        { key: "src", header: "source B", render: (r) => r.source_bytes ?? DASH, align: "right" },
        { key: "cmp", header: "compressed B", render: (r) => r.compressed_bytes ?? DASH, align: "right" },
        { key: "bpb", header: "bits/byte", render: (r) => fmt(r.bits_per_byte, 3), align: "right" },
        { key: "ratio", header: "ratio", render: (r) => fmt(r.compression_ratio, 3), align: "right" },
        { key: "ok", header: "lossless", render: (r) => (r.lossless ? "✓" : "✕") },
        { key: "ct", header: "compress", render: (r) => fmtS(r.compress_time_s, 3), align: "right" },
      ];
    }
    const base: Column<TrialRecord>[] = [
      { key: "label", header: "label", render: (r) => r.label ?? DASH },
      { key: "ch", header: "channel", render: (r) => r.channel ?? DASH },
      { key: "snr", header: "SNR dB", render: (r) => (isNum(r.snr_db) ? r.snr_db : DASH), align: "right" },
      { key: "mod", header: "mod · rate", render: (r) => `${r.modulation ?? DASH} ${r.code_rate ?? ""}` },
      { key: "nc", header: "carriers", render: (r) => r.n_carriers ?? DASH, align: "right" },
      { key: "bytes", header: "bytes", render: (r) => r.source_bytes ?? DASH, align: "right" },
      { key: "dur", header: "duration", render: (r) => fmtS(r.duration_s), align: "right" },
      { key: "net", header: "net bit/s", render: (r) => fmt(r.net_bitrate_bps, 0), align: "right" },
      { key: "ber", header: "raw BER", render: (r) => (isNum(r.raw_ber) ? r.raw_ber.toExponential(2) : DASH), align: "right" },
      { key: "per", header: "PER", render: (r) => fmtPct(r.packet_error_rate), align: "right" },
      { key: "est", header: "SNR est", render: (r) => fmt(r.snr_est_db, 1), align: "right" },
      { key: "ok", header: "ok", render: (r) => <span className={r.success ? "text-good" : "text-bad"}>{r.success ? "✓" : "✕"}</span> },
    ];
    if (experiment === "carrier_density") base.splice(4, 0, { key: "tc", header: "target", render: (r) => r.target_carriers ?? DASH, align: "right" });
    if (experiment === "channels") base.splice(1, 0, { key: "preset", header: "preset", render: (r) => r.preset ?? DASH });
    if (experiment === "adaptive") base.splice(1, 0, { key: "scheme", header: "scheme", render: (r) => r.scheme ?? DASH });
    return base;
  }, [experiment]);
  return <DataTable dense columns={cols} rows={records} maxHeight={320} empty="Waiting for the first trial…" />;
}

// ----------------------------------------------------------------- charts

/** Pivot summary rows into {x, <series>: value, <series>_err: ci95} rows. */
function pivot(summary: SummaryRow[], xKey: string, seriesKey: string | null, valueKey: string, errKey?: string) {
  const xs = new Map<number | string, Record<string, unknown>>();
  const series = new Set<string>();
  for (const r of summary) {
    const x = r[xKey] as number | string | null | undefined;
    if (x === null || x === undefined) continue;
    const s = seriesKey ? String(r[seriesKey] ?? "") : "value";
    series.add(s);
    const row = xs.get(x) ?? { x };
    const v = r[valueKey];
    row[s] = isNum(v) ? v : null;
    if (errKey) {
      const e = r[errKey];
      // Omit the bar when the CI is zero or float noise (recharts draws degenerate caps otherwise).
      const vv = isNum(v) ? Math.abs(v) : 0;
      row[`${s}_err`] = isNum(e) && e > Math.max(1e-9, vv * 1e-6) ? e : undefined;
    }
    xs.set(x, row);
  }
  const rows = Array.from(xs.values()).sort((a, b) => (typeof a.x === "number" && typeof b.x === "number" ? a.x - b.x : String(a.x).localeCompare(String(b.x))));
  return { rows, series: Array.from(series) };
}

function modSeries(names: string[], withErr = true, dashed = false): LineSeries[] {
  const ordered = [...names].sort((a, b) => MODULATION_ORDER.indexOf(a) - MODULATION_ORDER.indexOf(b));
  return ordered.map((m) => ({ key: m, name: m, color: modulationColor(m), errorKey: withErr ? `${m}_err` : undefined, dashed }));
}

function ExperimentCharts({ experiment, summary, records }: { experiment: string; summary: SummaryRow[] | null; records: TrialRecord[] }) {
  const s = summary ?? [];

  const spectral = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of s) if (r.modulation && isNum(r.spectral_efficiency) && !m.has(r.modulation)) m.set(r.modulation, r.spectral_efficiency);
    return Array.from(m.entries())
      .sort((a, b) => MODULATION_ORDER.indexOf(a[0]) - MODULATION_ORDER.indexOf(b[0]))
      .map(([modulation, se]) => ({ modulation, se }));
  }, [s]);

  if (experiment === "compression") return <CompressionCharts records={records} />;
  if (!summary || summary.length === 0) return <Card><div className="text-sm text-muted">No summary available for this run.</div></Card>;

  if (experiment === "snr_sweep") {
    const tp = pivot(s, "snr_db", "modulation", "net_bitrate_bps_mean", "net_bitrate_bps_ci95");
    const ber = pivot(s, "snr_db", "modulation", "raw_ber_mean");
    const berRows = ber.rows.map((r) => {
      const o: Record<string, unknown> = { x: r.x };
      for (const k of ber.series) o[k] = isNum(r[k]) ? Math.max(BER_FLOOR, r[k] as number) : null;
      return o;
    });
    const sr = pivot(s, "snr_db", "modulation", "success_rate");
    return (
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Net throughput vs SNR" caption="Mean net bit rate (payload bits over total airtime) per modulation, ±95% CI across trials. Failed trials count as 0 bit/s.">
          <LineSeriesChart data={tp.rows} xKey="x" series={modSeries(tp.series)} xLabel="channel SNR (dB)" yLabel="net bit rate (bit/s)" />
        </Card>
        <Card title="Raw BER vs SNR" caption={`Bit error rate before FEC on a log axis. Points with BER = 0 are drawn at the ${BER_FLOOR.toExponential(0)} floor.`}>
          <LineSeriesChart data={berRows} xKey="x" series={modSeries(ber.series, false)} xLabel="channel SNR (dB)" yLabel="raw BER" yScale="log" yDomain={[BER_FLOOR, 1]} yFormatter={(v) => v.toExponential(0)} />
        </Card>
        <Card title="Success rate vs SNR" caption="Fraction of trials where the file was reconstructed bit-exact (SHA-256 match).">
          <LineSeriesChart data={sr.rows} xKey="x" series={modSeries(sr.series, false)} xLabel="channel SNR (dB)" yLabel="success rate" yDomain={[0, 1]} yFormatter={(v) => v.toFixed(2)} />
        </Card>
        <SpectralCard rows={spectral} />
      </div>
    );
  }

  if (experiment === "carrier_density") {
    const tp = pivot(s, "target_carriers", "modulation", "net_bitrate_bps_mean", "net_bitrate_bps_ci95");
    const phy = pivot(s, "target_carriers", "modulation", "info_bitrate_bps");
    const merged = tp.rows.map((r) => {
      const p = phy.rows.find((q) => q.x === r.x) ?? {};
      const o: Record<string, unknown> = { ...r };
      for (const m of phy.series) o[`${m}_phy`] = p[m] ?? null;
      return o;
    });
    const series: LineSeries[] = [
      ...modSeries(tp.series),
      ...modSeries(phy.series, false, true).map((x) => ({ ...x, key: `${x.key}_phy`, name: `${x.name} PHY info rate` })),
    ];
    const papr = pivot(s, "target_carriers", "modulation", "papr_db_mean", "papr_db_ci95");
    const dur = pivot(s, "target_carriers", "modulation", "duration_s_mean", "duration_s_ci95");
    return (
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card
          title="Throughput vs carrier count"
          className="xl:col-span-2"
          caption="Solid: measured net throughput (±95% CI). Dashed: the PHY information rate. At equal bandwidth the PHY information rate is identical by construction (same bits per Hz per second), and only channel effects — echo tolerance via the cyclic prefix, PAPR, and drift sensitivity — differ between carrier counts."
        >
          <LineSeriesChart data={merged} xKey="x" series={series} xLabel="number of carriers (log scale)" yLabel="bit rate (bit/s)" height={320} xScale="log" xFormatter={(v) => String(v)} />
        </Card>
        <Card title="PAPR vs carrier count" caption="Peak-to-average power ratio grows with the number of carriers, which limits how loud the signal can be played without clipping.">
          <LineSeriesChart data={papr.rows} xKey="x" series={modSeries(papr.series)} xLabel="number of carriers (log scale)" yLabel="PAPR (dB)" yDomain={["auto", "auto"]} xScale="log" xFormatter={(v) => String(v)} />
        </Card>
        <Card title="Transmission time vs carrier count" caption="Total airtime for the same payload; differences come from symbol/cyclic-prefix overhead and the fixed header.">
          <LineSeriesChart data={dur.rows} xKey="x" series={modSeries(dur.series)} xLabel="number of carriers (log scale)" yLabel="duration (s)" xScale="log" xFormatter={(v) => String(v)} yFormatter={(v) => v.toFixed(2)} />
        </Card>
        <SpectralCard rows={spectral} />
      </div>
    );
  }

  if (experiment === "file_sizes") {
    const dur = pivot(s, "source_bytes", null, "duration_s_mean", "duration_s_ci95");
    const tp = pivot(s, "source_bytes", null, "net_bitrate_bps_mean", "net_bitrate_bps_ci95");
    return (
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Transmission time vs file size" caption="Airtime grows linearly with payload; the intercept is the fixed preamble + header cost.">
          <LineSeriesChart data={dur.rows} xKey="x" series={[{ key: "value", name: "duration", errorKey: "value_err", color: SERIES[0] }]} xLabel="file size (bytes)" yLabel="duration (s)" xFormatter={(v) => (v >= 1024 ? `${(v / 1024).toFixed(0)}k` : String(v))} yFormatter={(v) => v.toFixed(1)} />
        </Card>
        <Card title="Net throughput vs file size" caption="Net rate approaches the PHY rate as the fixed header overhead is amortised over a longer payload.">
          <LineSeriesChart data={tp.rows} xKey="x" series={[{ key: "value", name: "net bit rate", errorKey: "value_err", color: SERIES[2] }]} xLabel="file size (bytes)" yLabel="net bit rate (bit/s)" xFormatter={(v) => (v >= 1024 ? `${(v / 1024).toFixed(0)}k` : String(v))} />
        </Card>
      </div>
    );
  }

  if (experiment === "channels") {
    const tp = pivot(s, "channel", "preset", "net_bitrate_bps_mean", "net_bitrate_bps_ci95");
    const sr = pivot(s, "channel", "preset", "success_rate");
    return (
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Net throughput by channel and preset" caption="Mean net bit rate (±95% CI) of each OFDM preset in each synthetic room model.">
          <GroupedBarChart data={tp.rows} xKey="x" series={tp.series.map((p, i) => ({ key: p, name: p, errorKey: `${p}_err`, color: SERIES[i % SERIES.length] }))} xLabel="channel model" yLabel="net bit rate (bit/s)" height={300} />
        </Card>
        <Card title="Success rate by channel and preset" caption="Fraction of bit-exact reconstructions.">
          <GroupedBarChart data={sr.rows} xKey="x" series={sr.series.map((p, i) => ({ key: p, name: p, color: SERIES[i % SERIES.length] }))} xLabel="channel model" yLabel="success rate" height={300} yDomain={[0, 1]} yFormatter={(v) => v.toFixed(2)} />
        </Card>
      </div>
    );
  }

  if (experiment === "adaptive") {
    const tp = pivot(s, "channel", "scheme", "net_bitrate_bps_mean", "net_bitrate_bps_ci95");
    const order = ["fixed_default", "fixed_best", "adaptive"];
    const series = order.filter((k) => tp.series.includes(k)).map((k, i) => ({ key: k, name: k.replace("_", " "), errorKey: `${k}_err`, color: SERIES[i] }));
    return (
      <div className="grid grid-cols-1 gap-4">
        <Card title="Adaptive vs fixed modulation per channel" caption="Net throughput (±95% CI) for the default fixed scheme, the best single fixed modulation for that channel, and per-band adaptive bit-loading (which spends a few bytes of feedback overhead).">
          <GroupedBarChart data={tp.rows} xKey="x" series={series} xLabel="channel model" yLabel="net bit rate (bit/s)" height={320} />
        </Card>
      </div>
    );
  }

  if (experiment === "cp_vs_reverb") {
    const tp = pivot(s, "rt60_s", "cp_len", "net_bitrate_bps_mean", "net_bitrate_bps_ci95");
    const sr = pivot(s, "rt60_s", "cp_len", "success_rate");
    const cpSeries = (names: string[]) => [...names].sort((a, b) => Number(a) - Number(b)).map((k, i) => ({ key: k, name: `CP ${k}`, color: SERIES[i % SERIES.length] }));
    return (
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Net throughput vs reverberation time by cyclic prefix" caption="Longer cyclic prefixes absorb more echo (RT60) at the cost of per-symbol overhead (±95% CI).">
          <LineSeriesChart data={tp.rows} xKey="x" series={cpSeries(tp.series).map((x) => ({ ...x, errorKey: `${x.key}_err` }))} xLabel="RT60 (s)" yLabel="net bit rate (bit/s)" />
        </Card>
        <Card title="Success rate vs reverberation time by cyclic prefix" caption="Fraction of bit-exact reconstructions.">
          <LineSeriesChart data={sr.rows} xKey="x" series={cpSeries(sr.series)} xLabel="RT60 (s)" yLabel="success rate" yDomain={[0, 1]} yFormatter={(v) => v.toFixed(2)} />
        </Card>
      </div>
    );
  }

  if (experiment === "density_vs_bandwidth") {
    const tp = pivot(s, "target_carriers", "label", "net_bitrate_bps_mean", "net_bitrate_bps_ci95");
    const phy = pivot(s, "target_carriers", "label", "info_bitrate_bps");
    const merged = tp.rows.map((r) => {
      const p = phy.rows.find((q) => q.x === r.x) ?? {};
      const o: Record<string, unknown> = { ...r };
      for (const m of phy.series) o[`${m}_phy`] = p[m] ?? null;
      return o;
    });
    const series: LineSeries[] = [
      ...tp.series.map((k, i) => ({ key: k, name: k, errorKey: `${k}_err`, color: SERIES[i % SERIES.length] })),
      ...phy.series.map((k, i) => ({ key: `${k}_phy`, name: `${k} PHY info rate`, color: SERIES[i % SERIES.length], dashed: true })),
    ];
    return (
      <Card title="Throughput vs carrier count by bandwidth policy" caption="Solid: measured net throughput (±95% CI). Dashed: PHY information rate. With equal bandwidth the PHY rate is identical by construction; with equal spacing the bandwidth (and rate) scales with carrier count.">
        <LineSeriesChart data={merged} xKey="x" series={series} xLabel="number of carriers (log scale)" yLabel="bit rate (bit/s)" height={320} xScale="log" xFormatter={(v) => String(v)} />
      </Card>
    );
  }

  if (experiment === "sro_tolerance") {
    const withKey = s.map((r) => ({ ...r, mr: `${r.modulation ?? ""} ${r.code_rate ?? ""}`.trim() }));
    const tp = pivot(withKey, "ppm", "mr", "net_bitrate_bps_mean", "net_bitrate_bps_ci95");
    const sr = pivot(withKey, "ppm", "mr", "success_rate");
    const ser = (names: string[], err: boolean) => names.map((k, i) => ({ key: k, name: k, color: SERIES[i % SERIES.length], errorKey: err ? `${k}_err` : undefined }));
    return (
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="Net throughput vs sample-rate offset" caption="Clock mismatch between transmitter and receiver in parts per million; the pilot-based tracker compensates up to a limit (±95% CI).">
          <LineSeriesChart data={tp.rows} xKey="x" series={ser(tp.series, true)} xLabel="sample-rate offset (ppm)" yLabel="net bit rate (bit/s)" />
        </Card>
        <Card title="Success rate vs sample-rate offset" caption="Fraction of bit-exact reconstructions.">
          <LineSeriesChart data={sr.rows} xKey="x" series={ser(sr.series, false)} xLabel="sample-rate offset (ppm)" yLabel="success rate" yDomain={[0, 1]} yFormatter={(v) => v.toFixed(2)} />
        </Card>
      </div>
    );
  }

  return (
    <Card title="Summary" caption="No dedicated chart for this experiment; raw summary rows are shown.">
      <pre className="plain max-h-80 overflow-auto text-xs text-ink2">{JSON.stringify(summary.slice(0, 50), null, 1)}</pre>
    </Card>
  );
}

function SpectralCard({ rows }: { rows: { modulation: string; se: number }[] }) {
  return (
    <Card title="Spectral efficiency vs modulation" caption="Information bits per second per hertz of occupied bandwidth (after FEC), from the configuration used in this run.">
      {rows.length ? (
        <GroupedBarChart data={rows.map((r) => ({ ...r }))} xKey="modulation" series={[{ key: "se", name: "bit/s/Hz", color: SERIES[6] }]} xLabel="modulation" yLabel="bit/s/Hz" height={240} yFormatter={(v) => v.toFixed(2)} />
      ) : (
        <div className="text-xs text-muted">No modulation groups in this summary.</div>
      )}
    </Card>
  );
}

function CompressionCharts({ records }: { records: TrialRecord[] }) {
  const { rows, algos } = useMemo(() => {
    const acc = new Map<string, Map<string, { sum: number; n: number }>>();
    const algos = new Set<string>();
    for (const r of records) {
      if (!r.language || !r.algorithm || !isNum(r.bits_per_byte)) continue;
      algos.add(r.algorithm);
      const byAlgo = acc.get(r.language) ?? new Map();
      const cur = byAlgo.get(r.algorithm) ?? { sum: 0, n: 0 };
      cur.sum += r.bits_per_byte;
      cur.n += 1;
      byAlgo.set(r.algorithm, cur);
      acc.set(r.language, byAlgo);
    }
    const rows = Array.from(acc.entries()).map(([language, m]) => {
      const row: Record<string, unknown> = { language };
      for (const [a, v] of m) row[a] = v.sum / v.n;
      return row;
    });
    return { rows, algos: Array.from(algos) };
  }, [records]);
  const stats = useMemo(() => {
    const ok = records.filter((r) => r.lossless !== undefined);
    return { n: records.length, lossless: ok.filter((r) => r.lossless).length };
  }, [records]);

  return (
    <div className="flex flex-col gap-4">
      <StatGrid cols={3}>
        <NumberStat label="Records" value={stats.n} />
        <NumberStat label="Lossless round-trips" value={`${stats.lossless} / ${stats.n}`} tone={stats.lossless === stats.n ? "good" : "bad"} />
        <NumberStat label="Algorithms" value={algos.join(", ") || DASH} />
      </StatGrid>
      <Card title="Compression: bits per source byte by language and algorithm" caption="Mean output bits per input byte (lower is better; 8 = no compression). Code-aware compression exploits language syntax; general-purpose codecs vary with sample size.">
        {rows.length ? (
          <GroupedBarChart data={rows} xKey="language" series={algos.slice(0, 8).map((a, i) => ({ key: a, name: a, color: SERIES[i] }))} xLabel="language / kind" yLabel="bits per byte" height={320} yFormatter={(v) => v.toFixed(2)} yDomain={[0, 8]} />
        ) : (
          <div className="text-xs text-muted">No compression records.</div>
        )}
      </Card>
    </div>
  );
}
