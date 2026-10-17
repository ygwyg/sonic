/* Typed client for the Sonic FastAPI backend. All paths are relative to /api,
 * which the Vite dev server proxies to http://127.0.0.1:8000. */

// ----------------------------------------------------------------- types

export type Modulation = "bpsk" | "qpsk" | "16qam" | "64qam" | "256qam";
export type CodeRate = "1/2" | "2/3" | "3/4";
export type Compression = "auto" | "none" | "zlib" | "lzma" | "zstd" | "codeaware";
export type PayloadType = "text" | "json" | "url" | "binary" | "code" | "contact";

export interface ConfigDescribe {
  sample_rate: number;
  n_fft: number;
  cp_len: number;
  f_low: number;
  f_high: number;
  pilot_spacing: number;
  modulation: string;
  code_rate: string;
  band_modulations: (string | null)[];
  n_training: number;
  packet_size: number;
  carrier_spacing_hz: number;
  n_active_carriers: number;
  n_pilot_carriers: number;
  n_data_carriers: number;
  n_enabled_data_carriers: number;
  bits_per_ofdm_symbol: number;
  symbol_duration_s: number;
  occupied_bandwidth_hz: number;
  raw_bitrate_bps: number;
  info_bitrate_bps: number;
  spectral_efficiency_bps_per_hz: number;
}

export interface ConfigModel {
  preset?: string;
  sample_rate?: number;
  n_fft?: number;
  cp_len?: number;
  f_low?: number;
  f_high?: number;
  pilot_spacing?: number;
  modulation?: string;
  code_rate?: string;
  band_modulations?: (string | null)[];
  n_training?: number;
  packet_size?: number;
}

export interface ChannelModel {
  preset?: string;
  snr_db?: number | null;
  multipath?: [number, number][];
  reverb_rt60_s?: number;
  reverb_level?: number;
  tilt_db_per_khz?: number;
  notches?: [number, number, number][];
  lowpass_hz?: number | null;
  highpass_hz?: number | null;
  sample_rate_ppm?: number;
  frequency_offset_hz?: number;
  timing_offset_s?: number;
  tones?: [number, number][];
  burst_level_db?: number | null;
  burst_duty?: number;
  clip_level?: number | null;
  seed?: number;
}

export interface ChannelDescribe {
  name: string;
  snr_db: number | null;
  multipath: number[][];
  reverb_rt60_s: number;
  reverb_level: number;
  tilt_db_per_khz: number;
  notches: number[][];
  lowpass_hz: number | null;
  highpass_hz: number | null;
  sample_rate_ppm: number;
  frequency_offset_hz: number;
  timing_offset_s: number;
  tones: number[][];
  burst_level_db: number | null;
  burst_duty: number;
  burst_len_s?: number;
  clip_level: number | null;
  seed: number;
}

export interface Presets {
  ofdm: Record<string, ConfigDescribe>;
  header: ConfigDescribe;
  channels: Record<string, ChannelDescribe>;
  modulations: string[];
  code_rates: string[];
  compression: string[];
  payload_types: string[];
  limits: { max_payload_bytes: number; max_upload_bytes: number };
}

export interface Estimate {
  payload_bytes: number;
  duration_s: number;
  n_samples: number;
  n_header_symbols: number;
  n_payload_symbols: number;
  net_bitrate_bps: number;
  info_bitrate_bps: number;
  raw_bitrate_bps: number;
  spectral_efficiency: number;
}

export interface EstimateResponse {
  config: ConfigDescribe;
  estimate: Estimate;
}

export interface Section {
  name: string;
  start: number;
  end: number;
}

export interface HeaderInfo {
  version: number;
  tx_id: number;
  payload_type: string;
  compression: string;
  original_length: number;
  payload_length: number;
  packet_size: number;
  n_packets: number;
  sha256: string;
  filename: string;
  config: ConfigDescribe;
}

export interface CompressionInfo {
  algorithm: string;
  original_size: number;
  compressed_size: number;
  ratio: number;
  candidates: Record<string, number>;
}

export interface EncodeInfo {
  sample_rate: number;
  n_samples: number;
  duration_s: number;
  peak: number;
  rms: number;
  papr_db: number;
  info_bits: number;
  coded_bits: number;
  encode_time_s: number;
  net_bitrate_bps: number;
  transmitted_bitrate_bps: number;
  compression: CompressionInfo;
  header: HeaderInfo;
  config: ConfigDescribe;
  sections: Section[];
  n_header_symbols: number;
  n_payload_symbols: number;
}

export interface WaveformAnalysis {
  sample_rate: number;
  n_samples: number;
  duration_s: number;
  peak: number;
  rms: number;
  papr_db: number;
  envelope: { index: number[]; min: number[]; max: number[] };
}

export interface SpectrumAnalysis {
  frequency_hz: number[];
  power_db: number[];
}

export interface SpectrogramAnalysis {
  time_s: number[];
  frequency_hz: number[];
  db: number[][];
  db_min: number;
  db_max: number;
}

export interface Allocation {
  n_fft: number;
  carrier_spacing_hz: number;
  carriers: number[];
  frequencies_hz: number[];
  roles: string[];
  pilot_carriers: number[];
  n_data: number;
  n_pilot: number;
  guard_low_hz: number;
  guard_high_hz: number;
  bits_per_symbol: number;
}

export interface CarrierComponent {
  carrier: number;
  frequency_hz: number;
  magnitude: number;
  phase_rad: number;
  samples: number[];
}

export interface CarriersDemo {
  n_fft: number;
  shown: number;
  n_total_carriers: number;
  composite: number[];
  components: CarrierComponent[];
  carrier_magnitudes: number[];
  carrier_phases: number[];
  carrier_frequencies_hz: number[];
}

export interface Constellation {
  re: number[];
  im: number[];
}

export interface PowerAnalysis {
  section_energy_fraction: Record<string, number>;
  per_carrier_power: number[] | null;
  carrier_frequencies_hz: number[];
}

export interface Analysis {
  waveform: WaveformAnalysis;
  spectrum: SpectrumAnalysis;
  spectrogram: SpectrogramAnalysis;
  allocation?: Allocation;
  header_allocation?: Allocation;
  sections?: Section[];
  carriers_demo?: CarriersDemo;
  constellation_tx?: Constellation;
  power?: PowerAnalysis;
}

export interface SyncCandidate {
  position: number;
  score: number;
}

export interface SectionDiag {
  window_start: number;
  timing_refine_samples: number;
  n_symbols_requested: number;
  n_symbols_available: number;
  truncated: boolean;
  channel_magnitude_db: number[];
  carriers: number[];
  carrier_frequencies_hz: number[];
  snr_training_db: number[] | null;
  snr_training_mean_db: number | null;
  snr_evm_db: number[] | null;
  snr_evm_mean_db: number | null;
  timing_drift_samples: number[];
  common_phase_rad: number[];
  gain_track: number[];
  constellation: Constellation;
}

export interface PacketReport {
  n_packets: number;
  n_ok: number;
  crc_failed: number[];
  index_mismatch: number[];
  packet_error_rate: number;
  missing: number;
}

export interface Diagnostics {
  input?: { n_samples: number; duration_s: number; peak: number; rms: number; clipped_fraction: number };
  sync?: { candidates: SyncCandidate[]; threshold: number; selected: number | null };
  header_section?: SectionDiag;
  header?: HeaderInfo;
  layout?: Record<string, [number, number]>;
  payload_section?: SectionDiag;
  packets?: PacketReport;
  sha256?: { expected: string; actual: string; match: boolean };
  raw_ber?: number;
  raw_bit_errors?: number;
  raw_bits_compared?: number;
  evm_rms?: number;
  snr_from_evm_db?: number;
  stage_failed?: string;
  [key: string]: unknown;
}

export interface DecodeResponse {
  success: boolean;
  error: string | null;
  header: HeaderInfo | null;
  decode_time_s: number;
  diagnostics: Diagnostics;
  data_base64?: string;
  text?: string | null;
  input?: { sample_rate: number; channels: number; duration_s: number };
}

export interface EncodeResponse {
  info: EncodeInfo;
  wav_base64: string;
  analysis: Analysis;
  channel?: ChannelDescribe;
  received_wav_base64?: string;
  decode?: DecodeResponse;
  received_analysis?: Analysis;
}

export interface AnalyzeResponse {
  waveform: WaveformAnalysis;
  spectrum: SpectrumAnalysis;
  spectrogram: SpectrogramAnalysis;
  decode: { success: boolean; error: string | null; header: HeaderInfo | null; decode_time_s: number; diagnostics: Diagnostics };
}

export interface ChannelApplyResponse {
  wav_base64: string;
  decode: DecodeResponse;
  channel: ChannelDescribe;
}

export interface QrDecodeResponse {
  success: boolean;
  error: string | null;
  header: HeaderInfo | null;
  decode_time_s: number;
  data_base64?: string;
  text?: string | null;
  summary: {
    sync_score: number | null;
    snr_db: number | null;
    packets: PacketReport | null;
    sha256: { expected: string; actual: string; match: boolean } | null;
  };
}

export interface BitLoadingPlan {
  code_rate: string;
  band_modulations: (string | null)[];
  band_effective_snr_db: number[];
  expected_info_bitrate_bps: number;
  margin_db: number;
  rationale: string[];
}

export interface AdaptivePlanResponse {
  report: {
    n_bands: number;
    band_snr_db: number[];
    carrier_snr_db: number[];
    carrier_frequencies_hz: number[];
    overhead_bytes: number;
    probe: unknown;
  };
  plan: BitLoadingPlan;
  fixed_best: BitLoadingPlan;
  configs: { fixed_default: ConfigDescribe; fixed_best: ConfigDescribe; adaptive: ConfigDescribe };
  trials: { fixed_default: TrialRecord; fixed_best: TrialRecord; adaptive: TrialRecord };
}

/** One benchmark trial. Compression-experiment records use a subset of these
 * fields plus sample/kind/language/algorithm/bits_per_byte. */
export interface TrialRecord {
  label?: string;
  seed?: number;
  channel?: string;
  snr_db?: number | null;
  modulation?: string;
  band_modulations?: (string | null)[];
  code_rate?: string;
  n_fft?: number;
  cp_len?: number;
  n_carriers?: number;
  n_data_carriers?: number;
  n_pilots?: number;
  f_low?: number;
  f_high?: number;
  bandwidth_hz?: number;
  symbol_duration_s?: number;
  source_bytes?: number;
  compression?: string;
  compressed_bytes?: number;
  compression_ratio?: number;
  info_bits?: number;
  coded_bits?: number;
  n_samples?: number;
  duration_s?: number;
  papr_db?: number;
  raw_bitrate_bps?: number;
  info_bitrate_bps?: number;
  spectral_efficiency?: number;
  gross_bitrate_bps?: number;
  net_bitrate_bps?: number;
  success?: boolean;
  error?: string | null;
  raw_ber?: number | null;
  packet_error_rate?: number | null;
  packets_ok?: number;
  packets_total?: number;
  snr_est_db?: number | null;
  snr_training_db?: number | null;
  sync_score?: number | null;
  encode_time_s?: number;
  decode_time_s?: number;
  // experiment-specific
  target_carriers?: number;
  preset?: string;
  scheme?: "fixed_default" | "fixed_best" | "adaptive" | "probe" | string;
  plan?: unknown;
  feedback_overhead_bytes?: number;
  band_snr_db?: number[];
  // compression experiment
  sample?: string;
  kind?: string;
  language?: string;
  algorithm?: string;
  bits_per_byte?: number;
  lossless?: boolean;
  compress_time_s?: number;
  decompress_time_s?: number;
  [key: string]: unknown;
}

/** Group keys plus aggregated metrics. */
export interface SummaryRow {
  n_trials: number;
  success_rate: number;
  net_bitrate_bps_mean: number;
  net_bitrate_bps_ci95: number;
  raw_ber_mean: number | null;
  raw_ber_ci95: number | null;
  packet_error_rate_mean: number | null;
  packet_error_rate_ci95: number | null;
  snr_est_db_mean: number | null;
  snr_est_db_ci95: number | null;
  duration_s_mean: number;
  duration_s_ci95: number;
  encode_time_s_mean: number;
  encode_time_s_ci95: number;
  decode_time_s_mean: number;
  decode_time_s_ci95: number;
  compression_ratio_mean: number;
  compression_ratio_ci95: number;
  papr_db_mean: number;
  papr_db_ci95: number;
  raw_bitrate_bps: number;
  info_bitrate_bps: number;
  spectral_efficiency: number;
  bandwidth_hz: number;
  n_carriers: number;
  n_fft: number;
  symbol_duration_s: number;
  gross_bitrate_bps: number;
  // group keys (experiment dependent)
  modulation?: string;
  code_rate?: string;
  snr_db?: number | null;
  target_carriers?: number;
  source_bytes?: number;
  channel?: string;
  preset?: string;
  scheme?: string;
  [key: string]: unknown;
}

export type ExperimentName = "snr_sweep" | "carrier_density" | "file_sizes" | "channels" | "compression" | "adaptive";

export interface BenchmarkRequest {
  experiment: ExperimentName;
  trials: number;
  snrs?: number[];
  modulations?: string[];
  carrier_counts?: number[];
  channel?: ChannelModel;
  payload_bytes: number;
}

export interface BenchmarkProgress {
  experiment?: string;
  done?: number;
  total?: number;
}

export interface BenchmarkJobSummary {
  id: string;
  status: "running" | "done" | "error";
  request: BenchmarkRequest;
  progress: BenchmarkProgress;
  created: number;
  updated: number;
}

export interface BenchmarkJob extends BenchmarkJobSummary {
  error?: string | null;
  records: TrialRecord[];
  summary: SummaryRow[] | null;
}

export interface BenchmarkWsMessage {
  status: "running" | "done" | "error";
  progress: BenchmarkProgress;
  records: TrialRecord[];
  error?: string | null;
}

export interface StoredResult {
  meta?: Record<string, unknown>;
  records?: TrialRecord[];
  summary?: SummaryRow[] | null;
}

export interface ThresholdEntry {
  modulation: string;
  code_rate: string;
  threshold_channel_snr_db: number | null;
  threshold_est_snr_db: number | null;
  sweep: { snr_db: number; ok: boolean; snr_est_db: number | null }[];
}

export type StoredResults = Record<string, StoredResult | Record<string, ThresholdEntry | unknown>>;

// --------------------------------------------------------------- helpers

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") msg = body.detail;
      else if (body && body.detail) msg = JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return handle<T>(await fetch(`/api${path}`, { signal }));
}

async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return handle<T>(
    await fetch(`/api${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal,
    })
  );
}

async function postForm<T>(path: string, form: FormData, signal?: AbortSignal): Promise<T> {
  return handle<T>(await fetch(`/api${path}`, { method: "POST", body: form, signal }));
}

/** Drop undefined/empty keys so the backend falls back to preset values. */
export function cleanModel<T extends object>(m: T): Partial<T> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(m)) {
    if (v === undefined || v === "" || (typeof v === "number" && Number.isNaN(v))) continue;
    out[k] = v;
  }
  return out as Partial<T>;
}

// ------------------------------------------------------------- endpoints

export const api = {
  health: () => getJson<{ ok: boolean; version: string }>("/health"),
  presets: () => getJson<Presets>("/presets"),
  describeConfig: (config: ConfigModel, signal?: AbortSignal) =>
    postJson<ConfigDescribe>("/config/describe", cleanModel(config), signal),
  estimate: (config: ConfigModel, n_bytes: number, signal?: AbortSignal) =>
    postJson<EstimateResponse>("/estimate", { config: cleanModel(config), n_bytes }, signal),

  encode: (
    args: {
      text: string;
      config: ConfigModel;
      compression: Compression | string;
      payload_type: PayloadType | string;
      amplitude: number;
      channel?: ChannelModel | null;
    },
    signal?: AbortSignal
  ) =>
    postJson<EncodeResponse>(
      "/encode",
      {
        text: args.text,
        config: cleanModel(args.config),
        compression: args.compression,
        payload_type: args.payload_type,
        amplitude: args.amplitude,
        channel: args.channel ? cleanModel(args.channel) : undefined,
      },
      signal
    ),

  encodeFile: (
    args: {
      file: File;
      config: ConfigModel;
      compression: Compression | string;
      payload_type: PayloadType | string;
      amplitude: number;
      channel?: ChannelModel | null;
    },
    signal?: AbortSignal
  ) => {
    const fd = new FormData();
    fd.append("file", args.file, args.file.name);
    fd.append("config", JSON.stringify(cleanModel(args.config)));
    fd.append("compression", args.compression);
    fd.append("payload_type", args.payload_type);
    fd.append("amplitude", String(args.amplitude));
    fd.append("channel", args.channel ? JSON.stringify(cleanModel(args.channel)) : "");
    return postForm<EncodeResponse>("/encode/file", fd, signal);
  },

  decode: (file: Blob, channel?: ChannelModel | null, filename = "input.wav", signal?: AbortSignal) => {
    const fd = new FormData();
    fd.append("file", file, filename);
    if (channel) fd.append("channel", JSON.stringify(cleanModel(channel)));
    return postForm<DecodeResponse>("/decode", fd, signal);
  },

  analyze: (file: Blob, filename = "input.wav", signal?: AbortSignal) => {
    const fd = new FormData();
    fd.append("file", file, filename);
    return postForm<AnalyzeResponse>("/analyze", fd, signal);
  },

  channelApply: (file: Blob, channel: ChannelModel, filename = "input.wav", signal?: AbortSignal) => {
    const fd = new FormData();
    fd.append("file", file, filename);
    fd.append("channel", JSON.stringify(cleanModel(channel)));
    return postForm<ChannelApplyResponse>("/channel/apply", fd, signal);
  },

  qrEncode: (text: string, amplitude: number, payload_type: PayloadType | string, signal?: AbortSignal) =>
    postJson<EncodeResponse>("/qr/encode", { text, amplitude, payload_type }, signal),

  qrDecode: (file: Blob, filename = "recording.wav", signal?: AbortSignal) => {
    const fd = new FormData();
    fd.append("file", file, filename);
    return postForm<QrDecodeResponse>("/qr/decode", fd, signal);
  },

  adaptivePlan: (
    args: { channel: ChannelModel; config: ConfigModel; n_bands: number; margin_db: number; payload_bytes: number },
    signal?: AbortSignal
  ) =>
    postJson<AdaptivePlanResponse>(
      "/adaptive/plan",
      { ...args, channel: cleanModel(args.channel), config: cleanModel(args.config) },
      signal
    ),

  benchmarkStart: (req: BenchmarkRequest) =>
    postJson<{ job_id: string }>("/benchmark/start", {
      ...req,
      channel: req.channel ? cleanModel(req.channel) : undefined,
    }),
  benchmarkJobs: () => getJson<BenchmarkJobSummary[]>("/benchmark/jobs"),
  benchmarkJob: (jobId: string) => getJson<BenchmarkJob>(`/benchmark/${encodeURIComponent(jobId)}`),
  benchmarkExportUrl: (jobId: string, format: "csv" | "json") =>
    `/api/benchmark/${encodeURIComponent(jobId)}/export?format=${format}`,

  /** Open the live-progress WebSocket for a job. */
  benchmarkSocket: (jobId: string): WebSocket => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return new WebSocket(`${proto}//${window.location.host}/api/benchmark/ws/${encodeURIComponent(jobId)}`);
  },

  results: () => getJson<StoredResults>("/results"),
  resultPlots: () => getJson<string[]>("/results/plots"),
  resultPlotUrl: (name: string) => `/api/results/plots/${encodeURIComponent(name)}`,
};

export default api;
