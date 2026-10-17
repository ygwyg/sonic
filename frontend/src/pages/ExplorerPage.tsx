import { useCallback, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import CarrierAllocationChart from "../charts/CarrierAllocationChart";
import ConstellationScatter from "../charts/ConstellationScatter";
import EnvelopeChart from "../charts/EnvelopeChart";
import GroupedBarChart from "../charts/GroupedBarChart";
import SpectrogramCanvas from "../charts/SpectrogramCanvas";
import SpectrumChart from "../charts/SpectrumChart";
import { SECTION_COLORS, SERIES, TOOLTIP_STYLE } from "../charts/theme";
import Card from "../components/Card";
import ErrorBanner from "../components/ErrorBanner";
import FileDrop from "../components/FileDrop";
import NumberStat, { StatGrid } from "../components/NumberStat";
import PageHeader from "../components/PageHeader";
import api, { type AnalyzeResponse, type CarriersDemo, type EncodeResponse } from "../services/api";
import { DASH, fmt, fmtDb, fmtHz, fmtInt, fmtS, sectionLabel } from "../services/format";
import { useAppState } from "../state/AppState";

const DEMO_TEXT = "Sonic demo transmission: OFDM carriers overlap in frequency but stay orthogonal over one symbol.";

export default function ExplorerPage() {
  const { lastEncode, lastEncodeLabel, setLastEncode } = useAppState();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<{ name: string; analysis: AnalyzeResponse } | null>(null);
  const [view, setView] = useState<"encode" | "upload">("encode");

  const generateDemo = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.encode({ text: DEMO_TEXT, config: { preset: "default" }, compression: "auto", payload_type: "text", amplitude: 0.8, channel: { preset: "quiet_room" } });
      setLastEncode(r, "demo (default preset, quiet_room channel)");
      setView("encode");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onUpload = useCallback(async (f: File) => {
    setBusy(true);
    setError(null);
    try {
      const a = await api.analyze(f, f.name);
      setUploaded({ name: f.name, analysis: a });
      setView("upload");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Waveform Explorer"
        subtitle="Look inside an OFDM transmission: time, frequency, carrier allocation, orthogonality and constellations."
        actions={
          <div className="flex flex-wrap gap-2">
            <button className="btn" onClick={generateDemo} disabled={busy}>
              {busy ? "Working…" : "Generate demo"}
            </button>
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card title="Source">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <div className="flex rounded-md border border-line p-0.5">
              <button className={`tab ${view === "encode" ? "tab-active" : ""}`} onClick={() => setView("encode")} disabled={!lastEncode}>
                Transmission {lastEncode ? "" : "(none yet)"}
              </button>
              <button className={`tab ${view === "upload" ? "tab-active" : ""}`} onClick={() => setView("upload")} disabled={!uploaded}>
                Uploaded WAV {uploaded ? "" : "(none)"}
              </button>
            </div>
            <span className="num text-xs text-muted">
              {view === "encode" ? (lastEncode ? `buffer: ${lastEncodeLabel ?? "transmitter output"}` : "Use the Transmitter's “Send to Explorer” or generate a demo.") : uploaded ? uploaded.name : ""}
            </span>
          </div>
        </Card>
        <Card title="Analyze a WAV file" subtitle="Waveform, spectrum and spectrogram only (no transmitter metadata).">
          <FileDrop compact accept=".wav,audio/wav,audio/x-wav" onFile={onUpload} disabled={busy} label="Drop a WAV or click" />
        </Card>
      </div>

      {error && <ErrorBanner onDismiss={() => setError(null)}>{error}</ErrorBanner>}

      {view === "encode" && lastEncode && <EncodeExplorer r={lastEncode} />}
      {view === "upload" && uploaded && <UploadExplorer name={uploaded.name} a={uploaded.analysis} />}
      {!lastEncode && !uploaded && (
        <Card>
          <div className="py-10 text-center text-sm text-muted">Nothing to explore yet. Generate a demo transmission or upload a WAV file.</div>
        </Card>
      )}
    </div>
  );
}

// ------------------------------------------------------------- uploaded WAV

function UploadExplorer({ name, a }: { name: string; a: AnalyzeResponse }) {
  return (
    <div className="flex flex-col gap-4">
      <StatGrid cols={6}>
        <NumberStat label="File" value={name} />
        <NumberStat label="Sample rate" value={fmtInt(a.waveform.sample_rate)} unit="Hz" />
        <NumberStat label="Duration" value={fmtS(a.waveform.duration_s)} />
        <NumberStat label="Peak" value={fmt(a.waveform.peak, 3)} />
        <NumberStat label="RMS" value={fmt(a.waveform.rms, 4)} />
        <NumberStat label="PAPR" value={fmtDb(a.waveform.papr_db)} />
      </StatGrid>
      {a.decode && (
        <ErrorBanner tone={a.decode.success ? "good" : "warn"} title={a.decode.success ? "A Sonic transmission was decoded from this file" : "No decodable Sonic transmission found"}>
          {a.decode.success ? `${a.decode.header?.payload_type ?? ""} · ${a.decode.header?.original_length ?? DASH} B · ${a.decode.header?.compression ?? ""}` : a.decode.error ?? ""}
          {" "}— open the Receiver page for full diagnostics.
        </ErrorBanner>
      )}
      <Card title="1 · Time-domain envelope" caption="Min/max of the samples in short windows. Shows the overall level and where the signal starts and stops.">
        <EnvelopeChart waveform={a.waveform} sections={a.decode?.diagnostics?.layout ? layoutToSections(a.decode.diagnostics.layout) : null} />
      </Card>
      <Card title="2 · Power spectrum" caption="Averaged periodogram in dB. An OFDM signal shows as a flat plateau over its band with steep edges.">
        <SpectrumChart spectrum={a.spectrum} />
      </Card>
      <Card title="3 · Spectrogram" caption="Power over time and frequency. The header band (1–7 kHz) and payload band appear as distinct blocks.">
        <SpectrogramCanvas spectrogram={a.spectrogram} />
      </Card>
    </div>
  );
}

function layoutToSections(layout: Record<string, [number, number]>) {
  return Object.entries(layout).map(([name, [start, end]]) => ({ name, start, end }));
}

// ------------------------------------------------------- encoded transmission

function EncodeExplorer({ r }: { r: EncodeResponse }) {
  const a = r.analysis;
  const cfg = r.info.config;
  const band: [number, number] = [cfg.f_low, cfg.f_high];
  const nyq = cfg.sample_rate / 2;

  const sectionRows = useMemo(() => {
    const sef = a.power?.section_energy_fraction ?? {};
    return Object.entries(sef).map(([name, v]) => ({ name: sectionLabel(name), key: name, fraction: v }));
  }, [a.power]);

  const perCarrier = useMemo(() => {
    const p = a.power?.per_carrier_power;
    const f = a.power?.carrier_frequencies_hz ?? [];
    if (!p) return [];
    return p.map((v, i) => ({ f: f[i], p: v }));
  }, [a.power]);

  const rxConst = r.decode?.diagnostics?.payload_section?.constellation;

  return (
    <div className="flex flex-col gap-4">
      <StatGrid cols={6}>
        <NumberStat label="Duration" value={fmtS(r.info.duration_s)} />
        <NumberStat label="Sample rate" value={fmtInt(cfg.sample_rate)} unit="Hz" />
        <NumberStat label="Modulation" value={`${cfg.modulation} · ${cfg.code_rate}`} />
        <NumberStat label="Band" value={`${(cfg.f_low / 1000).toFixed(1)}–${(cfg.f_high / 1000).toFixed(1)} kHz`} />
        <NumberStat label="Carriers (data/pilot)" value={`${cfg.n_enabled_data_carriers} / ${cfg.n_pilot_carriers}`} />
        <NumberStat label="PAPR" value={fmtDb(r.info.papr_db)} />
      </StatGrid>

      <Card title="1 · Time-domain envelope with sections" caption="Each colored band is one part of the frame: preamble (sync), guard, header training + header data in the fixed 1–7 kHz band, then payload training + payload data in the configured band.">
        <EnvelopeChart waveform={a.waveform} sections={a.sections ?? r.info.sections} />
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card title="2 · Power spectrum" caption="Averaged power in dB versus frequency. The shaded band is the payload band; the header occupies 1–7 kHz.">
          <SpectrumChart spectrum={a.spectrum} band={band} />
        </Card>
        <Card title="3 · Spectrogram" caption="Energy over time (x) and frequency (y). Header symbols in the low band precede the wider-band payload.">
          <SpectrogramCanvas spectrogram={a.spectrogram} />
        </Card>
      </div>

      {a.allocation && (
        <Card
          title="4 · OFDM carrier allocation"
          subtitle={`${a.allocation.n_fft}-point FFT · ${fmt(a.allocation.carrier_spacing_hz, 2)} Hz spacing · ${a.allocation.n_data} data + ${a.allocation.n_pilot} pilot carriers · ${a.allocation.bits_per_symbol} bits/symbol`}
          caption="Every tick is one sub-carrier. Pilots (amber) carry known symbols for channel estimation; the rest carry data at the chosen modulation. Grey regions are guard bands kept clear of speaker and microphone roll-off."
        >
          <div className="flex flex-col gap-4">
            <CarrierAllocationChart allocation={a.allocation} fMax={nyq} label={`Payload band (${fmtHz(cfg.f_low)} – ${fmtHz(cfg.f_high)})`} />
            {a.header_allocation && <CarrierAllocationChart allocation={a.header_allocation} fMax={nyq} label="Header band (fixed 1–7 kHz, BPSK, robust)" />}
          </div>
        </Card>
      )}

      {a.carriers_demo && <CarriersDemoPanel demo={a.carriers_demo} sampleRate={cfg.sample_rate} />}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card
          title="7 · Transmitted constellation"
          subtitle={`${cfg.modulation} symbols, one OFDM symbol`}
          caption="Each point is one data carrier's complex symbol (I = in-phase, Q = quadrature). Higher-order QAM packs more bits per point but needs more SNR."
        >
          <div className="flex flex-wrap gap-6">
            {a.constellation_tx && <ConstellationScatter points={a.constellation_tx} title="Transmitted" color={SERIES[0]} />}
            {rxConst && <ConstellationScatter points={rxConst} title={`Received (${r.channel?.name ?? "channel"}${r.channel?.snr_db != null ? ` @ ${r.channel.snr_db} dB` : ""})`} color={SERIES[2]} />}
            {!rxConst && <div className="self-center text-xs text-muted">Enable a simulated channel in the Transmitter to see the received constellation next to it.</div>}
          </div>
        </Card>

        <Card title="8 · Power distribution" caption="Left: fraction of the total transmitted energy in each frame section. Right: average power per data carrier across the payload.">
          <div className="grid grid-cols-1 gap-3">
            <div>
              <div className="mb-1 text-xs text-ink2">Section energy fraction</div>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={sectionRows} margin={{ top: 4, right: 12, left: 4, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="2 4" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} stroke="#262d38" angle={-20} textAnchor="end" height={42} />
                  <YAxis width={44} tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} stroke="#262d38" />
                  <Tooltip {...TOOLTIP_STYLE} cursor={{ fill: "rgba(255,255,255,0.04)" }} formatter={(v: number) => [`${(v * 100).toFixed(2)} %`, "energy"]} />
                  <Bar dataKey="fraction" isAnimationActive={false} radius={[3, 3, 0, 0]} fill={SERIES[0]} shape={(props: { x?: number; y?: number; width?: number; height?: number; payload?: { key: string } }) => <rect x={props.x} y={props.y} width={props.width} height={props.height} rx={3} fill={SECTION_COLORS[props.payload?.key ?? ""] ?? SERIES[0]} />} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div>
              <div className="mb-1 text-xs text-ink2">Per-carrier power (payload)</div>
              {perCarrier.length ? (
                <ResponsiveContainer width="100%" height={160}>
                  <LineChart data={perCarrier} margin={{ top: 4, right: 12, left: 4, bottom: 16 }}>
                    <CartesianGrid strokeDasharray="2 4" />
                    <XAxis dataKey="f" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}k`} label={{ value: "frequency (Hz)", position: "insideBottom", offset: -8, fill: "#7a8595", fontSize: 11 }} stroke="#262d38" />
                    <YAxis width={58} domain={[0, "auto"]} tickFormatter={(v: number) => v.toExponential(1)} label={{ value: "power", angle: -90, position: "insideLeft", offset: 12, fill: "#7a8595", fontSize: 11, style: { textAnchor: "middle" } }} stroke="#262d38" />
                    <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => [v.toExponential(3), "power"]} labelFormatter={(v: number) => `${v.toFixed(1)} Hz`} />
                    <Line dataKey="p" dot={false} stroke={SERIES[3]} strokeWidth={1.5} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-xs text-muted">Per-carrier power not available (—).</div>
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

// --------------------------------------------------- carriers demo (5 and 6)

function CarriersDemoPanel({ demo, sampleRate }: { demo: CarriersDemo; sampleRate: number }) {
  const [enabled, setEnabled] = useState<boolean[]>(() => demo.components.map(() => true));
  const [showSum, setShowSum] = useState(true);
  const n = demo.composite.length;

  const rows = useMemo(() => {
    const out: Record<string, number>[] = [];
    for (let i = 0; i < n; i++) {
      const row: Record<string, number> = { t: (i / sampleRate) * 1000, composite: demo.composite[i] };
      let sum = 0;
      demo.components.forEach((c, k) => {
        const v = c.samples[i] ?? 0;
        row[`c${k}`] = v;
        if (enabled[k]) sum += v;
      });
      row.sum = sum;
      out.push(row);
    }
    return out;
  }, [demo, enabled, n, sampleRate]);

  const fftRows = useMemo(
    () => demo.carrier_frequencies_hz.map((f, i) => ({ f, mag: demo.carrier_magnitudes[i], phase: demo.carrier_phases[i] })),
    [demo]
  );

  const toggle = (k: number) => setEnabled((e) => e.map((v, i) => (i === k ? !v : v)));

  return (
    <>
      <Card
        title="5 · Overlapping carriers in one OFDM symbol"
        subtitle={`first ${n} samples (${((n / sampleRate) * 1000).toFixed(2)} ms) · showing ${demo.shown} of ${demo.n_total_carriers} carriers`}
        caption="Top: the composite symbol as actually transmitted. Bottom: individual sub-carrier sinusoids, each a pure tone with its own amplitude and phase. Toggle carriers to see the “sum of enabled” trace build up toward the composite — with all carriers enabled, the sum of the shown components approximates the composite (the remaining carriers are not plotted)."
      >
        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
          {demo.components.map((c, k) => (
            <button
              key={c.carrier}
              className={`rounded border px-2 py-0.5 num ${enabled[k] ? "border-line text-ink" : "border-line/50 text-muted line-through"}`}
              style={{ borderColor: enabled[k] ? SERIES[k % SERIES.length] : undefined }}
              onClick={() => toggle(k)}
            >
              <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: SERIES[k % SERIES.length] }} />
              k={c.carrier} · {c.frequency_hz.toFixed(0)} Hz
            </button>
          ))}
          <label className="ml-auto flex items-center gap-1">
            <input type="checkbox" checked={showSum} onChange={(e) => setShowSum(e.target.checked)} /> overlay sum of enabled
          </label>
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={rows} margin={{ top: 4, right: 12, left: 4, bottom: 16 }} syncId="carriers">
            <CartesianGrid strokeDasharray="2 4" />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v: number) => v.toFixed(1)} label={{ value: "time (ms)", position: "insideBottom", offset: -8, fill: "#7a8595", fontSize: 11 }} stroke="#262d38" />
            <YAxis width={60} tickFormatter={(v: number) => v.toFixed(2)} label={{ value: "amplitude", angle: -90, position: "insideLeft", offset: 12, fill: "#7a8595", fontSize: 11, style: { textAnchor: "middle" } }} stroke="#262d38" />
            <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => v.toFixed(4)} labelFormatter={(v: number) => `${v.toFixed(3)} ms`} />
            <Line dataKey="composite" name="composite symbol" dot={false} stroke="#e8ebef" strokeWidth={1.5} isAnimationActive={false} />
            {showSum && <Line dataKey="sum" name="sum of enabled components" dot={false} stroke={SERIES[1]} strokeWidth={1.5} strokeDasharray="4 3" isAnimationActive={false} />}
          </LineChart>
        </ResponsiveContainer>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={rows} margin={{ top: 4, right: 12, left: 4, bottom: 16 }} syncId="carriers">
            <CartesianGrid strokeDasharray="2 4" />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v: number) => v.toFixed(1)} label={{ value: "time (ms)", position: "insideBottom", offset: -8, fill: "#7a8595", fontSize: 11 }} stroke="#262d38" />
            <YAxis width={60} tickFormatter={(v: number) => v.toFixed(2)} label={{ value: "amplitude", angle: -90, position: "insideLeft", offset: 12, fill: "#7a8595", fontSize: 11, style: { textAnchor: "middle" } }} stroke="#262d38" />
            <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => v.toFixed(4)} labelFormatter={(v: number) => `${v.toFixed(3)} ms`} />
            {demo.components.map((c, k) =>
              enabled[k] ? <Line key={c.carrier} dataKey={`c${k}`} name={`carrier ${c.carrier} (${c.frequency_hz.toFixed(0)} Hz)`} dot={false} stroke={SERIES[k % SERIES.length]} strokeWidth={1.25} isAnimationActive={false} /> : null
            )}
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <Card
        title="6 · FFT separation: magnitude and phase per carrier"
        caption="The receiver takes one FFT of the symbol and every carrier lands in its own bin. Magnitude shows the carrier is present; phase (and magnitude for QAM) carries the data bits."
      >
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <div>
            <div className="mb-1 text-xs text-ink2">|X[k]| — carrier magnitude</div>
            <GroupedBarChart data={fftRows.map((r) => ({ ...r, fl: `${(r.f / 1000).toFixed(2)}k` }))} xKey="fl" series={[{ key: "mag", name: "magnitude", color: SERIES[0] }]} xLabel="carrier frequency (kHz)" yLabel="magnitude" height={220} yFormatter={(v) => v.toFixed(2)} />
          </div>
          <div>
            <div className="mb-1 text-xs text-ink2">∠X[k] — carrier phase</div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={fftRows} margin={{ top: 8, right: 16, left: 8, bottom: 20 }}>
                <CartesianGrid strokeDasharray="2 4" />
                <XAxis dataKey="f" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}k`} label={{ value: "frequency (Hz)", position: "insideBottom", offset: -12, fill: "#7a8595", fontSize: 11 }} stroke="#262d38" />
                <YAxis width={60} domain={[-Math.PI, Math.PI]} ticks={[-Math.PI, -Math.PI / 2, 0, Math.PI / 2, Math.PI]} tickFormatter={(v: number) => `${(v / Math.PI).toFixed(1)}π`} label={{ value: "phase (rad)", angle: -90, position: "insideLeft", offset: 12, fill: "#7a8595", fontSize: 11, style: { textAnchor: "middle" } }} stroke="#262d38" />
                <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => [`${v.toFixed(3)} rad`, "phase"]} labelFormatter={(v: number) => `${v.toFixed(1)} Hz`} />
                <Line dataKey="phase" dot={{ r: 2, strokeWidth: 0, fill: SERIES[4] }} stroke="none" isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </Card>
    </>
  );
}
